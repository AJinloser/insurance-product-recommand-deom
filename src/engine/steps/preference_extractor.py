from __future__ import annotations

import json
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from ...models.schemas import GroupWeight, RecommendationInput
from ..prompts import PREFERENCE_EXTRACTOR_SYSTEM, PREFERENCE_EXTRACTOR_USER

logger = logging.getLogger(__name__)

_DEFAULT_GROUPS = ["基本信息", "保费", "一般保险责任", "特殊保险责任", "其他说明"]


class PreferenceExtractor:
    """Step 3a — extract user preference weights for field groups via LLM."""

    def __init__(self, llm: BaseChatModel):
        self._llm = llm

    def extract(self, input_data: RecommendationInput) -> list[GroupWeight]:
        user_msg = PREFERENCE_EXTRACTOR_USER.format(
            user_profile=input_data.user_profile.model_dump_json(
                indent=2, exclude_none=True
            ),
            dialogue_history=json.dumps(
                input_data.dialogue_history, ensure_ascii=False, indent=2
            ),
            query=input_data.query,
            groups=json.dumps(_DEFAULT_GROUPS, ensure_ascii=False),
        )

        resp = self._llm.invoke([
            SystemMessage(content=PREFERENCE_EXTRACTOR_SYSTEM),
            HumanMessage(content=user_msg),
        ])
        return self._parse(resp.content)

    @staticmethod
    def _parse(content: str) -> list[GroupWeight]:
        default_weights = [
            GroupWeight(group="基本信息", weight=0.20),
            GroupWeight(group="保费", weight=0.25),
            GroupWeight(group="一般保险责任", weight=0.25),
            GroupWeight(group="特殊保险责任", weight=0.15),
            GroupWeight(group="其他说明", weight=0.15),
        ]
        try:
            body = content
            if "```json" in body:
                body = body.split("```json", 1)[1].split("```", 1)[0]
            elif "```" in body:
                body = body.split("```", 1)[1].split("```", 1)[0]

            parsed = json.loads(body.strip())
            weights_data = parsed.get("weights", parsed)

            # Handle dict format: {"基本信息": 0.20, ...}
            if isinstance(weights_data, dict):
                raw = [
                    GroupWeight(group=k, weight=float(v))
                    for k, v in weights_data.items()
                    if k in _DEFAULT_GROUPS
                ]
            # Handle list format: [{"group": "基本信息", "weight": 0.20}, ...]
            elif isinstance(weights_data, list):
                raw = [
                    GroupWeight(
                        group=item.get("group", ""),
                        weight=float(item.get("weight", 0)),
                    )
                    for item in weights_data
                    if item.get("group") in _DEFAULT_GROUPS
                ]
            else:
                return default_weights

            if not raw:
                return default_weights

            # Normalize weights to sum to 1.0
            total = sum(w.weight for w in raw)
            if total > 0 and abs(total - 1.0) > 0.001:
                raw = [
                    GroupWeight(group=w.group, weight=w.weight / total)
                    for w in raw
                ]

            return raw
        except Exception as exc:
            logger.warning("Preference extractor parse failed: %s", exc)
            return default_weights
