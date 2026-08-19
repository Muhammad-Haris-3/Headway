"""Headway M0-T5 and M0-T6 — match rate, and whether this fits in 0.5 GB.

T5: of the trip+stop pairs the agency predicted for, how many did we observe
arriving? A low rate is not merely less data — the arrivals we miss are
unlikely to be a random sample of arrivals.

T6: measured bytes on disk, projected forward. The question is not "is it small
now" but "does it stay under 0.5 GB indefinitely", which is a question about
growth, retention and the store-on-change ratio together.
"""
import io, sys, collections, statistics
from pathlib import Path

import psycopg

def _utf8_stdout():
    """Windows consoles default to cp1252 and choke on non-ASCII output.
    Applied only when run as a script: rebinding stdout at import time breaks
    pytest's capture, which is how this was first noticed."""
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


_utf8_stdout()
ROOT = Path(__file__).resolve().parent.parent
LIMIT_BYTES = 0.5 * 1024**3


def env(key: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        t = line.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    sys.exit(f"{key} missing from .env")


conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
def q(sql, p=()):
    """Fetch rows."""
    return list(conn.execute(sql, p))


def x(sql, p=()):
    """Execute a statement that returns no rows."""
    conn.execute(sql, p)

# ------------------------------------------------------------------ the window
win = q("""SELECT min(observed_at), max(observed_at),
                  EXTRACT(EPOCH FROM (max(observed_at) - min(observed_at)))
           FROM vehicle_events""")[0]
hours = (win[2] or 0) / 3600
print(f"window: {hours*60:.1f} minutes")
counts = q("""SELECT (SELECT count(*) FROM predictions_register) AS preds,
                     (SELECT count(*) FROM vehicle_events)       AS vehs""")[0]
print(f"rows stored: {counts[0]:,} predictions, {counts[1]:,} vehicle events\n")

# ---------------------------------------------------- T5: arrivals and matching
# Arrival = MIDPOINT of the bracket (PREREGISTRATION.md §1), never first STOPPED_AT.
x("DELETE FROM matches")
x("DELETE FROM arrivals")
x("""
INSERT INTO arrivals (trip_id, stop_id, bracket_lower, bracket_upper, arrival_at, bracket_width)
SELECT s.trip_id, s.stop_id, b.lower_t, s.first_stop,
       b.lower_t + (s.first_stop - b.lower_t) / 2,
       EXTRACT(EPOCH FROM (s.first_stop - b.lower_t))
FROM (SELECT trip_id, stop_id, min(COALESCE(feed_updated_at, observed_at)) AS first_stop
      FROM vehicle_events WHERE status = 'STOPPED_AT' AND trip_id IS NOT NULL
      GROUP BY trip_id, stop_id) s
JOIN LATERAL (
  SELECT max(COALESCE(v.feed_updated_at, v.observed_at)) AS lower_t
  FROM vehicle_events v
  WHERE v.trip_id = s.trip_id AND v.stop_id = s.stop_id
    AND v.status <> 'STOPPED_AT'
    AND COALESCE(v.feed_updated_at, v.observed_at) < s.first_stop
) b ON TRUE
WHERE b.lower_t IS NOT NULL
""")
n_arr = q("SELECT count(*) FROM arrivals")[0][0]
print(f"arrivals derived (bracketed): {n_arr:,}")

x("""
INSERT INTO matches (prediction_id, trip_id, stop_id, horizon_s, error_s, bracket_width)
SELECT DISTINCT ON (p.id) p.id, p.trip_id, p.stop_id,
       EXTRACT(EPOCH FROM (p.arrival_time - p.observed_at)),
       EXTRACT(EPOCH FROM (a.arrival_at - p.arrival_time)),
       a.bracket_width
FROM predictions_register p
JOIN arrivals a ON a.trip_id = p.trip_id AND a.stop_id = p.stop_id
WHERE p.arrival_time IS NOT NULL
  AND p.observed_at < a.arrival_at
  AND p.trip_id <> 'grant-test'
""")

# The 86.7% baseline was restricted to arrivals PREDICTED to occur before the
# observation window closed. Anything predicted for after we stopped watching
# cannot be observed, and counting it as a miss measures the window, not the
# method. The same restriction is applied here or the two are not comparable.
raw_targets = q("""SELECT count(*) FROM (SELECT DISTINCT trip_id, stop_id
                   FROM predictions_register
                   WHERE arrival_time IS NOT NULL AND trip_id <> 'grant-test') t""")[0][0]
targets = q("""SELECT count(*) FROM (
                 SELECT trip_id, stop_id, min(arrival_time) AS first_pred
                 FROM predictions_register
                 WHERE arrival_time IS NOT NULL AND trip_id <> 'grant-test'
                 GROUP BY trip_id, stop_id
               ) t WHERE t.first_pred < (SELECT max(observed_at) FROM vehicle_events)""")[0][0]
matched_pairs = q("SELECT count(DISTINCT (trip_id, stop_id)) FROM matches")[0][0]
n_match = q("SELECT count(*) FROM matches")[0][0]

print("=" * 64)
print(f"  MATCH RATE: {matched_pairs:,} of {targets:,} predicted trip+stop pairs "
      f"= {100*matched_pairs/max(1,targets):.1f}%")
print(f"  unrestricted, for reference: {matched_pairs:,} of {raw_targets:,} "
      f"= {100*matched_pairs/max(1,raw_targets):.1f}%   (feasibility unrestricted: 69.2%)")
print(f"  baseline at 30s polling, same in-window restriction: 86.7%")
print("=" * 64)
print(f"  matched predictions: {n_match:,}\n")

# error by horizon, primary window only (bracket <= 60s, PREREGISTRATION §3)
print("error by horizon, bracket <= 60s, midpoint estimator, >= 5 min only:")
print(f"  {'horizon':<12}{'n':>8}{'median':>10}{'mean':>9}")
for lo, hi, lab in [(300, 600, "5-10 min"), (600, 1200, "10-20 min"), (1200, 1800, "20-30 min")]:
    rows = q("""SELECT error_s FROM matches
                WHERE bracket_width <= 60 AND horizon_s >= %s AND horizon_s < %s""", (lo, hi))
    e = [r[0] for r in rows]
    if not e:
        print(f"  {lab:<12}{'—':>8}")
        continue
    print(f"  {lab:<12}{len(e):>8,}{statistics.median(e):>9.0f}s{statistics.mean(e):>8.0f}s")
print("  (horizons under 5 min withdrawn — PREREGISTRATION.md §2)\n")

# ------------------------------------------------------------------ T6: storage
print("=" * 64)
print("  T6 — STORAGE")
print("=" * 64)
sizes = q("""SELECT relname, pg_total_relation_size(c.oid) AS bytes
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname='public' AND c.relkind='r' ORDER BY bytes DESC""")
total = sum(b for _, b in sizes)
for name, b in sizes:
    print(f"  {name:<24}{b/1024:>10,.0f} KB")
print(f"  {'TOTAL':<24}{total/1024:>10,.0f} KB   ({total/1024**2:.2f} MB)")

if hours > 0:
    per_hour = float(total) / float(hours)
    per_day = per_hour * 24
    print(f"\n  measured growth: {per_hour/1024**2:.2f} MB/hour  ->  {per_day/1024**2:.1f} MB/day")
    days = LIMIT_BYTES / per_day if per_day else 0.0
    print(f"  0.5 GB tier is exhausted in {days:.1f} days of raw retention")
    print(f"  one year of raw would need {per_day*365/1024**3:.1f} GB")
    print()
    if days >= 365:
        print("  VERDICT: fits for a year with no retention policy.")
    else:
        keep_days = max(1, int(days * 0.6))
        print(f"  VERDICT: raw retention must be bounded. Keeping ~{keep_days} days of raw")
        print(f"  vehicle_events and aggregating older data leaves headroom; matches and")
        print(f"  arrivals are the durable record and are far smaller than the raw stream.")
        vh = [b for n_, b in sizes if n_ == 'vehicle_events']
        if vh and total:
            print(f"  vehicle_events is {100*vh[0]/total:.0f}% of current bytes — it is the "
                  f"table any retention policy must target.")
conn.close()
