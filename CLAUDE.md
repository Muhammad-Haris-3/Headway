# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Headway records the MBTA's published arrival predictions **before the outcome
exists**, observes what actually happened, and grades them. It forecasts
nothing. The value of the whole project is the credibility of that record, so
most of the design decisions here are about making the record hard to edit,
hard to cherry-pick, and honest about its own gaps.

Status: M0 complete, collecting. **No accuracy figures are published yet** and
nothing in the API or web layer may publish one until the pre-registered
threshold is met (see Invariants).

## Commands

```bash
python -m venv .venv && .venv/Scripts/activate      # Windows; Python 3.13.1
pip install -r requirements.txt pytest              # pytest is not in requirements.txt
cp .env.example .env                                # then fill in DATABASE_URL (owner)

python ingest/m0_setup.py            # apply sql/schema.sql, create roles, TEST the grants,
                                     #   write INGEST_/APP_DATABASE_URL back into .env
python ingest/m0_setup.py --rotate   # only when you intend to break deployed credentials
psql "$DATABASE_URL" -f sql/retention.sql   # see "Two-step schema" below — nothing does this for you

python ingest/collect.py --minutes 20   # ingest (append-only role)
python ingest/retain.py --dry-run       # aggregate/seal/prune, reporting only
python ingest/retain.py                 # live; runs as OWNER

pytest tests/ -v
pytest tests/test_headway.py::test_matches_is_a_view_not_a_table -v   # single test

uvicorn api.main:app --reload --port 8000    # API, read-only role
cd web && npm install && npm run dev         # Next.js 16 / React 19, needs NEXT_PUBLIC_API_URL
```

Analysis scripts (`analysis/m0_bracket.py`, `analysis/m0_t5_t6.py`,
`ingest/m0_precision.py`) are M0 milestone artifacts, run ad hoc. They are the
record of how the published numbers were produced — don't rewrite them to match
new code; they document what was actually run.

## Architecture

Four processes over one Neon Postgres, separated by **database role**, not by
convention:

| Process | Role | Env var | Can it delete? |
|---|---|---|---|
| `ingest/collect.py` (GitHub Actions, every 5 min) | `headway_ingest` | `INGEST_DATABASE_URL` | No — no `UPDATE`/`DELETE` grant anywhere |
| `ingest/retain.py` (GitHub Actions, daily 04:17) | owner | `DATABASE_URL` | Yes — that is why it is a separate workflow |
| `api/` (Render, FastAPI) | `headway_app` | `APP_DATABASE_URL` | No — `SELECT` only, plus per-transaction `SET TRANSACTION READ ONLY` |
| `web/` (Next.js, Vercel) | — | `NEXT_PUBLIC_API_URL` | — |

Data flow: `/vehicles` (4s) and `/predictions` (30s) → **store-on-change** →
`predictions_register` + `vehicle_events` → `derive_arrivals()` brackets each
arrival → `arrivals` → the `matches` **view** joins them → `retain.py`
aggregates into `daily_metrics` → seals → prunes.

Things that are easy to get wrong here:

- **Store on change, not on observation.** `collect.py` keeps in-memory
  `veh_state`/`pred_state` and writes a row only when the observed state
  differs. This is what keeps 197 MB/day survivable, and it is also what turns
  the register into a revision history (needed for BQ-4). Never run two
  ingesters concurrently — each has its own memory and they would duplicate
  rows. The Actions workflow enforces this with a `concurrency` group.
- **`derive_arrivals()` is the only thing that fills `arrivals`.** If it stops
  running, the pipeline looks healthy while the match rate silently decays
  against a frozen table. This already happened once (36.5% against the
  measured 82.6%).
- **`matches` is a view, not a table** — a test asserts this. It cost 73 MB/day
  as a table and held nothing derivable.
- **Two-step schema.** `m0_setup.py` applies only `sql/schema.sql` (where
  `matches` is still a table). `sql/retention.sql` — which drops it, creates the
  `matches` view, `is_sampled()`, `daily_metrics` and `seals` — has no runner
  and must be applied by hand after setup.
- **An aggregate in `daily_metrics` can never shrink.** `UPSERT_DAILY` in
  `ingest/retain.py` carries `WHERE EXCLUDED.n >= daily_metrics.n`, and a test
  attempts the overwrite. After a day's full raw is pruned its 10% sample
  survives, so the day is still visible to the aggregator — without the guard it
  is recomputed from a tenth of the data and the permanent record is silently
  replaced (measured: n 1,592 → 210, median +7.5s → −14.5s, late flipping to
  early). Do not "fix" this by restricting aggregation to days whose raw
  survives: aggregation runs before pruning precisely so an outage-delayed run
  still writes complete aggregates for the days it is about to prune.
