from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ..database.repository import ProductRepository
from ..engine.prompts import GROUP_SCORER_SYSTEM, GROUP_SCORER_USER

logger = logging.getLogger(__name__)


class GroupScorer:
    """Score products on each field group dimension at data-load time.

    For each (category, group) pair, sends all products' field values to the
    LLM and receives a competitiveness score (1-100) per product.  Results
    are cached in the ``group_scores`` table.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        repo: ProductRepository,
        methodology_text: str = "",
    ) -> None:
        self._llm = llm
        self._repo = repo
        self._methodology_text = methodology_text

    def score_category(self, category: str, groups: list[str]) -> None:
        """Score all products in *category* across each group."""
        products = self._repo.get_products_by_category(category)
        if not products:
            logger.warning("No products found for category %s", category)
            return

        self._repo.clear_group_scores(category)

        for group in groups:
            try:
                self._score_group(category, group, products)
            except Exception:
                logger.exception(
                    "Failed to score group %s for category %s",
                    group, category,
                )

    def _score_group(
        self, category: str, group: str, products: list[dict]
    ) -> None:
        # Build product info for this group
        product_info_parts: list[str] = []
        for p in products:
            pid = p["id"]
            name = p["product_name"]
            values = self._repo.get_product_values_by_group(pid, group)
            if not values:
                continue
            lines = [f"### 产品 ID:{pid} — {name}"]
            for v in values:
                txt = v.get("value_text")
                if txt:
                    lines.append(f"  - {v['field_name']}: {txt}")
            product_info_parts.append("\n".join(lines))

        if not product_info_parts:
            logger.info(
                "No field values for group %s in category %s, skipping",
                group, category,
            )
            return

        product_info = "\n\n".join(product_info_parts)

        user_msg = GROUP_SCORER_USER.format(
            category=category,
            group_name=group,
            methodology=self._methodology_text or "（未提供方法论文档）",
            products_info=product_info,
        )

        resp = self._llm.invoke([
            SystemMessage(content=GROUP_SCORER_SYSTEM),
            HumanMessage(content=user_msg),
        ])

        self._parse_and_store(resp.content, group)

    def _parse_and_store(self, content: str, group: str) -> None:
        try:
            body = content
            if "```json" in body:
                body = body.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in body:
                body = body.split("```", 1)[1].split("```", 1)[0]

            parsed = json.loads(body.strip())
            scores = parsed.get("scores", [])

            for item in scores:
                product_id = item.get("product_id")
                score = item.get("score", 50)
                reasoning = item.get("reasoning", "")
                if product_id is not None:
                    self._repo.insert_group_score(
                        product_id, group, float(score), reasoning
                    )

            logger.info(
                "Stored %d group scores for group '%s'",
                len(scores), group,
            )
        except Exception as exc:
            logger.error(
                "Failed to parse group scorer response for '%s': %s",
                group, exc,
            )
