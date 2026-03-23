from __future__ import annotations

import logging

from ...database.repository import ProductRepository

logger = logging.getLogger(__name__)


class HardFilter:
    """Step 2 – execute the LLM-generated SQL to narrow candidates."""

    def __init__(self, repository: ProductRepository):
        self._repo = repository

    def execute(self, sql_query: str) -> list[dict]:
        """Run *sql_query* and return matching product rows.

        On any SQL error the filter degrades gracefully by returning
        **all** products so the soft-scoring stage can still operate.
        """
        try:
            results = self._repo.execute_query(sql_query)
            logger.info("Hard filter matched %d products", len(results))
            return results
        except Exception as exc:
            logger.error(
                "Hard filter SQL failed (%s), returning all products", exc
            )
            return self._repo.get_all_products()
