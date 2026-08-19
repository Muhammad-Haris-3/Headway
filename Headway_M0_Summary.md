# Headway — M0 Summary: arrival-time precision

**Milestone:** M0 — Arrival-time precision and the walking skeleton
**Author:** Muhammad Haris Khokhar
**Date:** 2026-08-20
**Status:** **Partial.** The kill question is answered. Remaining tasks not started.
**Depends on:** `Headway_SRS_v1.0.md`, `Headway_M0_Spec.md`

---

## 1. Exit criterion

M0 asked one question:

> **Can the moment a train actually arrived be established precisely enough for
> the errors we intend to measure to mean anything?**

**Answer: partly — and not at short horizons.**

| | Measured |
|---|---|
| Median bracket width, feed clock | **20.0s** |
| Pre-registered band | 10–60s |
| **Verdict** | **Proceed, but withdraw every horizon under five minutes** |

The middle row of the criterion in `Headway_M0_Spec.md` §6 fires. That was the
outcome named as most likely before any data was collected, and it is the reason
the criterion had three bands rather than a pass/fail.

---

## 2. What was done

| Task | Status |
|---|---|
| M0-T1 Repository and CI | **Not started** |
| M0-T2 Streaming ingestion | **Superseded** — streaming is unavailable; see §4.1 |
| M0-T3 Schema and append-only grant | **Done.** Grant tested by attempted violation; see §3.4 |
| **M0-T4 Arrival-time precision** | **Done.** The task the milestone exists for |
| M0-T5 Match rate and misses | **Done** — 82.6% in-window; see §3.5 |
| M0-T6 Storage | **Done** — does **not** fit raw; see §3.6 |
| M0-T7 Pre-registration | **Done**, but written after the pilot — see §5.1 and `PREREGISTRATION.md` §0 |
| M0-T8 Walking skeleton | Not started |
| M0-T9 Decision | This document |

M0-T4 was taken first deliberately: the spec ordered it before the skeleton so a
bad answer would stop the build. It did not stop it, but it changed it.

Code: `ingest/m0_precision.py`, `analysis/m0_bracket.py`.

---

## 3. Verification performed

### 3.1 Collection

| | |
|---|---|
| Window | 30.0 minutes |
| Routes | Red, Orange, Blue (rapid transit) |
| Vehicle observations | **22,083** across 433 polls |
| Actual cadence | **4.2s** (designed 4.0s) |
| Status mix | 9,807 `STOPPED_AT`, 7,725 `INCOMING_AT`, 4,551 `IN_TRANSIT_TO` |
| Bracketable arrivals | **595** |
| API key | None. 20 requests/min, confirmed from `x-ratelimit-limit` |

### 3.2 The bracket, on two clocks

Each arrival is bracketed between the last observation showing the vehicle not
yet stopped and the first showing it stopped. The true arrival lies inside.

| Clock | Median | Mean | p25 | p75 | p90 | p99 | Max | ≤10s | ≤60s |
|---|---|---|---|---|---|---|---|---|---|
| **Feed (`updated_at`)** | **20.0s** | 24.3s | 12s | 32s | 44s | 145s | 148s | 18% | 97% |
| **Ours (poll time)** | **4.0s** | 4.3s | 4s | 4s | 5s | 7s | 18s | 99% | 100% |

**Converged.** The feed median read 19.0s at 349 and 397 arrivals, then 20.0s at
491 and again at the full 595. It moved by one second as the sample grew by 70%
and then stopped moving. It is not a sampling fluctuation.

### 3.4 The append-only guarantee, tested rather than asserted

`ingest/m0_setup.py` creates the roles, applies the grants, then **connects as
each role and attempts to violate them**. All six attempts behaved:

| Role | Attempt | Result |
|---|---|---|
| `headway_ingest` | INSERT into the register | permitted |
| `headway_ingest` | **UPDATE the register** | **refused** |
| `headway_ingest` | **DELETE from the register** | **refused** |
| `headway_app` | SELECT | permitted |
| `headway_app` | INSERT | refused |
| `headway_app` | DELETE | refused |

Each refusal is `InsufficientPrivilege`, raised by PostgreSQL rather than caught
by application code. A success on any of the four denied attempts exits non-zero
and fails the milestone.

This matters because the project's entire claim is that a prediction was
recorded before its outcome existed. That is worth precisely what the guarantee
against later editing is worth, and a grant nobody has tried to break is a
comment rather than a guarantee.