- **Progress toward the publication threshold is counted from `daily_metrics`,
  never from `count(*) FROM matches`.** `matches` is a view over raw that
  retention prunes, so counting it makes the gate drift down as data ages out
  instead of accumulating (12,625 present on 2026-08-21, of which 1,443 would
  survive the 2-day window). `/status` exposes the live figure separately as
  `matches_retained_now`, labelled as uncountable toward the threshold.
- **Retention order is aggregate → seal → prune, always.** Aggregating after
  pruning summarises data that is gone; pruning before sealing destroys the
  evidence the seal exists to protect. Seals are written to `seals/` and
  committed back to git by the workflow, because a digest held only in the
  database the owner controls proves nothing.
- **Coverage is recorded per run** (`coverage` table, NFR-5). A gap in ingestion
  is indistinguishable from punctual service unless coverage is published beside
  every figure. Scheduled Actions are throttled and delayed, so expect ~85–95%
  poll completion, not 100%.

## Invariants — do not change these to make code or numbers nicer

These come from [`PREREGISTRATION.md`](PREREGISTRATION.md), which was committed
before the data existed. Amendments are **appended as new numbered sections**,
never edits to what is above, and must be committed before the analysis they
affect runs.

- **Arrival is the bracket midpoint**, never the first `STOPPED_AT`. The first
  `STOPPED_AT` is the upper end of a ~20s bracket and manufactures ~10s of
  systematic lateness — it nearly produced a published false finding. (§1)
- **Horizons under 5 minutes are withdrawn permanently**, not caveated.
  `BUCKETS` in `ingest/retain.py` is `5-10 / 10-20 / 20-30` and a test guards
  the lower bound. No bucket boundary moves after data is seen. (§2)
- **Nothing publishes an error figure before 7 continuous days and 20,000
  matched predictions.** `REQUIRED_DAYS` / `REQUIRED_MATCHES` live in
  `api/main.py`; `/status` reports progress toward the threshold and serves the
  withheld figures as explanatory strings instead. A provisional number
  captioned "early" is how a stopping rule gets abandoned without anyone
  deciding to. (§7)
- **Primary window is bracket width ≤ 60s**, with both sensitivity analyses
  reported regardless of what they show. (§3)
- **`arrival_uncertainty` is not defined as a confidence interval** by GTFS-RT.
  What it empirically corresponds to is a finding, never evidence the agency is
  wrong against a standard it never claimed. Containment is a **lower bound**,
  because measurement noise biases it downward. (§4)
- **The 10% sample is a function** (`is_sampled()`, `md5(trip_id) % 10 = 0`), by
  trip, not a stored list — so it cannot be redrawn later to include a trip
  whose data turned out to be interesting. Sampling by trip rather than by row
  is what keeps revision chains complete. (§11)
- **The append-only grant is tested by attempting to violate it.**
  `m0_setup.py` §3 and `tests/test_headway.py` both connect as the ingest role
  and expect `InsufficientPrivilege`. A grant nobody has attacked is a comment,
  not a guarantee.

## Conventions

- **Tests skip rather than pass vacuously.** DB-backed tests are gated on
  `DATABASE_URL` / `INGEST_DATABASE_URL` being reachable. Keep that shape — a
  green tick that checked nothing is worse than a visible skip. CI passes the
  secrets on pushes; forked PRs skip.
- **Docstrings explain *why*, and record what broke.** Several carry the bug
  that motivated the code (the frozen `arrivals` table, the credential-rotation
  outage, pytest capture vs. stdout rebinding). Preserve that when editing;
  don't compress them into descriptions of what the code does.
- **Env lookup is process-env first, `.env` fallback**, duplicated in
  `collect.py`, `retain.py`, `api/db.py` and the tests so each entry point stays
  standalone. Files are read as `utf-8-sig` because Windows writes BOMs.
- **Scripts rebind stdout to UTF-8 only under `__main__`** (`_utf8_stdout()`).
  Doing it at import time breaks pytest's capture.
- **Never print or commit a credential.** `m0_setup.py` writes connection
  strings into `.env` and reports only that it did so.
- **The web layer fails loudly** when `NEXT_PUBLIC_API_URL` is missing — no
  localhost fallback, because a default of 127.0.0.1 makes a broken deployment
  look healthy on the developer's machine and nowhere else.
- `*.jsonl` is gitignored (raw stream dumps, ~7 MB per 20 min). Derived
  measurements are committed instead, so claims stay checkable without carrying
  the firehose in git.

## Reference documents

`Headway_SRS_v1.0.md` (requirements, BQ-* questions, NFR-*),
`Headway_M0_Spec.md` (the milestone and the kill criterion),
`Headway_M0_Summary.md` (every measurement, what broke, what was decided),
`PREREGISTRATION.md` (read §0 first — it states what the author had already seen
before writing it).
