# Headway — Software Requirements Specification v1.0

**Project:** Headway — keeping score on published arrival predictions
**Author:** Muhammad Haris Khokhar
**Date:** 2026-08-20
**Status:** Approved for M0

---

## 1. Introduction

### 1.1 Purpose

Transit agencies broadcast millions of arrival predictions a day. Millions of
people act on them. **Nobody keeps score.**

Headway records those predictions **before the outcome exists**, observes what
actually happened, and publishes a continuously maintained account of how wrong
they were — by how far ahead the prediction was made, by station, by time of day.

The MBTA also publishes, alongside each prediction, **its own uncertainty
figure**. Headway's central question is therefore not only *"how wrong are the
predictions"* but *"is the agency's own stated error honest?"*

### 1.2 What makes this different from Bellwether and GridCast

In both of those, the author is the forecaster: a model predicts, and the system
grades itself.

**Headway forecasts nothing.** It is the referee, not the player. The subject is
someone else's published, timestamped claims, and the deliverable is a scorecard
on them. The engineering discipline carries over; the posture does not.

One practical consequence: **ground truth arrives in minutes, not days.**
GridCast waits 48 hours for an outcome and Bellwether waits seven days. Headway
observes an arrival within minutes of the prediction it grades, so evidence
accumulates thousands of times faster while time still compounds the record.

### 1.3 Scope

**In scope:** continuous ingestion of MBTA rapid-transit predictions and vehicle
positions; an append-only register of predictions as issued; observation of
actual arrivals; matching; error measurement by horizon; calibration of the
agency's published uncertainty; a public site; a decision memo.

**Out of scope:** producing a competing arrival prediction; any claim about other
agencies; advice to travellers about specific journeys; real-time alerting;
anything requiring paid infrastructure.

### 1.4 Definitions

| Term | Meaning |
|---|---|
| **Prediction** | One published claim: trip T will arrive at stop S at time A, with stated uncertainty U |
| **Horizon** | Predicted arrival minus the time the prediction was recorded. How far ahead it was made |
| **Actual arrival** | The observed moment a vehicle on trip T was at stop S |
| **Match** | A prediction joined to the actual arrival for the same (trip, stop) |
| **Match rate** | Share of predicted (trip, stop) pairs for which an actual was observed |
| **Error** | Actual minus predicted. Positive means the vehicle arrived **late** |
| **Containment** | Share of actuals falling inside the agency's own stated uncertainty |
| **Dwell** | How long a vehicle remains stopped. Short dwells are how observations get missed |

### 1.5 Intended audience

Hiring managers and technical reviewers primarily. Sections 2, 3 and the decision
memo are written for a reader with no statistical background; sections 6 onward
are written so an independent party can reproduce every number.

---

## 2. Business context and problem statement

### 2.1 Context

A departure board says four minutes. A phone says six. Somebody decides whether
to run. That decision is made hundreds of millions of times a day worldwide, on
numbers whose accuracy has never been published by anyone.

Agencies do publish accuracy figures for *service* — on-time performance against
schedule. That is a different question. **Nobody publishes how accurate the
real-time predictions themselves are**, and the agency's own uncertainty field is
broadcast without any account of what it empirically means.

### 2.2 Problem statement

> Millions of people act on predictions that nobody has ever scored, accompanied
> by an error bar that nobody has ever checked.

### 2.3 Primary questions

| # | Question | Method |
|---|---|---|
| BQ-1 | How large is the error, and how does it grow with horizon? | Descriptive, on matched pairs |
| BQ-2 | **When the agency states an uncertainty, how often is it right?** | Containment, the headline |
| BQ-3 | Are predictions biased, or merely noisy? | Sign of the error distribution |
| BQ-4 | Do predictions converge honestly, or snap to reality at the last moment? | Revision paths per (trip, stop) |
| BQ-5 | Does accuracy vary by station, line, or time of day? | Stratified, once volume allows |

