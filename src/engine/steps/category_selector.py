from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ...models.schemas import CategorySelection, RecommendationInput
from ..prompts import CATEGORY_SELECTOR_SYSTEM, CATEGORY_SELECTOR_USER

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = frozenset({"百万医疗险", "中端医疗保险", "高端医疗保险"})


class CategorySelector:
    """Step 1 — select the appropriate insurance category via LLM."""

    def __init__(self, llm: BaseChatModel, methodology_text: str = ""):
        self._llm = llm
        self._methodology_text = methodology_text

    def select(self, input_data: RecommendationInput) -> CategorySelection:
        user_msg = CATEGORY_SELECTOR_USER.format(
            methodology=self._methodology_text or "（未提供方法论文档）",
            user_profile=input_data.user_profile.model_dump_json(
                indent=2, exclude_none=True
            ),
            dialogue_history=json.dumps(
                input_data.dialogue_history, ensure_ascii=False, indent=2
            ),
            query=input_data.query,
        )

        resp = self._llm.invoke([
            SystemMessage(content=CATEGORY_SELECTOR_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        return self._parse(resp.content)

    @staticmethod
    def _parse(content: str) -> CategorySelection:
        fallback = CategorySelection(
            category="百万医疗险",
            reasoning="无法解析LLM响应，默认使用百万医疗险",
            confidence="low",
        )
        try:
            body = content
            if "```json" in body:
                body = body.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in body:
                body = body.split("```", 1)[1].split("```", 1)[0]

            parsed = json.loads(body.strip())
            category = parsed.get("category", "百万医疗险")
            if category not in _VALID_CATEGORIES:
                category = "百万医疗险"

            confidence = parsed.get("confidence", "medium")
            if confidence not in ("high", "medium", "low"):
                confidence = "medium"

            return CategorySelection(
                category=category,
                reasoning=parsed.get("reasoning", ""),
                confidence=confidence,
            )
        except Exception as exc:
            logger.warning("Category selector parse failed: %s", exc)
            return fallback
