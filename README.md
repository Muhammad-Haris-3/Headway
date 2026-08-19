# Headway

**Transit agencies publish millions of arrival predictions, and their own error
bars. Nobody keeps score.**

Headway records the MBTA's published predictions **before the outcome exists**,
observes what actually happened, and grades them.

It forecasts nothing. It is the referee, not the player.

> **Status: M0 complete, collecting.** No accuracy figures are published yet.
> The [pre-registration](PREREGISTRATION.md) requires 7 continuous days of
> ingestion and 20,000 matched predictions first, and that floor was set before
> the data existed.

---

## What M0 established

**Arrival-time precision is 20.0s, and it is a property of the feed, not of the
method.** We poll every 4 seconds; the MBTA's vehicle records refresh about
every 20. An API key would not help — it raises the request limit, not the
refresh rate.

**That precision caught a false finding before it was published.** The pilot
produced a clean monotonic result — trains late by +3s, +13s, +28s, +42s as the
horizon grew. Taking arrival as the first `STOPPED_AT` observation takes the
upper end of a 20-second bracket, overstating arrival by ~10s. Switching to the
bracket midpoint:

| Horizon | First `STOPPED_AT` | Midpoint |
|---|---|---|
| 5–10 min | +28s | **+6s** |
| 10–20 min | +42s | **+13s** |

The lateness shrinks by three quarters. What was nearly published was mostly the
observer.

**Horizons under five minutes are withdrawn** — their true errors are smaller
than the measurement noise. Not caveated. Withdrawn.

Full record: [`Headway_M0_Summary.md`](Headway_M0_Summary.md).

---

## What makes the record trustworthy

| Mechanism | What it prevents |
|---|---|
| **Append-only register.** The ingest role holds no `UPDATE` or `DELETE` — by database grant, tested by attempting both | Retrospective editing of a prediction after its outcome is known |
| **Kill criterion as a number**, written before any data was collected | Deciding after the fact which horizons to trust |
| **Retention runs as a separate role** from ingestion | The process writing history being able to rewrite it |
| **Seals committed to git** before rows are pruned | Silent tampering — the digest is verifiable by someone with access to neither the database nor the author |
| **Coverage recorded per run** | A gap in ingestion reading as a period of punctual service |

---

## The honest limits

- **One agency.** Everything here is about the MBTA and generalises to nobody.
- **Storage forces a choice.** 197 MB/day against a 0.5 GB tier. Two days of
  full raw, thirty days at a 10% trip sample, aggregates forever. Questions not
  anticipated cannot be asked of older data except on the sample.
- **`arrival_uncertainty` is not defined as a confidence interval** by the
  GTFS-RT spec. What it empirically corresponds to is a finding, never evidence
  the agency is wrong against a standard it never claimed.
- **The repository was initialised after M0-T4 ran.** Commit order reflects
  working order, but for M0 itself the claim that the criterion preceded the
  result rests on the author's word. Recorded in
  [`PREREGISTRATION.md`](PREREGISTRATION.md) §10 rather than glossed.

---

## Documents

| | |
|---|---|
| [`Headway_SRS_v1.0.md`](Headway_SRS_v1.0.md) | Requirements, questions, risks |
| [`Headway_M0_Spec.md`](Headway_M0_Spec.md) | The milestone, and the kill criterion as three numbered bands |
| [`Headway_M0_Summary.md`](Headway_M0_Summary.md) | Every measurement, what broke, what was decided |
| [`PREREGISTRATION.md`](PREREGISTRATION.md) | Definitions and thresholds, fixed in advance — read §0 first |
