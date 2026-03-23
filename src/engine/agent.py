from __future__ import annotations

import logging
from typing import Optional

from langchain_openai import ChatOpenAI

from ..config import Settings
from ..database.connection import DatabaseConnection
from ..database.repository import ProductRepository
from ..data_loader.loader import DataLoader
from ..models.schemas import RecommendationInput, RecommendationOutput
from .steps.category_selector import CategorySelector
from .steps.hard_filter import HardFilter
from .steps.output_assembler import OutputAssembler
from .steps.preference_extractor import PreferenceExtractor
from .steps.query_constructor import QueryConstructor
from .steps.recommendation_writer import RecommendationWriter
from .steps.weighted_ranker import WeightedRanker

logger = logging.getLogger(__name__)


class InsuranceRecommendationAgent:
    """Insurance product recommendation engine with 5-step pipeline.

    Pipeline:
        1. CategorySelector — AI selects insurance category
        2. QueryConstructor + HardFilter — AI generates SQL scoped to category
        3. PreferenceExtractor + WeightedRanker — AI weights → deterministic ranking
        4. RecommendationWriter — AI writes professional reasoning
        5. OutputAssembler — pack results

    Usage::

        agent = InsuranceRecommendationAgent(settings)
        agent.load_data()                       # once, or on data refresh
        result = agent.recommend(input_data)     # each call is independent
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or Settings.from_env()
        self._db = DatabaseConnection(self._settings.db_path)
        self._repo = ProductRepository(self._db)
        self._llm = self._build_llm()
        self._methodology_text = self._load_methodology()

        self._category_selector = CategorySelector(
            self._llm, self._methodology_text
        )
        self._query_ctor = QueryConstructor(self._llm, self._repo)
        self._hard_filter = HardFilter(self._repo)
        self._preference_extractor = PreferenceExtractor(self._llm)
        self._weighted_ranker = WeightedRanker(
            self._repo, top_k=self._settings.top_k_ranked
        )
        self._recommendation_writer = RecommendationWriter(
            self._llm, self._repo, self._methodology_text
        )

    # ── public API ────────────────────────────────────────────────

    def load_data(self, force_reload: bool = False) -> None:
        """(Re-)load insurance product data from the configured Excel directory."""
        loader = DataLoader(
            self._settings.data_dir,
            self._db,
            llm=self._llm,
            methodology_text=self._methodology_text,
        )
        loader.load_all(force_reload=force_reload)

    def recommend(self, input_data: RecommendationInput) -> RecommendationOutput:
        """Run the full 5-step pipeline and return structured recommendations."""
        try:
            logger.info(">>> Recommendation started | query=%s", input_data.query)

            # Step 1 – category selection
            cat_result = self._category_selector.select(input_data)
            category = cat_result.category
            logger.info(
                "Step 1 done | category=%s | confidence=%s | reason=%s",
                category, cat_result.confidence, cat_result.reasoning,
            )

            # Step 2 – query construction + hard filtering
            sql, soft_prefs = self._query_ctor.construct(
                input_data, category=category
            )
            logger.info("Step 2a done | SQL=%s | soft_prefs=%s", sql, soft_prefs)

            candidates = self._hard_filter.execute(sql)
            logger.info("Step 2b done | %d candidates", len(candidates))

            if not candidates:
                # Fallback: try all products in category
                candidates = self._repo.get_products_by_category(category)
                logger.info(
                    "Hard filter returned 0, falling back to all %d products in %s",
                    len(candidates), category,
                )

            if not candidates:
                return OutputAssembler.failure(
                    "没有找到符合条件的保险产品，请尝试放宽筛选条件。"
                )

            # Step 3 – preference extraction + weighted ranking
            weights = self._preference_extractor.extract(input_data)
            logger.info(
                "Step 3a done | weights=%s",
                {w.group: w.weight for w in weights},
            )

            ranked = self._weighted_ranker.rank(candidates, weights, category)
            logger.info(
                "Step 3b done | %d ranked products", len(ranked),
            )

            if not ranked:
                return OutputAssembler.failure(
                    "加权排序阶段未能返回有效结果，请重试。"
                )

            # Step 4 – recommendation writing
            recommendations = self._recommendation_writer.write(
                ranked, input_data, category, weights
            )
            logger.info("Step 4 done | %d recommendations", len(recommendations))

            # Step 5 – assemble output
            result = OutputAssembler.success(recommendations)
            logger.info(
                ">>> Recommendation complete | %d products returned",
                len(result.recommendations),
            )
            return result

        except Exception as exc:
            logger.exception("Recommendation pipeline error")
            return OutputAssembler.failure(str(exc))

    def close(self) -> None:
        self._db.close()

    # ── private ───────────────────────────────────────────────────

    def _build_llm(self) -> ChatOpenAI:
        kwargs: dict = {
            "model": self._settings.llm_model,
            "api_key": self._settings.llm_api_key,
            "temperature": self._settings.llm_temperature,
        }
        if self._settings.llm_base_url:
            kwargs["base_url"] = self._settings.llm_base_url
        return ChatOpenAI(**kwargs)

    def _load_methodology(self) -> str:
        path = self._settings.methodology_doc_path
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Failed to read methodology doc: %s", path)
        return ""
