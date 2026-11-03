import sqlite3
from datetime import datetime, timezone


class HistoryDB:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dtc_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                description TEXT NOT NULL,
                vin TEXT,
                first_seen TEXT NOT NULL,
                cleared_at TEXT,
                notes TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                vin TEXT PRIMARY KEY,
                make TEXT NOT NULL,
                model TEXT NOT NULL,
                year TEXT NOT NULL,
                decoded_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record_active_codes(self, codes: list[tuple[str, str]], vin: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = {
            row["code"]
            for row in self._conn.execute("SELECT code FROM dtc_events WHERE cleared_at IS NULL")
        }
        for code, description in codes:
            if code not in existing:
                self._conn.execute(
                    "INSERT INTO dtc_events (code, description, vin, first_seen, cleared_at, notes) "
                    "VALUES (?, ?, ?, ?, NULL, '')",
                    (code, description, vin, now),
                )
        self._conn.commit()

    def active_events(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT e.id, e.code, e.description, e.vin, e.first_seen, e.cleared_at, e.notes,
                   v.make, v.model, v.year
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            WHERE e.cleared_at IS NULL
            ORDER BY e.first_seen
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def clear_active_events(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("UPDATE dtc_events SET cleared_at = ? WHERE cleared_at IS NULL", (now,))
        self._conn.commit()

    def set_notes(self, event_id: int, notes: str) -> bool:
        cur = self._conn.execute("UPDATE dtc_events SET notes = ? WHERE id = ?", (notes, event_id))
        self._conn.commit()
        return cur.rowcount > 0

    def vehicles_view(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT DISTINCT e.vin AS vin, v.make, v.model, v.year, v.decoded_at
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            WHERE e.vin IS NOT NULL
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def upsert_vehicle(self, vin: str, make: str, model: str, year: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO vehicles (vin, make, model, year, decoded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(vin) DO UPDATE SET
                make = excluded.make,
                model = excluded.model,
                year = excluded.year,
                decoded_at = excluded.decoded_at
            """,
            (vin, make, model, year, now),
        )
        self._conn.commit()
