from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class DatabaseConnection:
    """Thread-safe SQLite connection manager.

    Each thread gets its own connection via ``threading.local()``.
    """

    _local = threading.local()

    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)

    def get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None

    def init_tables(self) -> None:
        conn = self.get_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT    NOT NULL,
                category     TEXT    NOT NULL,
                source_file  TEXT    NOT NULL,
                UNIQUE(product_name, category)
            );

            CREATE TABLE IF NOT EXISTS field_metadata (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT NOT NULL,
                field_type TEXT NOT NULL CHECK(field_type IN ('hard', 'soft')),
                data_type  TEXT NOT NULL,
                category   TEXT NOT NULL,
                field_group TEXT,
                UNIQUE(field_name, category)
            );

            CREATE TABLE IF NOT EXISTS product_values (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id    INTEGER NOT NULL,
                field_name    TEXT    NOT NULL,
                field_type    TEXT    NOT NULL CHECK(field_type IN ('hard', 'soft')),
                field_group   TEXT,
                value_text    TEXT,
                value_numeric REAL,
                value_boolean INTEGER,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                UNIQUE(product_id, field_name)
            );

            CREATE TABLE IF NOT EXISTS group_scores (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id      INTEGER NOT NULL,
                field_group     TEXT    NOT NULL,
                score           REAL    NOT NULL,
                score_reasoning TEXT,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                UNIQUE(product_id, field_group)
            );

            CREATE INDEX IF NOT EXISTS idx_pv_field
                ON product_values(field_name, field_type);
            CREATE INDEX IF NOT EXISTS idx_pv_product
                ON product_values(product_id);
            CREATE INDEX IF NOT EXISTS idx_pv_group
                ON product_values(field_group);
            CREATE INDEX IF NOT EXISTS idx_gs_product
                ON group_scores(product_id);
            """
        )
        conn.commit()
