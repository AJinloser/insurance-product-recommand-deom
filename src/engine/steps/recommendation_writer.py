from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ...database.repository import ProductRepository
from ...models.schemas import GroupWeight, RankedProduct, RecommendationInput
from ..prompts import RECOMMENDATION_WRITER_SYSTEM, RECOMMENDATION_WRITER_USER

logger = logging.getLogger(__name__)


class RecommendationWriter:
    """Step 4 — write professional recommendation reasoning for top-K products."""

    def __init__(
        self,
        llm: BaseChatModel,
        repository: ProductRepository,
        methodology_text: str = "",
    ):
        self._llm = llm
        self._repo = repository
        self._methodology_text = methodology_text

    def write(
        self,
        ranked: list[RankedProduct],
        input_data: RecommendationInput,
        category: str,
        weights: list[GroupWeight],
    ) -> list[dict[str, Any]]:
        if not ranked:
            return []

        products_info = self._build_info(ranked)
        weights_info = "\n".join(
            f"  - {w.group}: {w.weight:.0%}" for w in weights
        )

        user_msg = RECOMMENDATION_WRITER_USER.format(
            methodology=self._methodology_text or "（未提供方法论文档）",
            category=category,
            user_profile=input_data.user_profile.model_dump_json(
                indent=2, exclude_none=True
            ),
            dialogue_history=json.dumps(
                input_data.dialogue_history, ensure_ascii=False, indent=2
            ),
            query=input_data.query,
            weights_info=weights_info,
            products_info=products_info,
        )

        resp = self._llm.invoke([
            SystemMessage(content=RECOMMENDATION_WRITER_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        return self._parse(resp.content, ranked)

    def _build_info(self, ranked: list[RankedProduct]) -> str:
        parts: list[str] = []
        for r in ranked:
            pid = r.product_id
            parts.append(
                f"\n### 产品 ID:{pid} — {r.product_name} "
                f"（综合得分: {r.final_score}）"
            )
            # Group score breakdown
            parts.append("  维度得分:")
            for group, score in r.group_scores.items():
                parts.append(f"    - {group}: {score}")

            # Full product details
            for v in self._repo.get_product_all_values(pid):
                txt = v["value_text"]
                if txt:
                    group_tag = f"[{v['field_group']}] " if v.get("field_group") else ""
                    parts.append(f"  - {group_tag}{v['field_name']}: {txt}")

        return "\n".join(parts)

    @staticmethod
    def _parse(
        content: str, ranked: list[RankedProduct]
    ) -> list[dict[str, Any]]:
        try:
            body = content
            if "```json" in body:
                body = body.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in body:
                body = body.split("```", 1)[1].split("```", 1)[0]

            parsed = json.loads(body.strip())
            recs = parsed.get("recommendations", [])

            # Build a map from product_id to recommendation_reason
            reason_map: dict[int, str] = {}
            for rec in recs:
                pid = rec.get("product_id")
                reason = rec.get("recommendation_reason", "")
                if pid is not None:
                    reason_map[pid] = reason

            # Merge with ranked results, preserving ranking order
            result: list[dict[str, Any]] = []
            for r in ranked:
                result.append({
                    "product_id": r.product_id,
                    "product_name": r.product_name,
                    "recommendation_reason": reason_map.get(
                        r.product_id,
                        f"综合评分 {r.final_score} 分，推荐使用。",
                    ),
                })

            return result
        except Exception as exc:
            logger.error("Recommendation writer parse failed: %s", exc)
            # Fallback: use basic reasoning from scores
            return [
                {
                    "product_id": r.product_id,
                    "product_name": r.product_name,
                    "recommendation_reason": (
                        f"综合评分 {r.final_score} 分，推荐使用。"
                    ),
                }
                for r in ranked
            ]
