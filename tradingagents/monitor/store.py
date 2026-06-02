"""
SQLite-backed shared state for watchlist + analysis results.

Shared between the FastAPI dashboard process and the standalone worker
(`python -m tradingagents.monitor.worker`). Uses WAL mode so concurrent
readers and a single writer per table coexist safely.

Pattern inspired by HKUDS/AI-Trader's service/server/database.py, simplified
to stdlib SQLite (no Postgres, no Redis) to fit the single-machine TradingAgents
deployment.

Override path with `TRADINGAGENTS_STORE_PATH`; defaults to
`~/.tradingagents/store.sqlite3`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".tradingagents", "store.sqlite3"
)


def _db_path() -> str:
    return os.environ.get("TRADINGAGENTS_STORE_PATH", DEFAULT_DB_PATH)


_INIT_LOCK = threading.Lock()
_INITIALISED_PATHS: set[str] = set()


def _connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS watchlist_entries (
            symbol TEXT PRIMARY KEY,
            display_name TEXT,
            mode TEXT,
            interval_hours INTEGER,
            analysts TEXT,
            use_tradingview INTEGER,
            enabled INTEGER DEFAULT 1,
            last_analysis TEXT,
            last_decision TEXT,
            last_signal TEXT
        );
        CREATE TABLE IF NOT EXISTS analysis_results (
            symbol TEXT PRIMARY KEY,
            success INTEGER,
            signal TEXT,
            decision_text TEXT,
            error TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            signal TEXT NOT NULL,
            decision_text TEXT,
            success INTEGER NOT NULL,
            error TEXT,
            params_snapshot TEXT,
            horizon_hours INTEGER NOT NULL,
            decided_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_symbol_ts
            ON decisions(symbol, decided_at);
        CREATE INDEX IF NOT EXISTS idx_decisions_decided_at
            ON decisions(decided_at);
        CREATE TABLE IF NOT EXISTS analysis_traces (
            decision_id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            trace TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (decision_id) REFERENCES decisions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_traces_symbol
            ON analysis_traces(symbol, created_at);
        CREATE TABLE IF NOT EXISTS decision_outcomes (
            decision_id INTEGER PRIMARY KEY,
            entry_price REAL,
            exit_price REAL,
            pnl_pct REAL,
            horizon_hours INTEGER,
            evaluated_at TEXT NOT NULL,
            error TEXT,
            FOREIGN KEY (decision_id) REFERENCES decisions(id)
        );
        CREATE TABLE IF NOT EXISTS learned_params_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            params TEXT NOT NULL,
            diff TEXT,
            rationale TEXT,
            applied INTEGER DEFAULT 0,
            proposed_at TEXT NOT NULL,
            applied_at TEXT
        );
        """
    )
    _migrate_proposal_lifecycle(conn)


