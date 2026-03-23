from __future__ import annotations

import sqlite3
from typing import Optional

from .connection import DatabaseConnection


class ProductRepository:
    """Data-access layer sitting on top of ``DatabaseConnection``."""

    def __init__(self, connection: DatabaseConnection):
        self._conn_mgr = connection

    @property
    def _conn(self) -> sqlite3.Connection:
        return self._conn_mgr.get_connection()

    # ── write helpers ─────────────────────────────────────────────

    def clear_source(self, source_file: str) -> None:
        self._conn.execute(
            "DELETE FROM product_values WHERE product_id IN "
            "(SELECT id FROM products WHERE source_file = ?)",
            (source_file,),
        )
        self._conn.execute(
            "DELETE FROM group_scores WHERE product_id IN "
            "(SELECT id FROM products WHERE source_file = ?)",
            (source_file,),
        )
        self._conn.execute(
            "DELETE FROM products WHERE source_file = ?", (source_file,)
        )
        self._conn.execute(
            "DELETE FROM field_metadata WHERE category IN "
            "(SELECT DISTINCT category FROM products WHERE source_file = ?)",
            (source_file,),
        )
        self._conn.execute(
            "DELETE FROM source_snapshots WHERE source_file = ?",
            (source_file,),
        )
        self._conn.commit()

    def clear_category_metadata(self, category: str) -> None:
        self._conn.execute(
            "DELETE FROM field_metadata WHERE category = ?", (category,)
        )
        self._conn.commit()

    def insert_product(
        self, name: str, category: str, source_file: str
    ) -> int:
        cur = self._conn.execute(
            "INSERT OR REPLACE INTO products "
            "(product_name, category, source_file) VALUES (?, ?, ?)",
            (name, category, source_file),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def insert_field_metadata(
        self,
        field_name: str,
        field_type: str,
        data_type: str,
        category: str,
        field_group: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO field_metadata "
            "(field_name, field_type, data_type, category, field_group) "
            "VALUES (?, ?, ?, ?, ?)",
            (field_name, field_type, data_type, category, field_group),
        )
        self._conn.commit()

    def insert_product_value(
        self,
        product_id: int,
        field_name: str,
        field_type: str,
        value_text: Optional[str],
        value_numeric: Optional[float],
        value_boolean: Optional[int],
        field_group: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO product_values "
            "(product_id, field_name, field_type, field_group, "
            "value_text, value_numeric, value_boolean) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (product_id, field_name, field_type, field_group,
             value_text, value_numeric, value_boolean),
        )
        self._conn.commit()

    # ── group score helpers ───────────────────────────────────────

    def insert_group_score(
        self,
        product_id: int,
        field_group: str,
        score: float,
        reasoning: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO group_scores "
            "(product_id, field_group, score, score_reasoning) "
            "VALUES (?, ?, ?, ?)",
            (product_id, field_group, score, reasoning),
        )
        self._conn.commit()

    def get_group_scores(self, product_id: int) -> list[dict]:
        return self.execute_query(
            "SELECT field_group, score, score_reasoning "
            "FROM group_scores WHERE product_id = ?",
            (product_id,),
        )

    def get_group_scores_by_category(self, category: str) -> list[dict]:
        return self.execute_query(
            "SELECT gs.product_id, gs.field_group, gs.score, "
            "gs.score_reasoning, p.product_name "
            "FROM group_scores gs "
            "JOIN products p ON gs.product_id = p.id "
            "WHERE p.category = ? "
            "ORDER BY gs.product_id, gs.field_group",
            (category,),
        )

    def get_products_by_category(self, category: str) -> list[dict]:
        return self.execute_query(
            "SELECT id, product_name, category, source_file "
            "FROM products WHERE category = ?",
            (category,),
        )

    def get_product_values_by_group(
        self, product_id: int, field_group: str
    ) -> list[dict]:
        return self.execute_query(
            "SELECT field_name, field_type, value_text, "
            "value_numeric, value_boolean "
            "FROM product_values "
            "WHERE product_id = ? AND field_group = ?",
            (product_id, field_group),
        )

    def clear_group_scores(self, category: str) -> None:
        self._conn.execute(
            "DELETE FROM group_scores WHERE product_id IN "
            "(SELECT id FROM products WHERE category = ?)",
            (category,),
        )
        self._conn.commit()

    def upsert_source_snapshot(
        self, source_file: str, category: str, content_hash: str
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO source_snapshots "
            "(source_file, category, content_hash) VALUES (?, ?, ?)",
            (source_file, category, content_hash),
        )
        self._conn.commit()

    def get_source_snapshots(self) -> list[dict]:
        return self.execute_query(
            "SELECT source_file, category, content_hash FROM source_snapshots"
        )

    def get_source_snapshot(self, source_file: str) -> Optional[dict]:
        rows = self.execute_query(
            "SELECT source_file, category, content_hash "
            "FROM source_snapshots WHERE source_file = ?",
            (source_file,),
        )
        return rows[0] if rows else None

    # ── read helpers ──────────────────────────────────────────────

    def execute_query(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cur = self._conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        except sqlite3.Error as exc:
            raise ValueError(f"SQL execution error: {exc}") from exc

    def get_all_products(self) -> list[dict]:
        return self.execute_query(
            "SELECT id, product_name, category, source_file FROM products"
        )

    def get_products_by_source(self, source_file: str) -> list[dict]:
        return self.execute_query(
            "SELECT id, product_name, category, source_file "
            "FROM products WHERE source_file = ?",
            (source_file,),
        )

    def get_product_by_id(self, product_id: int) -> Optional[dict]:
        rows = self.execute_query(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        )
        return rows[0] if rows else None

    def get_all_categories(self) -> list[str]:
        rows = self.execute_query(
            "SELECT DISTINCT category FROM products"
        )
        return [r["category"] for r in rows]

    def get_all_field_metadata(self) -> list[dict]:
        return self.execute_query(
            "SELECT * FROM field_metadata "
            "ORDER BY category, field_type, field_name"
        )

    def get_field_metadata_by_category(self, category: str) -> list[dict]:
        return self.execute_query(
            "SELECT * FROM field_metadata WHERE category = ? "
            "ORDER BY field_type, field_name",
            (category,),
        )

    def get_hard_field_metadata(self, category: Optional[str] = None) -> list[dict]:
        if category:
            return self.execute_query(
                "SELECT * FROM field_metadata "
                "WHERE field_type = 'hard' AND category = ?",
                (category,),
            )
        return self.execute_query(
            "SELECT * FROM field_metadata WHERE field_type = 'hard'"
        )

    def get_product_soft_values(self, product_id: int) -> list[dict]:
        return self.execute_query(
            "SELECT field_name, value_text FROM product_values "
            "WHERE product_id = ? AND field_type = 'soft' "
            "AND value_text IS NOT NULL AND value_text != ''",
            (product_id,),
        )

    def get_product_all_values(self, product_id: int) -> list[dict]:
        return self.execute_query(
            "SELECT field_name, field_type, field_group, value_text, "
            "value_numeric, value_boolean "
            "FROM product_values WHERE product_id = ?",
            (product_id,),
        )

    def get_distinct_groups(self, category: str) -> list[str]:
        rows = self.execute_query(
            "SELECT DISTINCT fm.field_group FROM field_metadata fm "
            "WHERE fm.category = ? AND fm.field_group IS NOT NULL "
            "ORDER BY fm.id",
            (category,),
        )
        return [r["field_group"] for r in rows]

    # ── schema description for LLM ───────────────────────────────

    def get_schema_description(self, category: Optional[str] = None) -> str:
        """Build a human-readable schema summary for prompt injection."""
        lines: list[str] = [
            "=== 数据库表结构 ===",
            "",
            "表 `products`  : id(INT), product_name(TEXT), category(TEXT)",
            "表 `product_values` : product_id(INT→products.id), "
            "field_name(TEXT), field_type('hard'/'soft'), field_group(TEXT), "
            "value_text(TEXT), value_numeric(REAL), value_boolean(INT 0/1)",
            "",
        ]

        hard_fields = self.get_hard_field_metadata(category)
        if hard_fields:
            lines.append("=== 可用于 SQL 过滤的硬性字段 ===")
            for f in hard_fields:
                lines.append(
                    f"  - {f['field_name']}  "
                    f"(数据类型: {f['data_type']}, 产品类别: {f['category']})"
                )
            lines.append("")

        if category:
            products = self.get_products_by_category(category)
        else:
            products = self.get_all_products()

        lines.append("=== 当前产品列表 ===")
        for p in products:
            lines.append(
                f"  - ID:{p['id']} | {p['product_name']} | "
                f"类别: {p['category']}"
            )

        return "\n".join(lines)
