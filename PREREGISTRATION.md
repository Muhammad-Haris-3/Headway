# Headway — Pre-registration

**Committed:** 2026-08-20, before any full-scale measurement
**Fixes:** definitions, estimators, thresholds and publication rules for M1 onward
**Author:** Muhammad Haris Khokhar

---

## 0. What I have already seen, stated first

`Headway_M0_Spec.md` §M0-T7 required this document to declare that **no accuracy
figure had been computed**. That is no longer true, and writing it would be
false.

A pre-registration written after seeing pilot data is a weaker instrument than
one written blind. It is not worthless — but a reader can only judge how much it
is worth if they know exactly what I had already seen. So:

**From a 35-minute feasibility run (2026-08-20):**

| | |
|---|---|
| In-window match rate | 86.7% (639 of 737) |
| Median error, 0–2 min horizon | +3s |
| Median error, 2–5 min | +13s |
| Median error, 5–10 min | +28s |
| Median error, 10–20 min | +42s |
| **Containment of the agency's stated uncertainty** | **84%** (8,504 of 10,145) |

**From the M0-T4 precision run (24.3 minutes, 491 bracketed arrivals):**

| | |
|---|---|
| Median bracket width, feed clock | **20.0s** (p90 44s, max 148s) |
| Median bracket width, our poll clock | 4.0s |

So I already know the approximate size and direction of every headline. I know
containment is near 84% and not near 50% or 99%. I know errors grow with horizon.

**What this document can therefore still protect against** is choosing, after
seeing the full-scale numbers, which horizons to trust, which estimator to use,
which arrivals to exclude, and what counts as a finding. Those choices are made
here, in advance, and they are the choices with the most freedom to flatter.

**What it cannot claim** is that the analyst was blind. I was not.

---

## 1. Definitions, fixed

**Prediction.** One published claim recorded from `/predictions`: trip *T* will
arrive at stop *S* at time *A*, with stated uncertainty *U*, observed by us at
time *R*.

**Horizon.** *A − R*. How far ahead the prediction was made.

**Actual arrival.** The **midpoint** of the bracket
`[last observation showing the vehicle not stopped at S, first showing it stopped at S]`,
on the feed's `updated_at` clock.

> Not the first `STOPPED_AT`. That is the upper end of a ~20s bracket and
> overstates arrival by roughly 10s, which manufactures a systematic lateness
> that is a fact about the observer (M0 Summary §4.2). Symmetric noise widens
> intervals; systematic offset invents findings.

**Error.** *actual − predicted*. **Positive means the vehicle arrived late.**

**Match.** A prediction joined to an actual arrival on `(trip, stop)`.

**Unmatchable.** A prediction for which no arrival can exist — cancelled trip,
skipped stop. Counted in the match rate, excluded from error.

---

## 2. Horizon buckets, fixed

| Bucket | Reported? |
|---|---|
| 0–2 min | **No — withdrawn** |
| 2–5 min | **No — withdrawn** |
| 5–10 min | Yes |
| 10–20 min | Yes |
| 20–30 min | Yes |
| > 30 min | Yes, if n ≥ 500 |

Buckets under five minutes are withdrawn under the M0 §6 middle band: their true
errors are smaller than the 20s measurement noise. **They will not be displayed,
not even with a caveat.** No bucket boundary moves after data is seen.

---

## 3. Which arrivals enter the analysis

**Primary:** every matched prediction whose arrival bracket is **≤ 60s** — 97% of
bracketed arrivals in the M0 sample.

**Sensitivity, both reported regardless of what they show:**

- All bracketed arrivals, no width limit.
- Bracket ≤ 30s only.

If the primary and sensitivity results disagree materially, **all three are
published** and the disagreement is the finding. The primary is not selected
because it is the friendliest.

---

## 4. Containment — the headline

**Containment** = the share of matched predictions carrying a stated uncertainty
*U* for which `|error| ≤ U`.

Three things fixed now:

**No confidence level is assumed.** GTFS-RT does not define `arrival_uncertainty`
as a 68%, 95% or any-percent interval. Whatever number comes out is *what the
field empirically corresponds to* — never evidence that the agency is wrong
against a standard it never claimed.

**Measurement noise biases containment downward.** ±10s of arrival noise pushes
some genuinely-inside predictions outside. **The measured figure is therefore a
lower bound**, and will be reported as one. I commit to this direction now,
before seeing whether the full-scale number is higher or lower than 84%.

**Reported with an interval**, never as a bare percentage.

---

## 5. Uncertainty quantification

**Bootstrap, 2,000 resamples, resampled by trip — not by prediction.**

