"""Headway API — M0-T8, the walking skeleton.

This service deliberately serves NO accuracy figures. Not one.

The pre-registration requires seven continuous days of ingestion and 20,000
matched predictions before any error figure is published, and that floor was
fixed before the data existed. Shipping a provisional number now — even
captioned "early" — is exactly how a stopping rule gets abandoned without
anyone deciding to abandon it.

What it serves instead is the state of the record: how much has been collected,
how complete the collection has been, how precisely arrivals can be pinned down,
and how far off the threshold is. Those are established.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db

# From PREREGISTRATION.md §7. Named here so the API cannot quietly publish early.
REQUIRED_DAYS = 7
REQUIRED_MATCHES = 20_000

NOTICES = {
    "one_agency": "Everything here describes the MBTA. It generalises to no other operator.",
    "not_advice": "This is a measurement of published predictions. It is not advice about any journey.",
    "no_figures_yet": (
        f"No accuracy figures are published yet. The pre-registration requires "
        f"{REQUIRED_DAYS} continuous days of ingestion and {REQUIRED_MATCHES:,} matched "
        f"predictions first, and that floor was set before any data existed."
    ),
    "cold_start": "The API sleeps when idle on its free tier; the first request after a quiet period can take 30-50 seconds.",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.pool.open()
    yield
    db.pool.close()


app = FastAPI(title="Headway API",
              description="Keeping score on published arrival predictions.",
              version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://[A-Za-z0-9._-]+\.vercel\.app|http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok", "rows": db.rows("""
        SELECT (SELECT count(*) FROM predictions_register) AS predictions,
               (SELECT count(*) FROM vehicle_events)       AS vehicle_events,
               (SELECT count(*) FROM arrivals)             AS arrivals,
               (SELECT count(*) FROM coverage)             AS coverage_windows
    """)[0]}


@app.get("/status")
def status():
    """Everything the skeleton page shows, in one call."""
    counts = db.rows("""
        SELECT (SELECT count(*) FROM predictions_register) AS predictions,
               (SELECT count(*) FROM vehicle_events)       AS vehicle_events,
               (SELECT count(*) FROM arrivals)             AS arrivals,
               (SELECT count(*) FROM matches)              AS matched_predictions
    """)[0]

    # Progress toward the threshold is counted from `daily_metrics`, NOT from a
    # live count over `matches`. `matches` is a view over raw that retention
    # prunes — 2 days full, 30 days at a 10% trip sample — so counting it makes
    # the gate DRIFT DOWN as old rows are deleted instead of accumulating: of
    # 12,625 matches present on 2026-08-21, only 1,443 would survive the 2-day
    # window. `daily_metrics` is written once per complete day, before anything
    # is pruned, and kept forever. It is the only counter that outlives its own
    # source, which is exactly what a stopping rule needs.
    cumulative = db.rows("""
        SELECT coalesce(sum(n), 0)  AS matched_predictions,
               count(DISTINCT day)  AS days_aggregated
        FROM daily_metrics
    """)[0]

    span = db.rows("""
        SELECT min(observed_at) AS first_seen, max(observed_at) AS last_seen,
               EXTRACT(EPOCH FROM (max(observed_at) - min(observed_at))) / 86400.0 AS days
        FROM predictions_register
    """)[0]
    days = float(span["days"] or 0)

    # Coverage: ingestion runs, and how many polls each actually managed against
    # what it intended. A gap here would otherwise read as punctual service.
    cov = db.rows("""
        SELECT count(*) AS windows, sum(polls) AS polls, sum(expected) AS expected,
               sum(errors) AS errors,
               EXTRACT(EPOCH FROM sum(window_end - window_start)) / 60.0 AS minutes_covered
        FROM coverage
    """)[0]
    recent = db.rows("""
        SELECT window_start, window_end, polls, expected, errors, note
        FROM coverage ORDER BY id DESC LIMIT 10
    """)

    # Arrival precision — the M0-T4 finding, recomputed live from whatever has
    # been collected rather than quoted from the summary.
    prec = db.rows("""
        SELECT count(*) AS n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY bracket_width) AS median,
               percentile_cont(0.9) WITHIN GROUP (ORDER BY bracket_width) AS p90,
               max(bracket_width) AS max,
               avg((bracket_width <= 60)::int) AS share_under_60s
        FROM arrivals
    """)[0]

    # Match rate, in-window: predictions whose arrival was due before we last
    # looked. Anything predicted for after that cannot have been observed, and
    # counting it as a miss measures the window rather than the method.
    mr = db.rows("""
        WITH targets AS (
          SELECT trip_id, stop_id, min(arrival_time) AS due
          FROM predictions_register
          WHERE arrival_time IS NOT NULL AND trip_id <> 'grant-test'
          GROUP BY trip_id, stop_id
        )
        SELECT count(*) FILTER (WHERE due < (SELECT max(observed_at) FROM vehicle_events)) AS in_window,
               count(*) FILTER (WHERE due < (SELECT max(observed_at) FROM vehicle_events)
                                  AND EXISTS (SELECT 1 FROM arrivals a
                                              WHERE a.trip_id = t.trip_id AND a.stop_id = t.stop_id)) AS matched
        FROM targets t
    """)[0]
    in_window = mr["in_window"] or 0
    matched = mr["matched"] or 0

    return {
        "collecting": True,
        "counts": counts,
        "window": {"first_seen": span["first_seen"], "last_seen": span["last_seen"],
                   "days": round(days, 3)},
        "threshold": {
            "required_days": REQUIRED_DAYS,
            "required_matches": REQUIRED_MATCHES,
            "days_done": round(days, 2),
            "matches_done": cumulative["matched_predictions"],
            "days_remaining": round(max(0.0, REQUIRED_DAYS - days), 2),
            "met": (days >= REQUIRED_DAYS
                    and cumulative["matched_predictions"] >= REQUIRED_MATCHES),
            "days_aggregated": cumulative["days_aggregated"],
            "matches_retained_now": counts["matched_predictions"],
            "note": ("Counted from the sealed daily aggregates, which are written before "
                     "any row is pruned and kept permanently — not from the live join, "
                     "which shrinks as raw data ages out. It covers complete days only, "
                     "in the analysis population fixed in advance: bracket width under "
                     "60s, horizons 5-30 minutes. Today is not included until it ends."),
        },
        "coverage": {
            "windows": cov["windows"], "polls": cov["polls"], "expected": cov["expected"],
            "errors": cov["errors"],
            "poll_completion": (float(cov["polls"]) / float(cov["expected"])
                                if cov["expected"] else None),
            "minutes_covered": round(float(cov["minutes_covered"] or 0), 1),
            "recent": recent,
        },
        "arrival_precision_seconds": {
            "n": prec["n"],
            "median": float(prec["median"]) if prec["median"] is not None else None,
            "p90": float(prec["p90"]) if prec["p90"] is not None else None,
            "max": float(prec["max"]) if prec["max"] is not None else None,
            "share_within_60s": float(prec["share_under_60s"]) if prec["share_under_60s"] is not None else None,
            "note": ("This is the precision of the observation, not of the prediction. "
                     "It is a property of how often the feed refreshes, not of our polling."),
        },
        "match_rate": {
            "in_window": in_window, "matched": matched,
            "rate": (matched / in_window) if in_window else None,
            "note": ("Restricted to arrivals due before we last observed. Anything predicted "
                     "for after that cannot have been seen, and counting it as a miss would "
                     "measure the window rather than the method."),
        },
        "withheld": {
            "error_by_horizon": NOTICES["no_figures_yet"],
            "containment": NOTICES["no_figures_yet"],
            "horizons_under_5_min": ("Permanently withdrawn. Their true errors are smaller than "
                                     "the 20s measurement noise, so they will not be published "
                                     "at any sample size."),
        },
        "notices": NOTICES,
    }
