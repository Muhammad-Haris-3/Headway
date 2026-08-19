"""Read path for the Headway API.

Connects as `headway_app`, which holds SELECT and nothing else (M0-T3).
Read-only is additionally set per TRANSACTION rather than per session or as a
startup option: Neon's pooled endpoint runs PgBouncer, which rejects
`options=-c ...` outright and does not reliably carry session SET across
transactions. The grant is the real enforcement; this is the second lock.
"""
import os
from pathlib import Path

from psycopg_pool import ConnectionPool

ROOT = Path(__file__).resolve().parent.parent
READ_ONLY = "SET TRANSACTION READ ONLY"


def _url() -> str:
    v = os.environ.get("APP_DATABASE_URL")
    if v:
        return v
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            t = line.strip()
            if t and not t.startswith("#") and "=" in t and t.split("=", 1)[0].strip() == "APP_DATABASE_URL":
                return t.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("APP_DATABASE_URL is not set. This must be the read-only role.")


pool = ConnectionPool(_url(), min_size=0, max_size=4, open=False)


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(READ_ONLY)
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(sql: str, params: tuple = ()):
    r = rows(sql, params)
    return list(r[0].values())[0] if r else None
