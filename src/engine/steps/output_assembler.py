from __future__ import annotations

from ...models.schemas import (
    ProductRecommendation,
    RecommendationOutput,
)


class OutputAssembler:
    """Step 4 – pack scored results into the public output contract."""

    @staticmethod
    def success(scored: list[dict]) -> RecommendationOutput:
        return RecommendationOutput(
            status="success",
            recommendations=[
                ProductRecommendation(
                    product_id=p.get("product_id", 0),
                    product_name=p.get("product_name", ""),
                    recommendation_reason=p.get("recommendation_reason", ""),
                )
                for p in scored
            ],
        )

    @staticmethod
    def failure(message: str) -> RecommendationOutput:
        return RecommendationOutput(
            status="failed",
            recommendations=[],
            error_message=message,
        )
