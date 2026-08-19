"""Headway — the ingester. Writes through the append-only role.

STORE ON CHANGE, not on observation.

M0-T4 established that we poll roughly five times faster than the MBTA's
records actually change. Storing every poll therefore writes four redundant
rows for every real one: ~2.2M rows/day on three routes, which exhausts a
0.5 GB tier in under three days while carrying almost no information.

So a row is written only when the observed state DIFFERS from the last state
recorded for that key. Two consequences, both good:

  * storage falls by roughly the ratio between our cadence and the feed's
  * the prediction table becomes a revision history rather than a sampling of
    one, which is what BQ-4 needs to ask whether predictions converge honestly
    or snap to reality at the last moment

Connects as `headway_ingest`, which holds INSERT and SELECT and cannot UPDATE
or DELETE (M0-T3). Nothing here can rewrite history, by grant.
"""
import argparse, io, json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
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
ROOT = Path(__file__).resolve().parent.parent
ROUTES = "Red,Orange,Blue"
BASE = "https://api-v3.mbta.com"
VEHICLE_EVERY = 4.0
PREDICT_EVERY = 30.0


def env(key: str) -> str:
    """Prefer the process environment (GitHub secrets), fall back to .env (local)."""
    v = os.environ.get(key)
    if v:
        return v
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and "=" in t:
                k, val = t.split("=", 1)
                if k.strip() == key:
                    return val.strip().strip('"').strip("'")
    sys.exit(f"{key} not set (no environment variable, not in .env)")


def get(path: str, params: dict):
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "headway/0.1"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def rel(o, name):
    d = (o.get("relationships", {}).get(name) or {}).get("data")
    return d["id"] if d else None


DERIVE_ARRIVALS = """
INSERT INTO arrivals (trip_id, stop_id, bracket_lower, bracket_upper, arrival_at, bracket_width)
SELECT s.trip_id, s.stop_id, b.lower_t, s.first_stop,
       b.lower_t + (s.first_stop - b.lower_t) / 2,
       EXTRACT(EPOCH FROM (s.first_stop - b.lower_t))
FROM (SELECT trip_id, stop_id, min(COALESCE(feed_updated_at, observed_at)) AS first_stop
      FROM vehicle_events
      WHERE status = 'STOPPED_AT' AND trip_id IS NOT NULL
        AND observed_at > now() - interval '6 hours'
      GROUP BY trip_id, stop_id) s
JOIN LATERAL (
  SELECT max(COALESCE(v.feed_updated_at, v.observed_at)) AS lower_t
  FROM vehicle_events v
  WHERE v.trip_id = s.trip_id AND v.stop_id = s.stop_id
    AND v.status <> 'STOPPED_AT'
    AND COALESCE(v.feed_updated_at, v.observed_at) < s.first_stop
) b ON TRUE
WHERE b.lower_t IS NOT NULL
ON CONFLICT (trip_id, stop_id) DO NOTHING
"""


def derive_arrivals(conn) -> int:
    """Turn raw vehicle events into bracketed arrivals.

    Nothing else does this. The ingester writes raw and the retention job
    aggregates from `matches`, which is a view over `arrivals` — so without this
    step `arrivals` never grows, the match rate falls steadily against a frozen
    table, and the pipeline looks healthy the whole time. Found by building the
    status page and seeing 36.5% where 82.6% was measured.

    Arrival is the bracket MIDPOINT (PREREGISTRATION.md §1). ON CONFLICT DO
    NOTHING because an arrival, once established, is not revised: a later run
    seeing a wider bracket must not overwrite a tighter earlier one.
    """
    with conn.cursor() as cur:
        cur.execute(DERIVE_ARRIVALS)
        return cur.rowcount