def _migrate_proposal_lifecycle(conn: sqlite3.Connection) -> None:
    """Add rejected_at / rejection_reason columns to older databases.

    SQLite supports ADD COLUMN for nullable columns without defaults. We
    catch OperationalError so re-running on an already-migrated DB is a no-op.
    """
    for ddl in (
        "ALTER TABLE learned_params_history ADD COLUMN rejected_at TEXT",
        "ALTER TABLE learned_params_history ADD COLUMN rejection_reason TEXT",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            # Column already exists.
            pass


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    with _INIT_LOCK:
        if path not in _INITIALISED_PATHS:
            init_conn = _connect(path)
            try:
                _init_schema(init_conn)
            finally:
                init_conn.close()
            _INITIALISED_PATHS.add(path)
    conn = _connect(path)
    try:
        yield conn
    finally:
        conn.close()


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


# ─── Watchlist ─────────────────────────────────────────────────────────────


def save_watchlist_entry(entry: Any) -> None:
    """Insert or replace an entry. `entry` is a WatchlistEntry dataclass."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist_entries "
            "(symbol, display_name, mode, interval_hours, analysts, use_tradingview, "
            " enabled, last_analysis, last_decision, last_signal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.symbol.upper(),
                entry.display_name,
                entry.mode,
                int(entry.interval_hours),
                json.dumps(entry.analysts),
                1 if entry.use_tradingview else 0,
                1 if entry.enabled else 0,
                entry.last_analysis.isoformat() if entry.last_analysis else None,
                entry.last_decision,
                entry.last_signal,
            ),
        )


def delete_watchlist_entry(symbol: str) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM watchlist_entries WHERE symbol = ?", (symbol.upper(),)
        )
        return cur.rowcount > 0


def load_watchlist_rows() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM watchlist_entries").fetchall()
    return [_row_to_entry_dict(row) for row in rows]


def get_watchlist_row(symbol: str) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM watchlist_entries WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
    return _row_to_entry_dict(row) if row else None


def watchlist_count() -> int:
    with _conn() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM watchlist_entries")
        return int(cur.fetchone()[0])


def _row_to_entry_dict(row: sqlite3.Row) -> dict[str, Any]:
    try:
        analysts = json.loads(row["analysts"]) if row["analysts"] else []
    except (TypeError, ValueError, json.JSONDecodeError):
        analysts = []
    return {
        "symbol": row["symbol"],
        "display_name": row["display_name"],
        "mode": row["mode"],
        "interval_hours": int(row["interval_hours"]) if row["interval_hours"] is not None else 0,
        "analysts": analysts,
        "use_tradingview": bool(row["use_tradingview"]),
        "enabled": bool(row["enabled"]),
        "last_analysis": _parse_dt(row["last_analysis"]),
        "last_decision": row["last_decision"],
        "last_signal": row["last_signal"],
    }


# ─── Analysis results ─────────────────────────────────────────────────────


def save_result(result: Any) -> None:
    """Insert or replace the latest result for a symbol. `result` is AnalysisResult."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analysis_results "
            "(symbol, success, signal, decision_text, error, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                result.symbol.upper(),
                1 if result.success else 0,
                result.signal,
                result.decision_text,
                result.error,
                result.timestamp.isoformat(),
            ),
        )


def load_results() -> dict[str, dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM analysis_results").fetchall()
    return {row["symbol"]: _row_to_result_dict(row) for row in rows}


def get_result(symbol: str) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM analysis_results WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
    return _row_to_result_dict(row) if row else None


def _row_to_result_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "success": bool(row["success"]),
        "signal": row["signal"],
        "decision_text": row["decision_text"],
        "error": row["error"],
        "timestamp": row["timestamp"],
    }


# ─── Decisions (append-only ledger) ───────────────────────────────────────


def record_decision(
    symbol: str,
    signal: str,
    decision_text: Optional[str],
    success: bool,
    horizon_hours: int,
    params_snapshot: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    decided_at: Optional[datetime] = None,
) -> int:
    """Append a decision to the ledger. Returns the new row id."""
    ts = (decided_at or datetime.now()).isoformat()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO decisions "
            "(symbol, signal, decision_text, success, error, params_snapshot, "
            " horizon_hours, decided_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol.upper(),
                signal,
                decision_text,
                1 if success else 0,
                error,
                json.dumps(params_snapshot) if params_snapshot is not None else None,
                int(horizon_hours),
                ts,
            ),
        )
        return int(cur.lastrowid)


