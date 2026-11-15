from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from backend.config import settings


class Database:
    def __init__(self, path: str | None = None):
        self.path = path or settings.database_path
        self._lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agents (
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflows (
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                """
            )

    def upsert(self, table: str, item_id: str, payload: dict[str, Any]) -> None:
        if table not in {"agents", "workflows", "runs"}:
            raise ValueError("unsupported table")
        created = payload.get("created_at", "")
        updated = payload.get("updated_at", created)
        with self._lock, self.connect() as conn:
            conn.execute(
                f"INSERT INTO {table}(id,payload,created_at,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at",
                (item_id, json.dumps(payload, ensure_ascii=False), created, updated),
            )

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        if table not in {"agents", "workflows", "runs"}:
            raise ValueError("unsupported table")
        with self.connect() as conn:
            row = conn.execute(f"SELECT payload FROM {table} WHERE id=?", (item_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def list(self, table: str) -> list[dict[str, Any]]:
        if table not in {"agents", "workflows", "runs"}:
            raise ValueError("unsupported table")
        with self.connect() as conn:
            rows = conn.execute(f"SELECT payload FROM {table} ORDER BY updated_at DESC").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def delete(self, table: str, item_id: str) -> bool:
        if table not in {"agents", "workflows"}:
            raise ValueError("unsupported table")
        with self._lock, self.connect() as conn:
            result = conn.execute(f"DELETE FROM {table} WHERE id=?", (item_id,))
        return result.rowcount > 0

    def add_event(self, run_id: str, payload: dict[str, Any]) -> int:
        with self._lock, self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO events(run_id,payload,created_at) VALUES(?,?,?)",
                (run_id, json.dumps(payload, ensure_ascii=False), payload["created_at"]),
            )
        return int(cur.lastrowid)

    def events(self, run_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id,payload FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after_id)
            ).fetchall()
        result = []
        for row in rows:
            event = json.loads(row["payload"])
            event["event_id"] = row["id"]
            result.append(event)
        return result


db = Database()

