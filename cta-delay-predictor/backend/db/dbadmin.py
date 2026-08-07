"""
Database diagnostics and emergency space recovery.

Why this exists
---------------
When a Postgres database is put into read-only mode (Supabase does this when a
project exceeds its disk quota), *every* write fails — including the DELETEs
that would free the space. The scheduled prune can't dig itself out.

This tool breaks that deadlock. Read-only enforcement of that kind is a GUC
(`default_transaction_read_only`), and a session may lift it for its own
transaction with `SET TRANSACTION READ WRITE` — provided the server is not a
physical replica in recovery. We attempt exactly that, then reclaim space.

Usage:
    python -m backend.db.dbadmin diagnose
    python -m backend.db.dbadmin recover --yes
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from backend.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Retention used by recovery (matches backend.etl.prune)
SNAPSHOT_RETENTION_DAYS = 7
DELETE_BATCH = 20_000


def _log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Write access
# ---------------------------------------------------------------------------

def _try_make_writable(conn) -> bool:
    """
    Attempt to lift read-only for the current transaction.

    Works when read-only comes from `default_transaction_read_only` set at the
    database/role level. Fails (correctly) on a physical standby, where writes
    are impossible no matter what.
    """
    for stmt in (
        "SET TRANSACTION READ WRITE",
        "SET LOCAL default_transaction_read_only = off",
    ):
        try:
            conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001 — try each, report at the end
            logger.debug("%s failed: %s", stmt, exc)

    try:
        ro = conn.execute(text("SHOW transaction_read_only")).scalar()
        return str(ro).lower() in ("off", "false", "f")
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Diagnose
# ---------------------------------------------------------------------------

def diagnose() -> dict:
    """Report connection identity, read-only state, and per-table sizes."""
    info: dict = {}
    with engine.connect() as conn:
        def scalar(sql: str, default=None):
            try:
                return conn.execute(text(sql)).scalar()
            except Exception as exc:  # noqa: BLE001
                return f"<error: {exc}>" if default is None else default

        info["current_user"] = scalar("SELECT current_user")
        info["database"] = scalar("SELECT current_database()")
        info["in_recovery"] = scalar("SELECT pg_is_in_recovery()")
        info["transaction_read_only"] = scalar("SHOW transaction_read_only")
        info["default_transaction_read_only"] = scalar("SHOW default_transaction_read_only")
        info["db_size"] = scalar("SELECT pg_size_pretty(pg_database_size(current_database()))")
        info["db_size_bytes"] = scalar("SELECT pg_database_size(current_database())")

        _log("=" * 68)
        _log("DATABASE DIAGNOSIS")
        _log("=" * 68)
        for key in (
            "current_user", "database", "in_recovery",
            "transaction_read_only", "default_transaction_read_only",
            "db_size",
        ):
            _log(f"  {key:34s} {info[key]}")

        # Per-table sizes, biggest first — shows where the space actually went.
        _log("\n  TABLE SIZES")
        try:
            rows = conn.execute(text(
                """
                SELECT c.relname,
                       pg_size_pretty(pg_total_relation_size(c.oid)) AS pretty,
                       pg_total_relation_size(c.oid) AS bytes,
                       COALESCE(s.n_live_tup, 0) AS approx_rows
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                ORDER BY pg_total_relation_size(c.oid) DESC
                """
            )).fetchall()
            info["tables"] = [
                {"name": r[0], "pretty": r[1], "bytes": r[2], "rows": r[3]} for r in rows
            ]
            for r in rows:
                _log(f"    {r[0]:28s} {r[1]:>10s}  ~{r[3]:,} rows")
        except Exception as exc:  # noqa: BLE001
            _log(f"    <could not read table sizes: {exc}>")

        # Is the dead raw_json blob column still present?
        try:
            has_raw = conn.execute(text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'arrival_snapshots' AND column_name = 'raw_json'
                """
            )).first() is not None
            info["raw_json_present"] = has_raw
            _log(f"\n  arrival_snapshots.raw_json present   {has_raw}")
        except Exception as exc:  # noqa: BLE001
            _log(f"  <raw_json check failed: {exc}>")

        # Oldest/newest snapshot — tells us how much is prunable.
        try:
            rng = conn.execute(text(
                "SELECT min(snapshot_time), max(snapshot_time) FROM arrival_snapshots"
            )).first()
            if rng:
                info["snapshot_range"] = [str(rng[0]), str(rng[1])]
                _log(f"  arrival_snapshots oldest             {rng[0]}")
                _log(f"  arrival_snapshots newest             {rng[1]}")
        except Exception as exc:  # noqa: BLE001
            _log(f"  <snapshot range failed: {exc}>")

    # Can we obtain write access at all?
    with engine.begin() as conn:
        writable = _try_make_writable(conn)
        info["can_make_writable"] = writable
        _log(f"\n  CAN LIFT READ-ONLY FOR A TRANSACTION  {writable}")
        if writable:
            try:
                conn.execute(text("CREATE TEMP TABLE _probe_write (x int)"))
                _log("  write probe                           OK")
                info["write_probe"] = True
            except Exception as exc:  # noqa: BLE001
                _log(f"  write probe                           FAILED: {exc}")
                info["write_probe"] = False
    _log("=" * 68)
    return info


