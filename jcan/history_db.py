import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SEED_DATA_PATH = Path(__file__).parent / "seed_data" / "dtc_codes.json"


class HistoryDB:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed_dtc_reference()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dtc_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
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
                raw_json TEXT NOT NULL DEFAULT '{}',
                decoded_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dtc_reference (
                code TEXT NOT NULL,
                make TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL,
                PRIMARY KEY (code, make)
            )
            """
        )
        self._conn.commit()

    def _seed_dtc_reference(self) -> None:
        entries = json.loads(SEED_DATA_PATH.read_text())
        self._conn.execute("DELETE FROM dtc_reference")
        for entry in entries:
            self._conn.execute(
                "INSERT INTO dtc_reference (code, make, description) VALUES (?, ?, ?)",
                (entry["code"], entry.get("make", ""), entry["description"]),
            )
        self._conn.commit()

    def record_active_codes(self, codes: list[str], vin: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = {
            row["code"]
            for row in self._conn.execute("SELECT code FROM dtc_events WHERE cleared_at IS NULL")
        }
        for code in codes:
            if code not in existing:
                self._conn.execute(
                    "INSERT INTO dtc_events (code, vin, first_seen, cleared_at, notes) "
                    "VALUES (?, ?, ?, NULL, '')",
                    (code, vin, now),
                )
                existing.add(code)
        self._conn.commit()

    def active_events(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT e.id, e.code, e.vin, e.first_seen, e.cleared_at, e.notes,
                   v.make, v.model, v.year,
                   COALESCE(specific.description, generic.description, 'Unknown DTC') AS description
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            LEFT JOIN dtc_reference specific ON specific.code = e.code AND specific.make = v.make
            LEFT JOIN dtc_reference generic ON generic.code = e.code AND generic.make = ''
            WHERE e.cleared_at IS NULL
            ORDER BY e.first_seen, e.id
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def all_events(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT e.id, e.code, e.vin, e.first_seen, e.cleared_at, e.notes,
                   v.make, v.model, v.year,
                   COALESCE(specific.description, generic.description, 'Unknown DTC') AS description
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            LEFT JOIN dtc_reference specific ON specific.code = e.code AND specific.make = v.make
            LEFT JOIN dtc_reference generic ON generic.code = e.code AND generic.make = ''
            ORDER BY e.first_seen DESC, e.id DESC
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
            SELECT DISTINCT e.vin AS vin, v.make, v.model, v.year, v.raw_json, v.decoded_at
            FROM dtc_events e
            LEFT JOIN vehicles v ON v.vin = e.vin
            WHERE e.vin IS NOT NULL
            """
        )
        return [dict(row) for row in cur.fetchall()]

    def upsert_vehicle(self, vin: str, make: str, model: str, year: str, raw_json: str = "{}") -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO vehicles (vin, make, model, year, raw_json, decoded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(vin) DO UPDATE SET
                make = excluded.make,
                model = excluded.model,
                year = excluded.year,
                raw_json = excluded.raw_json,
                decoded_at = excluded.decoded_at
            """,
            (vin, make, model, year, raw_json, now),
        )
        self._conn.commit()