def unevaluated_decisions(now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Decisions whose horizon has elapsed but have no outcome row yet."""
    now = now or datetime.now()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT d.* FROM decisions d "
            "LEFT JOIN decision_outcomes o ON o.decision_id = d.id "
            "WHERE o.decision_id IS NULL AND d.success = 1"
        ).fetchall()
    pending = []
    for row in rows:
        decided = _parse_dt(row["decided_at"])
        if decided is None:
            continue
        horizon_hours = int(row["horizon_hours"])
        if (now - decided).total_seconds() < horizon_hours * 3600:
            continue
        pending.append(_row_to_decision_dict(row))
    return pending


def save_outcome(
    decision_id: int,
    entry_price: Optional[float],
    exit_price: Optional[float],
    pnl_pct: Optional[float],
    horizon_hours: int,
    error: Optional[str] = None,
) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO decision_outcomes "
            "(decision_id, entry_price, exit_price, pnl_pct, horizon_hours, "
            " evaluated_at, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                int(decision_id),
                entry_price,
                exit_price,
                pnl_pct,
                int(horizon_hours),
                datetime.now().isoformat(),
                error,
            ),
        )


def recent_decisions_with_outcomes(
    since: Optional[datetime] = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Join decisions ⨝ outcomes, optionally filtered by decided_at >= since."""
    sql = (
        "SELECT d.*, o.entry_price, o.exit_price, o.pnl_pct, "
        "       o.evaluated_at, o.error AS outcome_error "
        "FROM decisions d "
        "LEFT JOIN decision_outcomes o ON o.decision_id = d.id "
    )
    params: tuple = ()
    if since is not None:
        sql += "WHERE d.decided_at >= ? "
        params = (since.isoformat(),)
    sql += "ORDER BY d.decided_at DESC LIMIT ?"
    params = params + (int(limit),)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        d = _row_to_decision_dict(row)
        d["entry_price"] = row["entry_price"]
        d["exit_price"] = row["exit_price"]
        d["pnl_pct"] = row["pnl_pct"]
        d["evaluated_at"] = row["evaluated_at"]
        d["outcome_error"] = row["outcome_error"]
        out.append(d)
    return out


def save_analysis_trace(
    decision_id: int,
    symbol: str,
    trace: dict[str, Any],
    created_at: Optional[datetime] = None,
) -> None:
    """Persist a component-level analysis trace for one decision row."""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analysis_traces "
            "(decision_id, symbol, trace, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                int(decision_id),
                symbol.upper(),
                json.dumps(trace),
                (created_at or datetime.now()).isoformat(),
            ),
        )


def get_analysis_trace(decision_id: int) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM analysis_traces WHERE decision_id = ?",
            (int(decision_id),),
        ).fetchone()
    return _row_to_trace_dict(row) if row else None


def recent_analysis_flows(limit: int = 50, symbol: Optional[str] = None) -> list[dict[str, Any]]:
    """Return recent decisions joined with their saved component traces."""
    sql = (
        "SELECT d.*, t.trace, t.created_at AS trace_created_at, "
        "       o.entry_price, o.exit_price, o.pnl_pct, "
        "       o.evaluated_at, o.error AS outcome_error "
        "FROM decisions d "
        "LEFT JOIN analysis_traces t ON t.decision_id = d.id "
        "LEFT JOIN decision_outcomes o ON o.decision_id = d.id "
    )
    params: tuple[Any, ...] = ()
    if symbol:
        sql += "WHERE d.symbol = ? "
        params = (symbol.upper(),)
    sql += "ORDER BY d.decided_at DESC LIMIT ?"
    params = params + (int(limit),)
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_flow_dict(row) for row in rows]


def _row_to_trace_dict(row: sqlite3.Row) -> dict[str, Any]:
    try:
        trace = json.loads(row["trace"]) if row["trace"] else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        trace = {}
    return {
        "decision_id": int(row["decision_id"]),
        "symbol": row["symbol"],
        "trace": trace,
        "created_at": row["created_at"],
    }


def _row_to_flow_dict(row: sqlite3.Row) -> dict[str, Any]:
    flow = _row_to_decision_dict(row)
    try:
        flow["trace"] = json.loads(row["trace"]) if row["trace"] else None
    except (TypeError, ValueError, json.JSONDecodeError):
        flow["trace"] = None
    flow["trace_created_at"] = row["trace_created_at"]
    flow["entry_price"] = row["entry_price"]
    flow["exit_price"] = row["exit_price"]
    flow["pnl_pct"] = row["pnl_pct"]
    flow["evaluated_at"] = row["evaluated_at"]
    flow["outcome_error"] = row["outcome_error"]
    return flow


def _row_to_decision_dict(row: sqlite3.Row) -> dict[str, Any]:
    try:
        params = json.loads(row["params_snapshot"]) if row["params_snapshot"] else None
    except (TypeError, ValueError, json.JSONDecodeError):
        params = None
    return {
        "id": int(row["id"]),
        "symbol": row["symbol"],
        "signal": row["signal"],
        "decision_text": row["decision_text"],
        "success": bool(row["success"]),
        "error": row["error"],
        "params_snapshot": params,
        "horizon_hours": int(row["horizon_hours"]),
        "decided_at": row["decided_at"],
    }


# ─── Learned-params history ───────────────────────────────────────────────