### 2.4 Success criteria

| # | Criterion | Threshold |
|---|---|---|
| SC-1 | Match rate in steady state | ≥ 85%, published continuously, not assumed |
| SC-2 | **Arrival-timestamp precision** | Materially finer than the errors being measured — see §3.1 |
| SC-3 | Append-only register | Predictions cannot be altered after issue; enforced by grant, not convention |
| SC-4 | Containment measured with an interval | BQ-2 answered with uncertainty, not a bare percentage |
| SC-5 | Cost | Zero. Free tiers only |
| SC-6 | Legibility | A non-technical reader can state the finding from the memo alone |

---

## 3. Feasibility study

Measured on 2026-08-20 over a 35-minute window, three rapid-transit routes:

| Factor | Measured |
|---|---|
| Prediction snapshots | **25,600** in 35 minutes |
| Vehicle observations | **3,246** |
| Distinct predicted (trip, stop) pairs | 924 |
| Observed arrivals | 690 |
| **Match rate, in-window** | **86.7%** (639 of 737) |
| Rows with no `arrival_time` | 41% — terminal departures |
| API access | Open, JSON, **no key required** at low rate |
| Cost | Zero |

Error already visible, by horizon — median, positive means late:

| Horizon | n | Median | Within 60s |
|---|---|---|---|
| 0–2 min | 2,359 | +3s | 91% |
| 2–5 min | 3,174 | +13s | 80% |
| 5–10 min | 4,470 | +28s | 64% |
| 10–20 min | 142 | +42s | 53% |

And a first estimate of the headline: **actual arrivals fell inside the agency's
stated uncertainty 84% of the time** (8,504 of 10,145).

### 3.1 Principal risk to validity

**The arrival timestamp may not be precise enough to support the finding.**

Actual arrival is taken from the first observation showing a vehicle stopped at
the stop. If that timestamp lags reality by tens of seconds, **every error is
biased positive** — and "trains run late" would be an artifact of the
measurement rather than a fact about trains.

The feasibility numbers are reassuring but not conclusive. At the 0–2 minute
horizon the median error is **+3s**; a systematic 30-second observation lag
would have pushed even short-horizon errors to roughly +15s. That the bias grows
with horizon rather than sitting flat is what one expects from a real effect.

**This is not proof, and M0 treats it as the question that can kill the project.**
If arrival times cannot be established to materially better than the errors being
measured, the short-horizon findings are noise and must be withdrawn — the
long-horizon findings would survive, and the project would shrink accordingly.

### 3.2 Second risk: unmatched arrivals are not a random sample

13% of predictions went unmatched. If the misses are concentrated on short dwells,
express patterns, or terminals, the surviving sample is not representative and
every published figure inherits that bias.

**The match rate must be published continuously and broken down**, never quoted
once and forgotten.

### 3.3 Third risk: this describes one agency

Every finding is about the MBTA. Nothing here generalises to any other operator,
and the site must say so wherever a figure appears.

---

## 4. Methodology

Incremental milestones, each with a spec before and a summary after, matching
OrderLens, GridCast, Bellwether and Triage.

**Definition of Done**, every milestone:

1. Requirements met or deferred with a written reason.
2. Tests pass in CI on a clean clone.
3. Every published number reproducible from committed inputs.
4. A summary recording what was built, verified, broken and decided.
5. Nothing asserted that was not measured.

---

## 5. Data source specification

**MBTA API v3**, `https://api-v3.mbta.com`. JSON. Free. A free key raises the
rate limit and will be used.

| Endpoint | Supplies |
|---|---|
| `/predictions` | `arrival_time`, `departure_time`, `arrival_uncertainty`, `stop_sequence`, `schedule_relationship`, `update_type`, and relationships to trip, stop, route, vehicle |
| `/vehicles` | `current_status`, `current_stop_sequence`, `updated_at`, position, and relationships to trip, stop, route |
| **Streaming** | Server-sent events on the same resources — pushes each state change instead of sampling |

