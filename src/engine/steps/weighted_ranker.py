from __future__ import annotations

import logging

from ...database.repository import ProductRepository
from ...models.schemas import GroupWeight, RankedProduct

logger = logging.getLogger(__name__)


class WeightedRanker:
    """Step 3b — deterministic weighted ranking (no LLM call).

    Computes ``final_score = sum(weight[group] * group_score[product][group])``
    for each candidate product and returns the top-K sorted by score.
    """

    def __init__(self, repository: ProductRepository, top_k: int = 3):
        self._repo = repository
        self._top_k = top_k

    def rank(
        self,
        candidates: list[dict],
        weights: list[GroupWeight],
        category: str,
    ) -> list[RankedProduct]:
        weight_map = {w.group: w.weight for w in weights}

        # Fetch all group scores for the category
        all_scores = self._repo.get_group_scores_by_category(category)
        # Build: {product_id: {group: score}}
        score_map: dict[int, dict[str, float]] = {}
        for row in all_scores:
            pid = row["product_id"]
            score_map.setdefault(pid, {})[row["field_group"]] = row["score"]

        candidate_ids = {
            c.get("id") or c.get("product_id") for c in candidates
        }

        ranked: list[RankedProduct] = []
        for c in candidates:
            pid = c.get("id") or c.get("product_id")
            if pid not in candidate_ids:
                continue
            name = c.get("product_name", "未知")

            product_scores = score_map.get(pid, {})
            final_score = 0.0
            group_details: dict[str, float] = {}

            for group, weight in weight_map.items():
                gs = product_scores.get(group, 50.0)  # default 50 if missing
                contribution = weight * gs
                final_score += contribution
                group_details[group] = round(gs, 1)

            ranked.append(RankedProduct(
                product_id=pid,
                product_name=name,
                final_score=round(final_score, 2),
                group_scores=group_details,
            ))

        ranked.sort(key=lambda x: x.final_score, reverse=True)
        result = ranked[: self._top_k]

        logger.info(
            "Weighted ranking: %s",
            [(r.product_name, r.final_score) for r in result],
        )
        return result