The test row inserted by the ingest role is deliberately left in place. The owner
could remove it; the ingest role cannot, which is the simplest standing
demonstration of the property.

### 3.3 What the gap between the two clocks means

Our polling is tight — 4.2s, and 99% of our own brackets close within 10s. The
feed's timestamps are four to five times coarser.

**We are polling roughly five times faster than the MBTA's vehicle records
actually change.** The same `updated_at` is returned across several consecutive
polls.

**Therefore precision is a property of the source, not of the method.** This is
the load-bearing conclusion of M0:

- An **API key** would not help. It raises the request limit, not the feed's
  refresh rate.
- **Streaming** would not help meaningfully. It would remove our own ~4s
  sampling error and leave the feed's ~20s untouched.
- **Polling harder** is already past the point of returning anything.

No engineering effort available to this project improves the number.

### 3.5 Match rate under 4-second polling, and the midpoint estimator

21.9 minutes of store-on-change ingestion through the `headway_ingest` role:
9,139 predictions and 2,313 vehicle events stored, 423 arrivals bracketed,
4,750 matched predictions.

| | |
|---|---|
| Match rate, in-window | **82.6%** (390 of 472) |
| Baseline at 30s polling, same restriction | 86.7% |

Slightly **worse** than the slower polling, not better. Store-on-change discards
observations that were byte-identical to the previous one, and a few of those
were the ones needed to close a bracket. Four points is an acceptable price for
the storage it saves, but it is a price, and it is recorded as one rather than
presented as a free optimisation.

**The midpoint estimator confirms §4.2 emphatically.** Same data, two estimators:

| Horizon | First `STOPPED_AT` (biased) | Midpoint (pre-registered) |
|---|---|---|
| 5–10 min | +28s | **+6s** |
| 10–20 min | +42s | **+13s** |

The systematic lateness shrinks by roughly three quarters. What survives is real
but small; what was published in the feasibility run was mostly the observer.
This is the M0-T4 prediction, measured rather than argued.

### 3.6 Storage: it does not fit, and the reason is not the table I expected

| Table | Size |
|---|---|
| `predictions_register` | 1,320 KB |
| `matches` | 1,104 KB |
| `vehicle_events` | 440 KB |
| `arrivals` | 184 KB |
| **Measured growth** | **197 MB/day** |

**0.5 GB is exhausted in 2.6 days.** A year of raw would need 70 GB.

Two expectations were wrong:

**Store-on-change barely helps predictions.** Vehicles compressed 6.9×, but
predictions only **1.8×** — because a prediction genuinely changes on almost
every poll. The estimated arrival ticks down as the train approaches, so
"unchanged" is rare. The compression that made vehicles cheap does not transfer.

**`vehicle_events` is not the problem.** It is **14%** of bytes. The retention
policy has to target `predictions_register` and `matches`, which is the opposite
of what DC-5 assumed.

**What actually fits:** the raw register is prunable once graded, and `matches`
is prunable once aggregated. Daily aggregates by horizon, route and hour are a
few hundred rows a day and can be kept forever. The durable record is the
scorecard, not the stream that produced it — which is the GridCast retention
pattern arrived at from the opposite direction.

---

## 4. Problems found

### 4.1 The streaming endpoint does not work, and the SRS assumed it did

`Accept: text/event-stream` returns **HTTP 406 `not_acceptable`** on `/vehicles`
and `/predictions`, with and without filters. It presumably requires an API key.

SRS §5 named streaming as the fix for DC-1 (short dwells missed by polling) and
M0-T2 was written around it. **That plan was wrong.**

The recovery came from a header rather than a workaround: `x-ratelimit-limit: 20`
permits a request every three seconds without any key, so vehicles are polled at
4s and predictions at 30s — 17 requests/min of the 20 allowed. That is 7× finer
than the 30-second feasibility run.

And it turned out not to matter, because §3.3 shows the binding constraint was
never our cadence.

### 4.2 The finding that would have been published was substantially an artifact

The feasibility run produced a clean monotonic result: median error **+3s, +13s,
+28s, +42s** by horizon. Trains run systematically late, worse the further ahead
you look. Plausible, tidy, and the kind of thing that goes in a headline.

**Taking arrival as the first `STOPPED_AT` observation takes the upper end of a
20-second bracket.** If the true arrival falls anywhere inside that window, this
overstates arrival time — by roughly **9–10 seconds on average** if arrivals are
uniform within the bracket.

