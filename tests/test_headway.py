"""Headway — CI tests.

The append-only guarantee is the project's load-bearing claim, so the test that
matters is the one that tries to break it. It skips when no database is
reachable rather than passing vacuously: a skipped test that says so is honest,
a green tick that checked nothing is not.
"""
import os
from datetime import date
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _env(key):
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
    return None


needs_db = pytest.mark.skipif(_env("DATABASE_URL") is None, reason="no DATABASE_URL available")
needs_ingest = pytest.mark.skipif(_env("INGEST_DATABASE_URL") is None,
                                  reason="no INGEST_DATABASE_URL available")


# ---------------------------------------------------------------- pure logic
def test_horizon_buckets_exclude_under_five_minutes():
    """PREREGISTRATION.md §2: sub-5-minute horizons are withdrawn, not caveated."""
    from ingest.retain import BUCKETS
    lows = [lo for lo, _, _ in BUCKETS]
    assert min(lows) >= 300, "a bucket below 5 minutes has crept back in"
    assert [lab for _, _, lab in BUCKETS] == ["5-10", "10-20", "20-30"]


def test_retention_windows_match_the_amendment():
    """PREREGISTRATION.md §11: 2 days full, 30 days sampled."""
    from ingest.retain import FULL_DAYS, SAMPLE_DAYS
    assert FULL_DAYS == 2
    assert SAMPLE_DAYS == 30


# ------------------------------------------------------- the guarantee itself
@needs_ingest
def test_ingest_role_cannot_update_or_delete_the_register():
    """M0-T3. If this ever passes silently, the project's central claim is void."""
    import psycopg
    url = _env("INGEST_DATABASE_URL")
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("UPDATE predictions_register SET route_id = 'tampered'")
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("DELETE FROM predictions_register WHERE true")


@needs_ingest
def test_ingest_role_can_still_append():
    """The guarantee is worthless if it also blocks the writing it protects."""
    import psycopg
    with psycopg.connect(_env("INGEST_DATABASE_URL"), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM predictions_register")
        assert cur.fetchone()[0] >= 0


@needs_db
def test_trip_sample_is_unbiased():
    """PREREGISTRATION.md §11: a 10% sample, by trip, fixed by function."""
    import psycopg
    with psycopg.connect(_env("DATABASE_URL"), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FILTER (WHERE is_sampled('trip-'||i)), count(*) "
                    "FROM generate_series(1, 50000) i")
        hit, total = cur.fetchone()
        assert 0.09 < hit / total < 0.11, f"sample rate {hit/total:.3f} is not 10%"


@needs_db
def test_an_aggregate_can_never_shrink():
    """The permanent record must not be recomputable from a fraction of itself.

    After a day's full raw is pruned its 10% sample survives, so the day is
    still visible to the aggregator. A plain upsert would recompute it from a
    tenth of the data and overwrite the real figures — on 2026-08-19, bucket
    5-10, n 1,592 -> 210 and median +7.5s -> -14.5s, with the raw needed to
    notice it deleted in the same run. This attempts exactly that overwrite and
    expects it to be refused.
    """
    import psycopg
    from ingest.retain import UPSERT_DAILY

    probe = (date(1970, 1, 1), "test-shrink-guard", "5-10")
    big = probe + (1000, 7.5, 7.5, -1.0, 20.0, 900, 800)
    small = probe + (10, -14.5, -14.5, -30.0, 5.0, 9, 3)

    with psycopg.connect(_env("DATABASE_URL"), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM daily_metrics WHERE route_id = %s", (probe[1],))
        try:
            cur.execute(UPSERT_DAILY, big)
            cur.execute(UPSERT_DAILY, small)          # the sample, trying to overwrite
            cur.execute("SELECT n, median_error_s FROM daily_metrics "
                        "WHERE day = %s AND route_id = %s AND horizon_bucket = %s", probe)
            n, median = cur.fetchone()
            assert n == 1000, f"a 10% recomputation overwrote the full day (n={n})"
            assert median == 7.5, f"median was overwritten with the sampled value ({median})"

            # ...but a genuinely larger recomputation must still land, or late-derived
            # arrivals could never be added to a day already written.
            cur.execute(UPSERT_DAILY, probe + (2000, 9.0, 9.0, -1.0, 20.0, 1800, 1600))
            cur.execute("SELECT n FROM daily_metrics "
                        "WHERE day = %s AND route_id = %s AND horizon_bucket = %s", probe)
            assert cur.fetchone()[0] == 2000, "growth was refused as well as erosion"
        finally:
            cur.execute("DELETE FROM daily_metrics WHERE route_id = %s", (probe[1],))


@needs_db
def test_matches_is_a_view_not_a_table():
    """It cost 73 MB/day as a table and held nothing derivable data did not."""
    import psycopg
    with psycopg.connect(_env("DATABASE_URL"), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT relkind FROM pg_class WHERE relname = 'matches'")
        row = cur.fetchone()
        assert row is not None and row[0] == "v", "matches is not a view"
