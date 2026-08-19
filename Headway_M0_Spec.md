# Headway — M0 Specification

**Milestone:** M0 — Arrival-time precision and the walking skeleton
**Author:** Muhammad Haris Khokhar
**Date:** 2026-08-20
**Status:** Not started
**Depends on:** `Headway_SRS_v1.0.md`

---

## 1. The one question

> **Can the moment a train actually arrived be established precisely enough for
> the errors we intend to measure to mean anything?**

Everything else in Headway is engineering. This is the only thing that can kill
it, and it can kill it quietly — a coarse arrival timestamp does not produce an
error, it produces a **plausible wrong answer**: every prediction looks late, and
"trains run late" gets published as a finding about trains when it is a fact
about the observer.

The 35-minute feasibility run measured a median error of **+3s at the 0–2 minute
horizon**, rising to +42s at 10–20 minutes. That pattern is what a real effect
looks like and not what a fixed observation lag looks like. **It is evidence, not
proof.** M0 turns it into one or the other.

**No grading, no site, no analysis of accuracy happens in M0** beyond what is
needed to answer the question above and stand up the thinnest deployable
skeleton.

---

## 2. Scope

### In scope

- Streaming ingestion of predictions and vehicle events, with a durable cursor.
- The append-only register, with the grant tested by attempting to violate it.
- **Measuring arrival-time precision** — the only thing that matters here.
- Measuring the match rate under streaming, against the polled baseline of 86.7%.
- Measuring storage growth per hour to size the retention design.
- `PREREGISTRATION.md`, committed before any accuracy figure is computed.
- Walking skeleton: repo, CI, schema, one scheduled job, a deployed page showing
  match rate and coverage.

### Explicitly out of scope

Error-by-horizon as a published finding, containment, revision paths,
stratification, retention machinery, seals, styling, the memo. All belong to
M1 and later.

### Deliberate simplification

M0 ingests **three rapid-transit routes only** — the same Red, Orange and Blue
used in the feasibility run, so the numbers are directly comparable. Bus routes
have longer dwells and different failure modes and would change the question
being answered.

---

## 3. Unverified facts to be measured

| # | Fact | Why it matters |
|---|---|---|
| **VER-1** | **Arrival-time precision under streaming** | The kill question. §5 |
| **VER-2** | Match rate under streaming, against 86.7% polled | If streaming does not improve it, DC-1 was the wrong explanation and the misses are something else |
| **VER-3** | Rows per hour, and bytes per hour, in Postgres | Sizes the whole retention design. The 25,600 rows per 35 minutes is a count of API objects, not stored rows |
| **VER-4** | Share of predictions carrying `arrival_uncertainty` | The feasibility run found 10,145 of ~15,000 arrival predictions carried one. If it is sparse or route-dependent, BQ-2 narrows |
| **VER-5** | Unmatched predictions: what are they? | R-2. If misses concentrate on particular stops or dwell lengths, the sample is biased |

---

## 4. Tasks

### M0-T1 — Repository and CI

`Headway`, **public** — unlimited Actions minutes depend on it.

```
headway/
  ingest/          # streaming client, cursor, writers
  analysis/        # precision and match-rate measurement
  api/             # FastAPI, read-only role
  web/             # Next.js
  sql/             # schema.sql, grants.sql
  .github/workflows/
```

CI runs tests and the append-only assertion from M0-T3 on every push.

**Done when:** CI green on a clean clone, repository public.

---

### M0-T2 — Streaming ingestion

Consume the MBTA server-sent event stream for predictions and vehicles on the
three routes. Durable cursor. Automatic resume. **Every reconnect and every gap
is recorded** — NFR-5 exists because a silent gap looks exactly like a period of
punctual service.

Record the local receipt time alongside every event, separately from any
timestamp the feed supplies. The difference between those two is part of VER-1.

**Done when:** the stream runs for one continuous hour, and a deliberate kill
mid-run resumes without duplicating or losing events.

---

### M0-T3 — Schema and the append-only grant

Tables per SRS §8. The application role gets `INSERT` and `SELECT` on
`predictions_register` and **no `UPDATE`, no `DELETE`**.

Then the test that matters: **connect as that role and attempt both.** The
milestone fails if either succeeds. A grant nobody has tried to violate is not a
guarantee — this is the same test that caught nothing in Triage precisely because
it was written to be capable of catching something.

**Done when:** both attempts raise `InsufficientPrivilege` in CI.

---

### M0-T4 — Arrival-time precision  *(resolves VER-1 — the critical task)*

Three independent estimates of when a vehicle actually arrived, compared against
each other:

1. **First `STOPPED_AT`** for the (trip, stop), by feed timestamp.
2. **Last `IN_TRANSIT_TO` / `INCOMING_AT`** for that stop, by feed timestamp.
   The true arrival lies between (1) and (2); the width of that bracket is a
   direct measure of precision.
3. **Local receipt time** of the first `STOPPED_AT`, which bounds how much of the
   uncertainty is the feed's and how much is ours.