def main(minutes: float):
    conn = psycopg.connect(env("INGEST_DATABASE_URL"), autocommit=True)
    end = time.time() + minutes * 60
    next_pred = 0.0

    # last state seen per key — the store-on-change memory
    veh_state: dict[str, tuple] = {}
    pred_state: dict[tuple, tuple] = {}
    seen = {"veh": 0, "pred": 0}
    wrote = {"veh": 0, "pred": 0}
    polls = errors = 0
    started = datetime.now(timezone.utc)

    while time.time() < end:
        cycle = time.time()
        now = datetime.now(timezone.utc)
        polls += 1

        try:
            d = get("/vehicles", {"filter[route]": ROUTES, "page[limit]": 200})
            rows = []
            for x in d.get("data", []):
                a = x["attributes"]
                key = x["id"]
                state = (a.get("current_status"), rel(x, "stop"), a.get("updated_at"),
                         a.get("current_stop_sequence"))
                seen["veh"] += 1
                if veh_state.get(key) == state:
                    continue                      # byte-identical to last: skip
                veh_state[key] = state
                rows.append((now, a.get("updated_at"), key, rel(x, "trip"), rel(x, "stop"),
                             rel(x, "route"), a.get("current_status"), a.get("current_stop_sequence")))
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO vehicle_events (observed_at, feed_updated_at, vehicle_id,"
                        " trip_id, stop_id, route_id, status, stop_sequence)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", rows)
                wrote["veh"] += len(rows)
        except Exception as e:
            errors += 1
            print(f"  vehicle error: {type(e).__name__}", flush=True)

        if time.time() >= next_pred:
            next_pred = time.time() + PREDICT_EVERY
            try:
                d = get("/predictions", {"filter[route]": ROUTES, "page[limit]": 400})
                rows = []
                for x in d.get("data", []):
                    a = x["attributes"]
                    trip, stop = rel(x, "trip"), rel(x, "stop")
                    if not trip or not stop:
                        continue
                    key = (trip, stop)
                    state = (a.get("arrival_time"), a.get("arrival_uncertainty"))
                    seen["pred"] += 1
                    if pred_state.get(key) == state:
                        continue                  # unchanged prediction: skip
                    pred_state[key] = state
                    rows.append((now, trip, stop, rel(x, "route"), a.get("arrival_time"),
                                 a.get("arrival_uncertainty"), a.get("stop_sequence"),
                                 a.get("schedule_relationship")))
                if rows:
                    with conn.cursor() as cur:
                        cur.executemany(
                            "INSERT INTO predictions_register (observed_at, trip_id, stop_id,"
                            " route_id, arrival_time, arrival_uncertainty, stop_sequence,"
                            " schedule_relationship) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", rows)
                    wrote["pred"] += len(rows)
            except Exception as e:
                errors += 1
                print(f"  prediction error: {type(e).__name__}", flush=True)

        if polls % 60 == 0:
            print(f"  polls={polls}  vehicles {wrote['veh']:,}/{seen['veh']:,} written/seen"
                  f"  predictions {wrote['pred']:,}/{seen['pred']:,}", flush=True)

        sleep = VEHICLE_EVERY - (time.time() - cycle)
        if sleep > 0:
            time.sleep(sleep)

    try:
        n = derive_arrivals(conn)
        print(f"derived {n:,} new arrivals", flush=True)
    except Exception as e:
        errors += 1
        print(f"  derive error: {type(e).__name__}: {e}", flush=True)

    # NFR-5: coverage is recorded, so a gap can never be read as punctual service
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO coverage (window_start, window_end, polls, expected, errors, note)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (started, datetime.now(timezone.utc), polls,
             int(minutes * 60 / VEHICLE_EVERY), errors, os.environ.get("RUN_NOTE", "local run")))
    conn.close()

    for k in ("veh", "pred"):
        ratio = seen[k] / max(1, wrote[k])
        print(f"{k}: wrote {wrote[k]:,} of {seen[k]:,} observed  ->  {ratio:.1f}x reduction")
    print(f"DONE polls={polls} errors={errors}", flush=True)


if __name__ == "__main__":
    _utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=20.0)
    main(**vars(ap.parse_args()))
