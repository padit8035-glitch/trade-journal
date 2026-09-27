"""SQLite trade journal. CSV import, stdlib only.

Trust boundary is the CSV: every row is validated, bad rows are reported and
skipped rather than silently inserted.
"""

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id        INTEGER PRIMARY KEY,
    opened_at TEXT NOT NULL,
    symbol    TEXT NOT NULL,
    side      TEXT NOT NULL CHECK (side IN ('long', 'short')),
    "exit"    REAL NOT NULL,
    entry     REAL NOT NULL CHECK (entry > 0),
    size      REAL NOT NULL CHECK (size  > 0),
    stop      REAL CHECK (stop IS NULL OR stop > 0),
    fees      REAL NOT NULL DEFAULT 0,
    notes     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_trades_opened ON trades(opened_at);
"""

# Acceptance order, and the header a user's CSV must provide.
COLUMNS = ("opened_at", "symbol", "side", "entry", "exit", "size", "stop", "fees", "notes")

_SIDES = ("long", "short")
_DATES = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y")


def connect(path="journal.db"):
    """Open (and create) a journal database."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _date(raw, field):
    raw = raw.strip()
    for fmt in _DATES:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise ValueError(f"{field}={raw!r} is not a recognised date") from None


def _num(raw, field, required=True):
    raw = (raw or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{field} is required")
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{field}={raw!r} is not a number") from None


def parse_row(row, row_no):
    """Validate one CSV row into a trade dict.

    Every ValueError leaves here carrying the row number, so callers and users
    always know which line to fix. Raises ValueError on the first bad field.
    """
    try:
        return _parse_row(row, row_no)
    except ValueError as exc:
        # Prefix once, at the boundary, rather than at each of the five raise sites.
        if not str(exc).startswith(f"row {row_no}:"):
            raise ValueError(f"row {row_no}: {exc}") from None
        raise


def _parse_row(row, row_no):
    def need(field):
        raw = (row.get(field) or "").strip()
        if not raw:
            raise ValueError(f"row {row_no}: {field} is required")
        return raw

    side = need("side").lower()
    if side not in _SIDES:
        raise ValueError(f"side={side!r} must be 'long' or 'short'")

    trade = {
        "opened_at": _date(need("opened_at"), "opened_at").isoformat(sep=" ", timespec="seconds"),
        "symbol": need("symbol").upper(),
        "side": side,
        "entry": _num(need("entry"), "entry"),
        "exit": _num(need("exit"), "exit"),
        "size": _num(need("size"), "size"),
        "stop": _num(row.get("stop"), "stop", required=False),
        "fees": _num(row.get("fees"), "fees", required=False) or 0.0,
        "notes": (row.get("notes") or "").strip(),
    }
    for field in ("entry", "exit", "size"):
        if trade[field] <= 0:
            raise ValueError(f"{field} must be > 0, got {trade[field]}")
    return trade


def import_csv(conn, path):
    """Insert every valid row. Returns (inserted, [(row_no, reason), ...])."""
    inserted, errors = 0, []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS[:6] if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing required column(s): {', '.join(missing)}")
        for row_no, row in enumerate(reader, start=2):  # line 1 is the header
            try:
                conn.execute(
                    'INSERT INTO trades (opened_at, symbol, side, entry, "exit", size, stop, fees, notes)'
                    " VALUES (:opened_at, :symbol, :side, :entry, :exit, :size, :stop, :fees, :notes)",
                    parse_row(row, row_no),
                )
                inserted += 1
            except ValueError as exc:
                errors.append((row_no, str(exc)))
    conn.commit()
    return inserted, errors


def all_trades(conn):
    """Every trade, oldest first."""
    return list(conn.execute("SELECT * FROM trades ORDER BY opened_at, id"))