def record_params_proposal(
    params: dict[str, Any],
    diff: Optional[dict[str, Any]],
    rationale: Optional[str],
    applied: bool = False,
) -> int:
    now = datetime.now().isoformat()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO learned_params_history "
            "(params, diff, rationale, applied, proposed_at, applied_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                json.dumps(params),
                json.dumps(diff) if diff is not None else None,
                rationale,
                1 if applied else 0,
                now,
                now if applied else None,
            ),
        )
        return int(cur.lastrowid)


def latest_params_proposal() -> Optional[dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM learned_params_history "
            "ORDER BY proposed_at DESC LIMIT 1"
        ).fetchone()
    return _row_to_proposal_dict(row) if row else None


def _row_to_proposal_dict(row: sqlite3.Row) -> dict[str, Any]:
    try:
        params = json.loads(row["params"]) if row["params"] else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        params = {}
    try:
        diff = json.loads(row["diff"]) if row["diff"] else None
    except (TypeError, ValueError, json.JSONDecodeError):
        diff = None
    keys = row.keys() if hasattr(row, "keys") else []
    return {
        "id": int(row["id"]),
        "params": params,
        "diff": diff,
        "rationale": row["rationale"],
        "applied": bool(row["applied"]),
        "proposed_at": row["proposed_at"],
        "applied_at": row["applied_at"],
        "rejected_at": row["rejected_at"] if "rejected_at" in keys else None,
        "rejection_reason": row["rejection_reason"] if "rejection_reason" in keys else None,
    }


def list_proposals(
    status: str = "all",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return proposals filtered by status: pending|applied|rejected|all."""
    status = status.lower().strip()
    where = ""
    if status == "pending":
        where = "WHERE applied = 0 AND rejected_at IS NULL "
    elif status == "applied":
        where = "WHERE applied = 1 "
    elif status == "rejected":
        where = "WHERE rejected_at IS NOT NULL "
    sql = (
        "SELECT * FROM learned_params_history "
        + where
        + "ORDER BY proposed_at DESC LIMIT ?"
    )
    with _conn() as conn:
        rows = conn.execute(sql, (int(limit),)).fetchall()
    return [_row_to_proposal_dict(row) for row in rows]


def pending_proposals(limit: int = 50) -> list[dict[str, Any]]:
    return list_proposals(status="pending", limit=limit)


def get_proposal(proposal_id: int) -> Optional[dict[str, Any]]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM learned_params_history WHERE id = ?",
            (int(proposal_id),),
        ).fetchone()
    return _row_to_proposal_dict(row) if row else None


class ProposalNotFound(Exception):
    pass


class ProposalAlreadyResolved(Exception):
    pass


def apply_proposal(proposal_id: int) -> dict[str, Any]:
    """Mark proposal applied and persist its params via learning_config.

    Raises ProposalNotFound / ProposalAlreadyResolved.
    Returns the new live learned_params dict.
    """
    from tradingagents.monitor import learning_config

    proposal = get_proposal(proposal_id)
    if not proposal:
        raise ProposalNotFound(f"proposal id={proposal_id}")
    if proposal["applied"]:
        raise ProposalAlreadyResolved(f"proposal id={proposal_id} already applied")
    if proposal["rejected_at"]:
        raise ProposalAlreadyResolved(f"proposal id={proposal_id} already rejected")

    new_params = proposal["params"]
    learning_config.save_learned_params(new_params)
    now = datetime.now().isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE learned_params_history "
            "SET applied = 1, applied_at = ?, rejected_at = NULL, rejection_reason = NULL "
            "WHERE id = ?",
            (now, int(proposal_id)),
        )
    return new_params


def reject_proposal(proposal_id: int, reason: Optional[str] = None) -> dict[str, Any]:
    proposal = get_proposal(proposal_id)
    if not proposal:
        raise ProposalNotFound(f"proposal id={proposal_id}")
    if proposal["applied"]:
        raise ProposalAlreadyResolved(f"proposal id={proposal_id} already applied")
    if proposal["rejected_at"]:
        raise ProposalAlreadyResolved(f"proposal id={proposal_id} already rejected")

    now = datetime.now().isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE learned_params_history "
            "SET rejected_at = ?, rejection_reason = ? "
            "WHERE id = ?",
            (now, reason, int(proposal_id)),
        )
    refreshed = get_proposal(proposal_id)
    return refreshed or {}
