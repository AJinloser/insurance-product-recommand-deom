from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ...database.repository import ProductRepository
from ...models.schemas import RecommendationInput
from ..prompts import QUERY_CONSTRUCTOR_SYSTEM, QUERY_CONSTRUCTOR_USER

logger = logging.getLogger(__name__)

_DANGEROUS_KEYWORDS = frozenset({
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE",
})


class QueryConstructor:
    """Step 2a — use an LLM to extract constraints and emit a SQL query."""

    def __init__(self, llm: BaseChatModel, repository: ProductRepository):
        self._llm = llm
        self._repo = repository

    def construct(
        self,
        input_data: RecommendationInput,
        category: Optional[str] = None,
    ) -> tuple[str, list[str]]:
        """Return ``(sql_query, soft_preferences_list)``."""
        schema = self._repo.get_schema_description(category)

        category_hint = ""
        if category:
            category_hint = (
                f"\n\n**重要**：用户已选择产品类别「{category}」，"
                f"SQL 必须包含 `WHERE p.category = '{category}'` 条件，"
                f"仅在该类别范围内筛选。"
            )

        user_msg = QUERY_CONSTRUCTOR_USER.format(
            schema_description=schema,
            category_hint=category_hint,
            user_profile=input_data.user_profile.model_dump_json(
                indent=2, exclude_none=True
            ),
            dialogue_history=json.dumps(
                input_data.dialogue_history, ensure_ascii=False, indent=2
            ),
            query=input_data.query,
        )

        resp = self._llm.invoke([
            SystemMessage(content=QUERY_CONSTRUCTOR_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        return self._parse(resp.content)

    # ── helpers ───────────────────────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        body = text
        if "```json" in body:
            body = body.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in body:
            body = body.split("```", 1)[1].split("```", 1)[0]
        return json.loads(body.strip())

    @classmethod
    def _parse(cls, content: str) -> tuple[str, list[str]]:
        fallback_sql = "SELECT id, product_name, category FROM products"
        try:
            parsed = cls._extract_json(content)

            sql: str = parsed.get("sql_query", fallback_sql)
            upper = sql.upper().strip()
            if not upper.startswith("SELECT"):
                sql = fallback_sql
            if any(kw in upper for kw in _DANGEROUS_KEYWORDS):
                logger.warning("Blocked dangerous SQL from LLM: %s", sql)
                sql = fallback_sql

            prefs = [
                p["description"]
                for p in parsed.get("soft_preferences", [])
                if p.get("description")
            ]
            return sql, prefs
        except Exception as exc:
            logger.warning("LLM response parse failed, using fallback: %s", exc)
            return fallback_sql, []
