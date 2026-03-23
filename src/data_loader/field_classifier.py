from __future__ import annotations

import re
from typing import Optional

FieldClassification = tuple[str, str]   # (field_type, data_type)
ParsedValue = tuple[Optional[str], Optional[float], Optional[int]]

_NUMERIC_RE = re.compile(r"^[\d,]+\.?\d*\s*(万|元|天|岁|%|年)?$")
_BOOL_TRUE = frozenset({"是", "有", "yes", "true", "y", "1"})
_BOOL_FALSE = frozenset({"否", "无", "no", "false", "n", "0"})


class FieldClassifier:
    """Classify insurance-product fields as *hard* (filterable) or *soft* (textual).

    Hard fields are those whose values are predominantly numeric or boolean,
    suitable for SQL ``WHERE`` clauses.  Soft fields carry free-text
    descriptions better evaluated by an LLM.
    """

    @classmethod
    def classify(cls, field_name: str, values: list) -> FieldClassification:
        if field_name.startswith("是否"):
            return "hard", "BOOLEAN"

        non_empty = [
            v for v in values
            if v is not None and str(v).strip() not in ("", "None")
        ]
        if not non_empty:
            return "soft", "TEXT"

        bool_cnt = sum(1 for v in non_empty if cls._is_boolean(v))
        if bool_cnt >= len(non_empty) * 0.5:
            return "hard", "BOOLEAN"

        num_cnt = sum(1 for v in non_empty if cls._is_numeric(v))
        if num_cnt >= len(non_empty) * 0.5:
            return "hard", "NUMERIC"

        return "soft", "TEXT"

    # ── value parsing ─────────────────────────────────────────────

    @classmethod
    def parse_value(
        cls, raw: object, field_type: str, data_type: str
    ) -> ParsedValue:
        if raw is None or str(raw).strip() in ("", "None"):
            return None, None, None

        text = str(raw).strip()

        if data_type == "BOOLEAN":
            return text, None, cls._to_bool(raw)
        if data_type == "NUMERIC":
            return text, cls._to_float(raw), None
        return text, None, None

    # ── private helpers ───────────────────────────────────────────

    @classmethod
    def _is_numeric(cls, value: object) -> bool:
        if isinstance(value, (int, float)):
            return True
        s = str(value).strip().replace(",", "").replace("，", "")
        if _NUMERIC_RE.match(s):
            return True
        try:
            float(s)
            return True
        except (ValueError, TypeError):
            return False

    @classmethod
    def _is_boolean(cls, value: object) -> bool:
        s = str(value).strip().lower()
        return s in _BOOL_TRUE or s in _BOOL_FALSE

    @classmethod
    def _to_float(cls, value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().replace(",", "").replace("，", "")
        if s.endswith("万"):
            try:
                return float(s[:-1]) * 10_000
            except ValueError:
                return None
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    @classmethod
    def _to_bool(cls, value: object) -> Optional[int]:
        s = str(value).strip().lower()
        if s in _BOOL_TRUE:
            return 1
        if s in _BOOL_FALSE:
            return 0
        return None
