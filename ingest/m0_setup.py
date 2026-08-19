"""Headway M0-T3 — schema, roles, and the test that the grant actually holds.

Two roles beyond the owner:

    headway_ingest   INSERT + SELECT on the register. No UPDATE. No DELETE.
    headway_app      SELECT only, everywhere. Used by the API.

The grants are not the point. The point is §3 below, which connects AS each
role and tries to violate them. A grant nobody has attempted to break is not a
guarantee, it is a comment.

Never prints a credential. Run:  python ingest/m0_setup.py
"""
import argparse, io, json, secrets, sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg
from psycopg import sql

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
INGEST_ROLE = "headway_ingest"
APP_ROLE = "headway_app"


def env(path=ROOT / ".env") -> dict:
    out = {}
    if not path.exists():
        sys.exit(f"{path} not found. Create it with one line: DATABASE_URL=postgresql://...")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        t = line.strip()
        if t and not t.startswith("#") and "=" in t:
            k, v = t.split("=", 1)
            if k.strip().isidentifier():
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def url_for(base: str, role: str, pw: str) -> str:
    u = urlparse(base)
    return urlunparse(u._replace(netloc=f"{role}:{pw}@{u.hostname}"))


def main(rotate: bool = False):
    cfg = env()
    if "DATABASE_URL" not in cfg:
        sys.exit("DATABASE_URL missing from .env")
    owner = cfg["DATABASE_URL"]
    dbname = urlparse(owner).path.lstrip("/")
    print("host:", urlparse(owner).hostname)

    pws = {}
    with psycopg.connect(owner, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute((ROOT / "sql" / "schema.sql").read_text(encoding="utf-8"))
            print("schema created")

            for role, key in ((INGEST_ROLE, "INGEST_DATABASE_URL"), (APP_ROLE, "APP_DATABASE_URL")):
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
                fresh = cur.fetchone() is None
                existing = cfg.get(key)
                # Rotating on every run silently invalidates whatever is already
                # configured in a deployed service, turning a routine setup into
                # an outage. Learned on Triage.
                reuse = (not fresh) and (not rotate) and bool(existing)
                pw = urlparse(existing).password if reuse else secrets.token_urlsafe(24)
                pws[key] = pw
                if not reuse:
                    # CREATE/ALTER ROLE are utility statements and take no bind
                    # parameters; the password is composed as an escaped literal.
                    cur.execute(sql.SQL("{} ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.SQL("CREATE" if fresh else "ALTER"),
                        sql.Identifier(role), sql.Literal(pw)))
                cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(dbname), sql.Identifier(role)))
                cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
                state = "created" if fresh else ("rotated" if rotate else "reused")
                print(f"  role {role}: {state}")

            ing, app = sql.Identifier(INGEST_ROLE), sql.Identifier(APP_ROLE)

            # ingest: append and read. Deliberately no UPDATE, no DELETE, anywhere.
            for tbl in ("predictions_register", "vehicle_events", "coverage"):
                cur.execute(sql.SQL("GRANT INSERT, SELECT ON {} TO {}").format(sql.Identifier(tbl), ing))
            for seqn in ("predictions_register_id_seq", "vehicle_events_id_seq", "coverage_id_seq"):
                cur.execute(sql.SQL("GRANT USAGE ON SEQUENCE {} TO {}").format(sql.Identifier(seqn), ing))

            # app: read everything, write nothing
            cur.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(app))
            cur.execute(sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}").format(app))
            print("  grants applied")
        conn.commit()

    # ---------------------------------------------------------------- §3 the test
    ingest_url = url_for(owner, INGEST_ROLE, pws["INGEST_DATABASE_URL"])
    app_url = url_for(owner, APP_ROLE, pws["APP_DATABASE_URL"])
    failures = []

    def must_fail(url, role, statement, label):
        try:
            with psycopg.connect(url, autocommit=True) as c, c.cursor() as k:
                k.execute(statement)
            failures.append(f"{role} was ALLOWED to {label} — the grant does not hold")
            print(f"  FAIL  {role}: {label} succeeded")
        except psycopg.errors.InsufficientPrivilege:
            print(f"  ok    {role}: {label} refused")
        except psycopg.Error as e:
            print(f"  ok?   {role}: {label} raised {type(e).__name__} (not a privilege error)")

    def must_work(url, role, statement, label):
        try:
            with psycopg.connect(url, autocommit=True) as c, c.cursor() as k:
                k.execute(statement)
            print(f"  ok    {role}: {label} permitted")
        except psycopg.Error as e:
            failures.append(f"{role} could not {label}: {type(e).__name__}")
            print(f"  FAIL  {role}: {label} refused — {type(e).__name__}")

    print("\nattempting to violate the grants:")
    must_work(ingest_url, INGEST_ROLE,
              "INSERT INTO predictions_register (observed_at, trip_id, stop_id, route_id) "
              "VALUES (now(), 'grant-test', 'grant-test', 'test')", "INSERT into the register")
    must_fail(ingest_url, INGEST_ROLE,
              "UPDATE predictions_register SET route_id = 'tampered' WHERE trip_id = 'grant-test'",
              "UPDATE the register")
    must_fail(ingest_url, INGEST_ROLE,
              "DELETE FROM predictions_register WHERE trip_id = 'grant-test'",
              "DELETE from the register")
    must_work(app_url, APP_ROLE, "SELECT count(*) FROM predictions_register", "SELECT")
    must_fail(app_url, APP_ROLE,
              "INSERT INTO predictions_register (observed_at, trip_id, stop_id, route_id) "
              "VALUES (now(), 'x', 'x', 'x')", "INSERT")
    must_fail(app_url, APP_ROLE, "DELETE FROM predictions_register WHERE true", "DELETE")

    # the test row stays: the owner could remove it, but the ingest role cannot,
    # and leaving it is the simplest standing demonstration of that.
    if failures:
        print("\n" + "\n".join(f"  {f}" for f in failures))
        sys.exit("M0-T3 FAILED: the append-only guarantee does not hold.")

    p = ROOT / ".env"
    lines = [l for l in p.read_text(encoding="utf-8-sig").splitlines()
             if not l.strip().startswith(("INGEST_DATABASE_URL=", "APP_DATABASE_URL="))]
    lines += [f"INGEST_DATABASE_URL={ingest_url}", f"APP_DATABASE_URL={app_url}"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nM0-T3 PASSED. Append-only holds under attempted violation.")
    print("INGEST_DATABASE_URL and APP_DATABASE_URL written to .env (values not shown)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rotate", action="store_true",
                    help="mint new role passwords; requires updating any deployed service")
    main(**vars(ap.parse_args()))
