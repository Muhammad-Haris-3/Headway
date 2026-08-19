"""Headway M0-T4 — arrival-time precision.

The kill question: can the moment a train actually arrived be pinned down
finely enough for the errors we intend to measure to mean anything?

Method. Every arrival is BRACKETED between two observations:

    last time we saw the vehicle still approaching the stop
    first time we saw it stopped at the stop

The true arrival lies somewhere inside. The width of that bracket IS the
precision, measured rather than assumed — and it is measured per arrival, so
the distribution can be published instead of a single flattering median.

Vehicles are polled hard and predictions gently, because only the vehicle
stream determines precision. The MBTA allows 20 requests/minute without an API
key (confirmed from x-ratelimit-limit), so this runs at 15 + 2 = 17.
"""
import json, sys, io, time, urllib.request, urllib.parse
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROUTES = "Red,Orange,Blue"
VEHICLE_EVERY = 4.0      # seconds -> 15 requests/min
PREDICT_EVERY = 30.0     # seconds ->  2 requests/min
MINUTES = 30
BASE = "https://api-v3.mbta.com"


def get(path: str, params: dict):
    url = f"{BASE}{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "headway-m0/0.1"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def rel(o, name):
    d = (o.get("relationships", {}).get(name) or {}).get("data")
    return d["id"] if d else None


veh = open("m0_vehicles.jsonl", "w", encoding="utf-8")
pred = open("m0_predictions.jsonl", "w", encoding="utf-8")
end = time.time() + MINUTES * 60
next_pred = 0.0
nv = np_ = errors = 0

while time.time() < end:
    cycle = time.time()
    now = datetime.now(timezone.utc).isoformat()

    try:
        d = get("/vehicles", {"filter[route]": ROUTES, "page[limit]": 200})
        for x in d.get("data", []):
            a = x["attributes"]
            veh.write(json.dumps({
                "recorded_at": now,                 # our clock
                "updated_at": a.get("updated_at"),  # the feed's clock
                "vehicle": x["id"], "trip": rel(x, "trip"), "stop": rel(x, "stop"),
                "route": rel(x, "route"),
                "status": a.get("current_status"),
                "seq": a.get("current_stop_sequence"),
            }) + "\n"); nv += 1
        veh.flush()
    except Exception as e:
        errors += 1
        print(f"  vehicle error: {type(e).__name__}", flush=True)

    if time.time() >= next_pred:
        next_pred = time.time() + PREDICT_EVERY
        try:
            d = get("/predictions", {"filter[route]": ROUTES, "page[limit]": 400})
            for x in d.get("data", []):
                a = x["attributes"]
                pred.write(json.dumps({
                    "recorded_at": now,
                    "trip": rel(x, "trip"), "stop": rel(x, "stop"),
                    "route": rel(x, "route"),
                    "arrival_time": a.get("arrival_time"),
                    "arrival_uncertainty": a.get("arrival_uncertainty"),
                    "seq": a.get("stop_sequence"),
                    "schedule_relationship": a.get("schedule_relationship"),
                }) + "\n"); np_ += 1
            pred.flush()
        except Exception as e:
            errors += 1
            print(f"  prediction error: {type(e).__name__}", flush=True)

    if nv and nv % 2000 < 60:
        print(f"  vehicles={nv:,} predictions={np_:,} errors={errors}", flush=True)

    sleep = VEHICLE_EVERY - (time.time() - cycle)
    if sleep > 0:
        time.sleep(sleep)

veh.close(); pred.close()
print(f"DONE vehicles={nv:,} predictions={np_:,} errors={errors}", flush=True)