# ---------------------------------------------------------------------------
# Recover
# ---------------------------------------------------------------------------

def _phase(name: str, fn) -> bool:
    """Run one recovery phase, logging outcome; never raises."""
    _log(f"\n--- {name} ---")
    try:
        fn()
        _log(f"    OK: {name}")
        return True
    except Exception as exc:  # noqa: BLE001
        _log(f"    FAILED: {name}: {exc}")
        return False


def recover() -> None:
    """
    Reclaim disk space so the database can leave read-only mode.

    Ordered cheapest-and-most-effective first. Each phase is independent, so a
    failure in one doesn't prevent the others from freeing space.
    """
    _log("Starting recovery…")

    # Phase 1 — TRUNCATE the unused train_positions table.
    # TRUNCATE unlinks the files outright, so space returns immediately (unlike
    # DELETE, which only marks rows dead). Nothing reads this table: the live
    # map queries the CTA API directly and training never uses it.
    def truncate_positions() -> None:
        with engine.begin() as conn:
            if not _try_make_writable(conn):
                raise RuntimeError("could not obtain write access")
            conn.execute(text("TRUNCATE TABLE train_positions"))

    _phase("Phase 1: TRUNCATE train_positions (unused)", truncate_positions)

    # Phase 2 — drop the raw_json blob column (nothing reads it).
    # Metadata-only, so it doesn't reclaim space by itself; the table rewrite in
    # phase 4 is what actually returns those bytes.
    def drop_raw_json() -> None:
        with engine.begin() as conn:
            if not _try_make_writable(conn):
                raise RuntimeError("could not obtain write access")
            conn.execute(text(
                "ALTER TABLE arrival_snapshots DROP COLUMN IF EXISTS raw_json"
            ))

    _phase("Phase 2: DROP arrival_snapshots.raw_json", drop_raw_json)

    # Phase 3 — batched delete of snapshots past the retention window.
    # Batched so no single transaction has to hold a huge amount of WAL on a
    # disk that is already full.
    def delete_old_snapshots() -> None:
        total = 0
        while True:
            with engine.begin() as conn:
                if not _try_make_writable(conn):
                    raise RuntimeError("could not obtain write access")
                result = conn.execute(text(
                    f"""
                    DELETE FROM arrival_snapshots
                    WHERE ctid IN (
                        SELECT ctid FROM arrival_snapshots
                        WHERE snapshot_time < now() - interval '{SNAPSHOT_RETENTION_DAYS} days'
                        LIMIT {DELETE_BATCH}
                    )
                    """
                ))
                deleted = result.rowcount or 0
            total += deleted
            if deleted:
                _log(f"    deleted {total:,} rows so far…")
            if deleted < DELETE_BATCH:
                break
        _log(f"    deleted {total:,} old snapshot rows")

    _phase("Phase 3: DELETE snapshots older than retention", delete_old_snapshots)

    # Phase 4 — rewrite the table to actually return the freed bytes to disk.
    # VACUUM FULL needs its own connection outside a transaction. It also needs
    # scratch space roughly the size of the live data, which phases 1-3 should
    # have made available.
    def vacuum_snapshots() -> None:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            try:
                conn.execute(text("SET default_transaction_read_only = off"))
            except Exception:  # noqa: BLE001 — may already be writable
                pass
            conn.execute(text("VACUUM FULL arrival_snapshots"))

    _phase("Phase 4: VACUUM FULL arrival_snapshots", vacuum_snapshots)

    def vacuum_positions() -> None:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            try:
                conn.execute(text("SET default_transaction_read_only = off"))
            except Exception:  # noqa: BLE001
                pass
            conn.execute(text("VACUUM FULL train_positions"))

    _phase("Phase 5: VACUUM FULL train_positions", vacuum_positions)

    _log("\nRecovery finished — re-running diagnosis:\n")
    diagnose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Database diagnostics and recovery")
    parser.add_argument("action", choices=["diagnose", "recover"])
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required for 'recover' — confirms destructive space reclamation",
    )
    args = parser.parse_args()

    if args.action == "diagnose":
        diagnose()
        return

    if not args.yes:
        raise SystemExit("recover is destructive — pass --yes to confirm")
    recover()


if __name__ == "__main__":
    main()