Publish the distribution of the bracket width, not just its median. **A median of
4 seconds with a tail reaching 90 is a different project from a uniform 4.**

Also measure the same bracket under the 30-second polling already collected, so
the improvement from streaming is quantified rather than claimed.

**Done when:** the bracket-width distribution is recorded, and the kill criterion
in §6 has been evaluated against it.

---

### M0-T5 — Match rate and what goes missing  *(VER-2, VER-5)*

Compute the match rate under streaming, on the same definitions as the
feasibility run so the two are comparable.

For the unmatched remainder, characterise them: which stops, which routes, which
hours, terminal or through, `ADDED` or scheduled. **The question is not how many
we lose but whether what we lose resembles what we keep.**

**Done when:** the streaming match rate is recorded next to the polled 86.7%, and
the unmatched set is described rather than counted.

---

### M0-T6 — Storage  *(VER-3)*

Measure rows and bytes per hour in Postgres, including indexes. Project to a
year. State plainly whether the raw stream can be retained, and if not, what the
aggregation-on-write design must be.

**Done when:** a projected annual figure exists and is compared against 0.5 GB.

---

### M0-T7 — Pre-registration  *(gate — blocks M0-T8)*

`PREREGISTRATION.md`, committed before any accuracy figure is computed:

1. The horizon buckets, fixed.
2. Error defined as actual minus predicted, positive meaning late.
3. Containment defined against the stated uncertainty, with no assumed
   confidence level (DC-4).
4. Bootstrap procedure: **resampled by trip**, not by prediction.
5. **The kill criterion from §6, as a number**, and what gets published if it fires.
6. A statement that no accuracy figure has been computed at time of commit.

The commit timestamp is the evidence. Nothing in M0-T8 begins until this is on
`main`.

---

### M0-T8 — Walking skeleton

The thinnest deployable path carrying only what M0 established:

- **Schema** in Neon, application role `SELECT` only on the read path.
- **API** on Render: one endpoint returning match rate, coverage and row counts.
- **Web** on Vercel: one page showing the match rate, the coverage record, the
  measured arrival-time precision, and the row counts behind them.
- SRS §7 notices present from the first deploy.

**No accuracy figures on this page.** They are not established yet, and shipping
them provisionally is the failure the whole project argues against.

**Done when:** the page is reachable and its numbers match the repository's.

---

### M0-T9 — Go / kill decision

`Headway_M0_Summary.md`: VER-1 to VER-5 as measured, what broke, decisions taken,
the kill evaluation in writing, and whether M1 proceeds.

---

## 5. Why precision is the kill question

The error being measured at short horizons has a **median absolute value of
about 7 seconds**. If the arrival timestamp is itself uncertain by 20 or 30
seconds, that measurement is noise wearing a decimal point.

The danger is not that the analysis fails. It is that it **succeeds and is
wrong**: a fixed observation lag adds the same positive offset to every error,
which reads as "trains are systematically late" — a plausible, publishable,
entirely false finding.

The feasibility run gives real grounds for optimism, because a fixed lag would
inflate short and long horizons equally and the measured bias instead **grows**
with horizon. But "grounds for optimism" is not a measurement, and it is exactly
the kind of reasoning that feels sufficient until someone checks.

---

## 6. Kill criterion

Committed as a number in `PREREGISTRATION.md` before any accuracy figure exists.

Let **W** be the median bracket width from M0-T4 — the gap between the last
observation showing a vehicle approaching and the first showing it stopped.

| Measured W | Consequence |
|---|---|
| **≤ 10s** | Proceed in full. All horizon buckets supported |
| **10–60s** | Proceed, but **no claim about horizons under five minutes**. Those buckets are withdrawn and the site says why |
| **> 60s** | **M1 does not start.** Publish the negative result: this data cannot answer the question at the resolution the question requires, with the measurement and an account of why |

The middle row is the likely one, and writing it down now is the point. Deciding
after seeing the number which horizons to trust is precisely the failure this
document exists to prevent.

---

## 7. What M0 must not become

- **An accuracy report.** Not one error figure is published until precision is
  established. The temptation will be strong: the feasibility run already
  produced a beautiful monotonic curve, and it may well be right. It is not
  established.
- **A tuning exercise.** No adjusting the arrival definition until the numbers
  look better. The definition is fixed in M0-T7 and the measurement is what it is.
- **A second agency.** One operator measured properly.
- **A styling exercise.** One page, four numbers.

---

## 8. Estimated effort

| Task | Estimate |
|---|---|
| M0-T1 Repository and CI | 0.5 day |
| M0-T2 Streaming ingestion | 2 days |
| M0-T3 Schema and grant | 0.5 day |
| M0-T4 **Precision** | 1.5 days |
| M0-T5 Match rate and misses | 1 day |
| M0-T6 Storage | 0.5 day |
| M0-T7 Pre-registration | 0.5 day |
| M0-T8 Walking skeleton | 1.5 days |
| M0-T9 Summary and decision | 0.5 day |
| **Total** | **~8.5 days** |

**M0-T4 answers the kill question and can be done before the skeleton exists.**
If the answer is bad, T8 is never built.