### 5.1 Characteristics requiring handling

| # | Characteristic | Handling |
|---|---|---|
| DC-1 | **Short dwells are missed by polling.** Measured statuses: 1,477 stopped, 1,124 incoming, 645 in transit | Move to the streaming endpoint. M0 measures the improvement rather than assuming it |
| DC-2 | **41% of prediction rows carry no `arrival_time`** — terminals publish departures only | Departure predictions handled as a separate, clearly labelled series. Never silently mixed with arrivals |
| DC-3 | `schedule_relationship: ADDED` — trips appear that were not scheduled | Recorded and analysed separately; they are legitimate predictions and excluding them would be selection |
| DC-4 | `arrival_uncertainty` is not rigorously defined as a confidence interval in the GTFS-RT specification | **Its empirical meaning is a finding, not an assumption.** No claim that it "should" be 95% |
| DC-5 | Volume: ~1M rows/day on three routes against a 0.5 GB tier | Aggregation on write, raw retention window, monthly seals before pruning — the GridCast pattern |
| DC-6 | Trips are cancelled, rerouted, and skip stops | A prediction with no possible arrival is `unmatchable`, recorded as such, and excluded from error but **counted in the match rate** |

---

## 6. Functional requirements

### 6.1 Ingestion and the register

| # | Requirement |
|---|---|
| FR-1 | Consume the streaming endpoint for predictions and vehicles, with a durable cursor and automatic resume |
| FR-2 | Write every prediction to an **append-only** register, stamped with the time it was received |
| FR-3 | The application role holds no `UPDATE` or `DELETE` on the register — enforced by database grant, and tested by attempting both |
| FR-4 | Record vehicle state transitions sufficient to establish arrival times |
| FR-5 | Never discard a prediction because it later proved unmatchable |

### 6.2 Matching and grading

| # | Requirement |
|---|---|
| FR-6 | Join predictions to observed arrivals on (trip, stop) |
| FR-7 | Classify every prediction as matched, unmatchable, or pending |
| FR-8 | Publish the match rate continuously, broken down by route, stop and hour |
| FR-9 | Compute error by horizon bucket, reporting median, mean and absolute median |
| FR-10 | Compute containment against the stated uncertainty, **with an interval** |
| FR-11 | Retain each prediction's revision path so BQ-4 can be answered |

### 6.3 Publication

| # | Requirement |
|---|---|
| FR-12 | Public site: headline error curve, containment, match rate, and a station view |
| FR-13 | Every figure carries its sample size and the window it covers |
| FR-14 | State on every page that this describes the MBTA and no other operator |
| FR-15 | `METHODS.md`, `PREREGISTRATION.md`, and a two-page decision memo |

---

## 7. Non-functional requirements

| # | Requirement |
|---|---|
| NFR-1 | Zero cost. Neon, Render, Vercel, GitHub Actions free tiers |
| NFR-2 | Unattended operation with resume after failure; gaps recorded, never interpolated |
| NFR-3 | Every published number reproducible from committed inputs and a pinned seed |
| NFR-4 | Storage stays inside 0.5 GB indefinitely, by design not by rescue |
| NFR-5 | **Coverage is published.** Hours where ingestion was down appear as gaps, never as absence of delay |
| NFR-6 | No claim about the arrival-time precision that has not been measured (§3.1) |
| NFR-7 | Public repository |
| NFR-8 | The site never advises anyone whether to run for a train |

---

## 8. Architecture

```
MBTA streaming API
        |
        v
Ingestor (Python, long-running)  --->  PostgreSQL (Neon)
   durable cursor, resume               predictions_register  (append-only)
                                        vehicle_events
                                        arrivals
        |                               matches
        v                               metrics_by_horizon
Grader (scheduled)  ------------------> coverage
                                              |
                                              v
                                     FastAPI (Render) --> Next.js (Vercel)
```

