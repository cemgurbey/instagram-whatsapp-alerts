"""SQLite state: webhook dedupe, the exclusion list, the quiet-hours queue.

Three small tables:

- ``processed_events`` — Instagram message ids already handled. Webhooks
  retry deliveries, so every event is checked here before it can alert.
- ``exclusions`` — senders that must never alert. Instagram's API does not
  expose which conversations the user muted, so this list is the manual
  mirror of the in-app mute state (seeded from EXCLUDED_SENDERS, then
  managed with ``python -m app.exclusions``).
- ``queue`` — alerts that arrived during quiet hours, flushed as one
  batch when quiet hours end.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_events (
                mid TEXT PRIMARY KEY,
                processed_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exclusions (
                sender TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                text TEXT NOT NULL,
                queued_at INTEGER NOT NULL
            );
            """
        )
        self._db.commit()

    # -- dedupe ---------------------------------------------------------
    def mark_processed(self, mid: str) -> bool:
        """Record a message id. Returns False if it was already seen."""
        cur = self._db.execute(
            "INSERT OR IGNORE INTO processed_events (mid, processed_at) VALUES (?, ?)",
            (mid, int(time.time())),
        )
        self._db.commit()
        return cur.rowcount == 1

    # -- exclusions -----------------------------------------------------
    def seed_exclusions(self, senders: tuple[str, ...]) -> None:
        self._db.executemany(
            "INSERT OR IGNORE INTO exclusions (sender) VALUES (?)",
            [(s,) for s in senders],
        )
        self._db.commit()

    def is_excluded(self, sender: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM exclusions WHERE sender = ?", (sender,)
        ).fetchone()
        return row is not None

    def add_exclusion(self, sender: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO exclusions (sender) VALUES (?)", (sender,)
        )
        self._db.commit()

    def remove_exclusion(self, sender: str) -> None:
        self._db.execute("DELETE FROM exclusions WHERE sender = ?", (sender,))
        self._db.commit()

    def list_exclusions(self) -> list[str]:
        rows = self._db.execute("SELECT sender FROM exclusions ORDER BY sender")
        return [r[0] for r in rows]

    # -- quiet-hours queue ----------------------------------------------
    def enqueue(self, sender: str, text: str) -> None:
        self._db.execute(
            "INSERT INTO queue (sender, text, queued_at) VALUES (?, ?, ?)",
            (sender, text, int(time.time())),
        )
        self._db.commit()

    def drain_queue(self) -> list[tuple[str, str]]:
        rows = self._db.execute(
            "SELECT sender, text FROM queue ORDER BY id"
        ).fetchall()
        self._db.execute("DELETE FROM queue")
        self._db.commit()
        return [(r[0], r[1]) for r in rows]

    def queue_size(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