A single trip contributes many predictions for many stops and their errors are
correlated. Resampling predictions independently would treat correlated
observations as independent and understate every interval.

Percentile method, 2.5th and 97.5th.

---

## 6. What gets published, in each direction

Declared now so that no result can be framed after the fact:

| Outcome | Published as |
|---|---|
| Containment materially below the stated uncertainty's apparent intent | "The published error bar is optimistic by X points" — with the lower-bound caveat from §4 |
| Containment high (≥ 90%) | **"The MBTA's published uncertainty is honest."** A positive result about a public agency, published as readily as a critical one |
| Match rate falls below 80% in steady state | Published as a limitation on the front page, and the unmatched set characterised before any error figure is quoted |
| Errors show no growth with horizon | Published. It would contradict the pilot, and the pilot would be the thing that was wrong |

**There is no outcome of this study that goes unpublished.**

---

## 7. Stopping rules

- **Minimum before any error figure is published:** 7 continuous days of
  ingestion and ≥ 20,000 matched predictions.
- **Minimum before containment is published:** ≥ 20,000 matched predictions
  carrying a stated uncertainty.
- Collection does not stop when the number looks good. The site publishes a
  rolling window and the full record, both.

---

## 8. What is not being tested

- No comparison to any other transit agency.
- No claim about causes of delay — weather, crowding, incidents. Only about
  prediction error.
- No competing prediction model. Headway forecasts nothing.
- No advice to any traveller about any journey.

---

## 9. Amendments

Any change to this document is a **new numbered section appended below**, never an
edit to what is above, stating what changed, when, and why — committed before the
analysis it affects is run.

**Amendments so far: one (§11).**

---

## 10. Provenance, stated plainly

The repository was initialised on 2026-08-20, **after** M0-T4 had already run.
The commit ordering reflects working order, and from this commit forward every
measurement lands in git as it happens. But for M0 itself, the claim that the
kill criterion preceded the result rests on my word, not on a timestamp anyone
else can check.

That is recorded here for the same reason as §0: a project whose subject is
whether published claims can be trusted cannot overstate the provenance of its
own.


---

## 11. Amendment 1 — retention, sampling and seals

**Added:** 2026-08-20, after the M0-T6 storage measurement and before any
retention has run. No data has been pruned at the time of writing.

### Why

M0-T6 measured **197 MB/day** against a 0.5 GB tier. Thirty days of full raw
would need 5.9 GB. Keeping everything is not an option that was rejected — it is
an option that does not exist.

### The policy

| Data | Kept |
|---|---|
| Full raw (`predictions_register`, `vehicle_events`) | **2 days** |
| Raw for a **10% sample of trips** | **30 days**, complete revision chains |
| `daily_metrics` aggregates | **Forever** |
| Seals over everything pruned | **Forever, in git** |

`matches` ceases to be a table and becomes a view. It cost 73 MB/day and held
nothing the register and arrivals did not already contain.

### The sample is by trip, and fixed by function

Membership is `md5(trip_id) % 10 = 0` — deterministic, computable by anyone,
carrying no state. It is a function rather than a stored list **so that the
sample cannot be quietly redrawn later to include a trip whose data turned out
to be interesting.** Verified unbiased at 9.98% over 200,000 identifiers.

Sampling by trip rather than by row is what keeps **BQ-4** answerable. Revision
paths need whole chains; a sample of scattered rows would answer nothing. This
gives complete chains for a tenth of trips — reduced power, not absence.

### What is knowingly given up

**Questions not thought of in advance cannot be asked of data older than two
days**, except on the 10% sample. Aggregates are frozen answers to the questions
listed in §2 and §4. This is a real loss and it is recorded as one.

**BQ-4 beyond two days is a 10% result** and must be reported as such — never as
if it covered the whole record.

### Seals

Before any row is deleted, a SHA-256 digest is taken over the rows in a fixed
order, together with the row count, and written to `seals/` and committed to git.

A seal proves the rows have not changed since sealing. **It does not prove they
were correct when written** — that is what the append-only grant is for — and it
cannot distinguish deliberate tampering from legitimate pruning, since both leave
fewer rows. This is why counts are published alongside digests rather than
reduced to pass/fail.

### Order of operations, fixed

**Aggregate → seal → prune.** Each step refuses to run unless the previous
succeeded. Aggregating after pruning would summarise data already gone; pruning
before sealing would destroy the evidence the seal exists to protect.

Retention runs as the **owner** role. The ingest role holds no `DELETE` by grant
(M0-T3), and that separation is deliberate: the process writing history must not
be able to rewrite it.