The register is append-only and the grader writes only to derived tables. A
prediction, once recorded, is never touched again — which is the entire basis of
the claim that it was recorded before the outcome existed.

### 8.1 Decisions and rejected alternatives

| Decision | Chosen | Rejected | Reason |
|---|---|---|---|
| Feed | Streaming SSE | 30s polling | DC-1: polling loses short dwells and blurs arrival times |
| Ground truth | Observed vehicle state | Agency's own arrival record | The point is independent observation |
| Retention | Aggregate on write, prune raw, seal monthly | Keep everything | 0.5 GB against ~1M rows/day |
| Scope | MBTA rapid transit | Multiple agencies | One operator measured properly beats four measured loosely |

---

## 9. Analysis plan

1. Establish arrival-time precision (§3.1). Everything downstream is conditional on it.
2. Match rate, published with its breakdown.
3. Error by horizon, with intervals.
4. Containment of the stated uncertainty, with an interval.
5. Bias: is the error distribution centred on zero?
6. Revision paths: honest convergence or last-moment snap.
7. Stratification by station, line and hour, once volume supports it.

**Bootstrap intervals throughout, resampled by trip** — errors within a trip are
correlated, and resampling individual predictions would understate every interval.

---

## 10. Milestone plan

| # | Milestone | Exit criterion |
|---|---|---|
| **M0** | Precision and the walking skeleton | Arrival-time precision measured; match rate under streaming measured; register append-only and tested; one number deployed. **Kill point** |
| M1 | Continuous ingestion | Runs unattended for seven days with coverage published |
| M2 | Grading | Match, classify, error by horizon, all tested |
| M3 | Containment | BQ-2 answered with an interval |
| M4 | Retention and seals | Storage provably bounded; monthly seals committed |
| M5 | Stratification | BQ-5, once volume allows |
| M6 | Site | FR-12 to FR-14 live |
| M7 | Memo | Decision memo and write-up |

---

## 11. Risks

| # | Risk | Mitigation |
|---|---|---|
| R-1 | **Arrival timestamps too coarse** | §3.1. Measured in M0 as the kill question |
| R-2 | Unmatched arrivals are systematically different | Match rate published and broken down (FR-8); a drop is a finding |
| R-3 | Storage exceeds the free tier | DC-5 designed in from M0 |
| R-4 | Ingestion gaps read as "no delay" | NFR-5: coverage published alongside every figure |
| R-5 | Uncertainty field misread as a 95% interval | DC-4: its meaning is measured, never assumed |
| R-6 | Read as an attack on the agency | It is a scorecard, not an accusation. They publish more than most operators do, which is the only reason this is possible — and the site says so |
| R-7 | The agency turns out to be well calibrated | A legitimate finding, pre-registered as such |

### 11.1 Kill criterion

**If arrival timestamps cannot be established to materially better precision than
the errors being measured, the short-horizon findings are withdrawn.**

Stated as a number in `PREREGISTRATION.md` before M0 analysis begins: if the
measured arrival-time precision is coarser than **10 seconds**, no claim is made
about horizons under five minutes. If it is coarser than **60 seconds**, the
project does not proceed, and what is published is the negative result: that this
data cannot support the question, and why.

---

## 12. Acceptance criteria

| # | Criterion |
|---|---|
| AC-1 | Every FR met or deferred with a written reason |
| AC-2 | SC-1 to SC-6 met, or §11.1 executed |
| AC-3 | Append-only grant tested by attempting `UPDATE` and `DELETE` |
| AC-4 | Match rate and coverage published continuously |
| AC-5 | `PREREGISTRATION.md` committed before the first grading run |
| AC-6 | Memo readable by a non-technical reader |
| AC-7 | Storage inside 0.5 GB with the mechanism documented |

---

## 13. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-20 | Initial specification, grounded in the 35-minute feasibility measurement. |
