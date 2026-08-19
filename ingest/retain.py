"""Headway — aggregate, seal, prune. In that order, always.

The order is the whole design. Aggregating after pruning would summarise data
that is already gone; pruning before sealing would destroy the evidence the seal
exists to protect. Each step refuses to run unless the previous one succeeded.

Runs as the OWNER role, not the ingest role. The ingest role holds no DELETE by
grant (M0-T3) and that is deliberate: the process writing history must not be
able to rewrite it. Retention is a separate, privileged operation, and the
separation is the point rather than an inconvenience.

Policy, from the M0-T6 measurement of 197 MB/day against a 0.5 GB tier:

    full raw            2 days
    10% trip sample    30 days, complete revision chains
    daily aggregates   forever

Usage:  python ingest/retain.py [--dry-run]
"""
import argparse, hashlib, io, json, os, sys
from datetime import date, datetime, timedelta, timezone
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
SEAL_DIR = ROOT / "seals"
FULL_DAYS = 2
SAMPLE_DAYS = 30

BUCKETS = [(300, 600, "5-10"), (600, 1200, "10-20"), (1200, 1800, "20-30")]


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


def aggregate(conn, day: date) -> int:
    """Write the permanent record for one complete day. Idempotent."""
    written = 0
    with conn.cursor() as cur:
        for lo, hi, label in BUCKETS:
            cur.execute("""
                SELECT route_id, count(*),
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY error_s),
                       avg(error_s),
                       percentile_cont(0.1) WITHIN GROUP (ORDER BY error_s),
                       percentile_cont(0.9) WITHIN GROUP (ORDER BY error_s),
                       count(*) FILTER (WHERE arrival_uncertainty IS NOT NULL),
                       count(*) FILTER (WHERE arrival_uncertainty IS NOT NULL
                                          AND abs(error_s) <= arrival_uncertainty)
                FROM matches
                WHERE observed_at::date = %s
                  AND bracket_width <= 60          -- primary window, pre-registration §3
                  AND horizon_s >= %s AND horizon_s < %s
                GROUP BY route_id
            """, (day, lo, hi))
            for r in cur.fetchall():
                cur.execute("""
                    INSERT INTO daily_metrics (day, route_id, horizon_bucket, n,
                        median_error_s, mean_error_s, p10_error_s, p90_error_s,
                        n_with_uncert, n_contained)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (day, route_id, horizon_bucket) DO UPDATE SET
                        n = EXCLUDED.n, median_error_s = EXCLUDED.median_error_s,
                        mean_error_s = EXCLUDED.mean_error_s,
                        p10_error_s = EXCLUDED.p10_error_s, p90_error_s = EXCLUDED.p90_error_s,
                        n_with_uncert = EXCLUDED.n_with_uncert,
                        n_contained = EXCLUDED.n_contained
                """, (day, r[0], label, r[1], r[2], r[3], r[4], r[5], r[6], r[7]))
                written += 1
    return written


def seal(conn, day: date, table: str, where: str, params: tuple, dry: bool) -> dict | None:
    """Digest the rows about to be removed, in a fixed order, before removing them."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT md5(t.*::text) FROM {table} t WHERE {where} ORDER BY 1", params)
        hashes = [r[0] for r in cur.fetchall()]
    if not hashes:
        return None
    digest = hashlib.sha256("".join(hashes).encode()).hexdigest()
    rec = {"covers_day": day.isoformat(), "table": table, "row_count": len(hashes),
           "digest": digest, "sealed_at": datetime.now(timezone.utc).isoformat()}
    if not dry:
        SEAL_DIR.mkdir(exist_ok=True)
        path = SEAL_DIR / f"{day.isoformat()}_{table}.json"
        path.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO seals (covers_day, table_name, row_count, digest)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT (covers_day, table_name) DO NOTHING""",
                        (day, table, len(hashes), digest))
    return rec


def main(dry_run: bool = False):
    conn = psycopg.connect(env("DATABASE_URL"), autocommit=True)
    today = datetime.now(timezone.utc).date()
    full_before = today - timedelta(days=FULL_DAYS)
    sample_before = today - timedelta(days=SAMPLE_DAYS)
    print(f"{'DRY RUN — nothing will be deleted' if dry_run else 'LIVE'}")
    print(f"full raw kept after   {full_before}")
    print(f"sampled raw kept after {sample_before}\n")

    # ---- 1. aggregate, before anything is removed -------------------------
    with conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT observed_at::date FROM predictions_register
                       WHERE observed_at::date < %s ORDER BY 1""", (today,))
        days = [r[0] for r in cur.fetchall()]
    total = 0
    for d in days:
        n = aggregate(conn, d)
        total += n
        print(f"  aggregated {d}: {n} rows into daily_metrics")
    if not days:
        print("  nothing complete to aggregate yet")
    print(f"  daily_metrics rows written: {total}\n")

    # ---- 2. seal, before anything is removed ------------------------------
    # Unsampled rows past the full-raw window are the ones that will go.
    doomed = [
        ("predictions_register",
         "observed_at::date < %s AND NOT is_sampled(trip_id)", (full_before,)),
        ("vehicle_events",
         "observed_at::date < %s AND (trip_id IS NULL OR NOT is_sampled(trip_id))", (full_before,)),
        ("predictions_register",
         "observed_at::date < %s AND is_sampled(trip_id)", (sample_before,)),
        ("vehicle_events",
         "observed_at::date < %s AND trip_id IS NOT NULL AND is_sampled(trip_id)", (sample_before,)),
    ]
    seals_made = 0
    for table, where, params in doomed:
        rec = seal(conn, params[0], table, where, params, dry_run)
        if rec:
            seals_made += 1
            print(f"  sealed {rec['row_count']:,} rows of {table} -> {rec['digest'][:16]}…")
    if not seals_made:
        print("  nothing old enough to seal")
    print()

    # ---- 3. only now, prune ----------------------------------------------
    if dry_run:
        for table, where, params in doomed:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {table} WHERE {where}", params)
                print(f"  would delete {cur.fetchone()[0]:,} from {table}")
    else:
        for table, where, params in doomed:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {table} WHERE {where}", params)
                print(f"  deleted {cur.rowcount:,} from {table}")

    with conn.cursor() as cur:
        cur.execute("""SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid)))
                       FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='public' AND c.relkind='r'""")
        print(f"\ndatabase size now: {cur.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    _utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    main(**vars(ap.parse_args()))
