"""Headway M0-T4 — measure the arrival bracket, and evaluate the kill criterion.

For each (trip, stop) the vehicle was observed arriving at, the true arrival is
bracketed between:

    lower = last observation showing the vehicle NOT yet stopped there
    upper = first observation showing it STOPPED_AT

`upper - lower` is the precision. It is reported as a distribution, because a
median of 4s with a tail reaching 90s is a different project from a uniform 4s
(M0 spec T4).

Two clocks are compared. The feed's `updated_at` is what a real system would
use; our own `recorded_at` bounds how much of the uncertainty is ours rather
than the feed's.
"""
import json, io, sys, collections, statistics
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
T = lambda s: datetime.fromisoformat(s) if s else None

rows = [json.loads(l) for l in open("../ingest/m0_vehicles.jsonl", encoding="utf-8")]
print(f"vehicle observations: {len(rows):,}")
if not rows:
    sys.exit("no data")

span = (T(rows[-1]["recorded_at"]) - T(rows[0]["recorded_at"])).total_seconds()
print(f"window: {span/60:.1f} minutes")
polls = len({r["recorded_at"] for r in rows})
print(f"distinct polls: {polls:,}  ->  {span/max(1,polls-1):.1f}s actual cadence")
print(f"status mix: {dict(collections.Counter(r['status'] for r in rows))}\n")


def brackets(clock: str):
    """clock: 'updated_at' (feed) or 'recorded_at' (ours)."""
    seq = collections.defaultdict(list)
    for r in rows:
        if not r["trip"] or not r["stop"]:
            continue
        t = T(r.get(clock)) or T(r["recorded_at"])
        seq[(r["trip"], r["stop"])].append((t, r["status"]))

    out = []
    for key, obs in seq.items():
        obs.sort()
        first_stop = next((t for t, s in obs if s == "STOPPED_AT"), None)
        if first_stop is None:
            continue
        before = [t for t, s in obs if s != "STOPPED_AT" and t < first_stop]
        if not before:
            continue          # never seen approaching: cannot bracket
        out.append((first_stop - before[-1]).total_seconds())
    return out


for clock, label in [("updated_at", "feed clock (updated_at)"), ("recorded_at", "our clock (poll time)")]:
    w = brackets(clock)
    if not w:
        print(f"{label}: no bracketable arrivals\n")
        continue
    w.sort()
    q = lambda p: w[min(len(w) - 1, int(p * len(w)))]
    print(f"{label}: {len(w):,} bracketed arrivals")
    print(f"  median {statistics.median(w):.1f}s   mean {statistics.mean(w):.1f}s")
    print(f"  p25 {q(.25):.0f}s   p75 {q(.75):.0f}s   p90 {q(.90):.0f}s   p99 {q(.99):.0f}s   max {w[-1]:.0f}s")
    print(f"  within 10s: {100*sum(1 for x in w if x <= 10)/len(w):.0f}%"
          f"   within 60s: {100*sum(1 for x in w if x <= 60)/len(w):.0f}%\n")

feed = brackets("updated_at")
if feed:
    W = statistics.median(feed)
    print("=" * 62)
    print(f"  MEDIAN BRACKET WIDTH  W = {W:.1f}s   (feed clock)")
    verdict = ("PROCEED IN FULL — all horizon buckets supported" if W <= 10 else
               "PROCEED, BUT WITHDRAW every horizon under five minutes" if W <= 60 else
               "DO NOT BUILD — publish the negative result")
    print(f"  KILL CRITERION (M0 spec 6): {verdict}")
    print("=" * 62)
