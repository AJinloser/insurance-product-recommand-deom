from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import openpyxl


_KNOWN_GROUPS = frozenset({
    "基本信息", "保费", "一般保险责任", "特殊保险责任", "其他说明",
})


class ExcelParser:
    """Parse transposed insurance-product Excel files.

    Convention: rows = attribute fields, columns = products.
    The first column holds field names; remaining columns hold one product each.
    Group rows (col 0 has text in _KNOWN_GROUPS, cols 1+ all empty) are
    detected and used to assign fields to groups.
    """

    _HEADER_KEYWORDS = ("保障计划", "保险公司", "计划名称", "产品名称")

    @classmethod
    def parse(cls, file_path: Path) -> dict[str, Any]:
        """Return parsed data with group information.

        Returns::

            {
                'products': [{'__product_name__': str, '__fields__': {field: value}}],
                'field_groups': {field_name: group_name},
                'groups_ordered': [group_name, ...],
            }
        """
        wb = openpyxl.load_workbook(str(file_path), data_only=True)
        ws = wb.active
        if ws is None:
            wb.close()
            return {"products": [], "field_groups": {}, "groups_ordered": []}

        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if len(rows) < 2:
            return {"products": [], "field_groups": {}, "groups_ordered": []}

        header_idx = cls._find_header_row(rows)
        if header_idx is None:
            return {"products": [], "field_groups": {}, "groups_ordered": []}

        header_row = rows[header_idx]
        product_cols = [
            i for i in range(1, len(header_row))
            if header_row[i] and str(header_row[i]).strip()
        ]
        if not product_cols:
            return {"products": [], "field_groups": {}, "groups_ordered": []}

        products: list[dict[str, Any]] = []
        field_groups: dict[str, str] = {}
        groups_ordered: list[str] = []
        current_group: Optional[str] = None

        for col in product_cols:
            products.append({
                "__product_name__": str(header_row[col]).strip(),
                "__fields__": {},
            })

        for row_idx in range(header_idx + 1, len(rows)):
            row = rows[row_idx]
            cell0 = row[0]
            if not cell0 or not str(cell0).strip():
                continue

            cell0_text = str(cell0).strip().rstrip("：:")

            # Check if this is a group header row
            if cls._is_group_row(cell0_text, row, product_cols):
                current_group = cls._match_group(cell0_text)
                if current_group and current_group not in groups_ordered:
                    groups_ordered.append(current_group)
                continue

            # Regular field row
            field_name = cell0_text
            if current_group:
                field_groups[field_name] = current_group

            for i, col in enumerate(product_cols):
                raw = row[col] if col < len(row) else None
                if raw is not None:
                    products[i]["__fields__"][field_name] = (
                        raw if isinstance(raw, (int, float)) else str(raw).strip()
                    )
                else:
                    products[i]["__fields__"][field_name] = None

        return {
            "products": products,
            "field_groups": field_groups,
            "groups_ordered": groups_ordered,
        }

    @classmethod
    def _is_group_row(
        cls, cell0_text: str, row: tuple, product_cols: list[int]
    ) -> bool:
        """A group row has a known group name (or starts with one) in col 0 and all product cols empty."""
        matched = cls._match_group(cell0_text)
        if matched is None:
            return False
        for col in product_cols:
            val = row[col] if col < len(row) else None
            if val is not None and str(val).strip():
                return False
        return True

    @classmethod
    def _match_group(cls, text: str) -> Optional[str]:
        """Return the canonical group name if text matches (exact or prefix)."""
        if text in _KNOWN_GROUPS:
            return text
        for group in _KNOWN_GROUPS:
            if text.startswith(group):
                return group
        return None

    @classmethod
    def _find_header_row(cls, rows: list[tuple]) -> Optional[int]:
        for idx, row in enumerate(rows[:5]):
            cell = row[0]
            if cell and any(kw in str(cell) for kw in cls._HEADER_KEYWORDS):
                return idx
        return 1 if len(rows) > 1 else None