Applying that correction:

| Horizon | As measured | Roughly corrected |
|---|---|---|
| 0–2 min | +3s | **≈ −7s** |
| 2–5 min | +13s | ≈ +3s |
| 5–10 min | +28s | ≈ +18s |
| 10–20 min | +42s | ≈ +32s |

**At the shortest horizon the finding does not merely shrink — it may reverse.**

This is exactly the failure `Headway_M0_Spec.md` §5 described: not an error, a
**plausible wrong answer**. A fixed observation lag adds the same positive offset
to every prediction and reads as a fact about trains. It would have been
published, and it would have been about the observer.

The correction above is arithmetic on an assumption of uniformity, not a
measurement. It is stated to show the size of the problem, not as a result.

### 4.3 Long dwells produce a heavy tail

The bracket median is 20s but the tail runs to **148s** (p99 = 88s). Terminals,
held trains and layovers keep a vehicle stopped long enough that neighbouring
observations spread apart.

A median alone would have hidden this, which is why M0-T4 required the
distribution. Arrivals with wide brackets carry more measurement noise and must
be weighted or excluded explicitly — not averaged in silently.

---

## 5. Decisions taken

### 5.1 Pre-registration was weaker than the spec required, and this is a real gap

M0-T7 required `PREREGISTRATION.md` committed **before** any figure was computed.
That file does not exist.

What is true: the kill criterion was written as three numbered bands in
`Headway_M0_Spec.md` §6, and that document was written and saved **before the
collector was written or run**. The bar was set before the result was known.

What is **not** true: that this is independently evidenced. **No git repository
existed during M0**, so there are no timestamps anyone else can check. The
ordering rests on my word.

That is a weaker claim than this project is supposed to make, and it is recorded
here rather than glossed. The repository is initialised before M1, the planning
documents are committed before any analysis output, and every subsequent
measurement lands as it happens.

### 5.2 Arrival becomes the midpoint of the bracket

Using the first `STOPPED_AT` is a biased estimator (§4.2). From M1, arrival is
the **midpoint** of `[last not-stopped, first stopped]`, which removes most of the
systematic offset and leaves roughly ±10s of symmetric noise.

Symmetric noise widens intervals. Systematic offset invents findings. The trade
is not close.

### 5.3 Horizons under five minutes are withdrawn

Per §6 of the spec, at 10–60s precision no claim is made about horizons under
five minutes. Their true errors — corrected medians of about −7s and +3s — are
**smaller than the measurement uncertainty**.

Withdrawn, not caveated. The site will not display them.

### 5.4 The streaming requirement is dropped from the SRS

DC-1's fix was wrong. Polling at 4s is already finer than the feed refreshes.

---

## 6. What this means for the project

**It survives, smaller and more honest.**

Still supported:

- **BQ-2, the headline** — containment of the agency's own stated uncertainty.
  The feasibility estimate of 84% concerns a window of roughly ±120s, an order of
  magnitude wider than 20s of measurement noise. Unaffected.
- **BQ-1 at horizons of five minutes and beyond**, where errors of 18–32s exceed
  the noise floor.
- **BQ-3, bias** — but only against the midpoint estimator, and reported with the
  ±9.5s explicitly.
- **BQ-4, revision paths** — these compare predictions to each other, not to an
  arrival, and never touch the precision problem at all.

Withdrawn:

- Every horizon under five minutes.
- The "trains run systematically late" claim in its original form.

**The best finding was never at risk.** Containment lives on a scale where 20s of
noise does not matter, and it remains the thing nobody has published.

---

## 7. Next

M1 does **not** begin with ingestion. It begins with:

1. `git init`, planning documents committed **first**, before any analysis output.
2. `PREREGISTRATION.md`, properly, with the midpoint estimator and the withdrawn
   horizons written down before anything is measured against them.
3. SRS amended: streaming removed, precision recorded as a source property,
   midpoint estimator adopted.

Then M0-T3, T5, T6 and T8, which remain undone.

---

## 8. Document control

| Version | Date | Change |
|---|---|---|
| 1.2 | 2026-08-20 | Figures finalised on the complete 30-minute run (n 491 -> 595). W stays 20.0s. Same band, same verdict. |
| 1.1 | 2026-08-20 | Figures updated mid-run (W 19.0s -> 20.0s, n 397 -> 491). |
| 1.0 | 2026-08-20 | M0-T4 complete. Kill criterion evaluated: middle band. Remaining tasks not started. |
