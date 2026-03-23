from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from langchain_core.language_models import BaseChatModel

from .excel_parser import ExcelParser
from .field_classifier import FieldClassifier
from .group_scorer import GroupScorer
from ..database.connection import DatabaseConnection
from ..database.repository import ProductRepository

logger = logging.getLogger(__name__)


class DataLoader:
    """Orchestrate the full pipeline: scan → parse → classify → store → score groups.

    Designed for idempotent reloads: every call to ``load_all`` is safe to
    re-run and will reconcile the DB with the current state of the data
    directory (adding new files, updating changed ones, removing stale data).
    """

    def __init__(
        self,
        data_dir: Path,
        db_connection: DatabaseConnection,
        llm: Optional[BaseChatModel] = None,
        methodology_text: str = "",
    ) -> None:
        self.data_dir = data_dir
        self.db = db_connection
        self.repo = ProductRepository(db_connection)
        self.parser = ExcelParser()
        self.classifier = FieldClassifier()
        self._llm = llm
        self._methodology_text = methodology_text

    def load_all(self, force_reload: bool = False) -> None:
        self.db.init_tables()

        xlsx_files = self._scan()
        if not xlsx_files:
            logger.warning("No xlsx files found in %s", self.data_dir)
            return

        if force_reload:
            self._truncate_all()

        existing_snapshots = {
            row["source_file"]: row for row in self.repo.get_source_snapshots()
        }

        loaded_sources: set[str] = set()
        categories_changed: set[str] = set()
        categories_loaded: set[str] = set()
        for fp in xlsx_files:
            try:
                source = fp.name
                category = self._category(source)
                content_hash = self._content_hash(fp)

                loaded_sources.add(fp.name)
                categories_loaded.add(category)

                snapshot = existing_snapshots.get(source)
                has_existing_products = bool(self.repo.get_products_by_source(source))
                unchanged = (
                    not force_reload
                    and snapshot is not None
                    and snapshot["content_hash"] == content_hash
                    and snapshot["category"] == category
                    and has_existing_products
                )

                if unchanged:
                    logger.info(
                        "Skipping reload for %s (source unchanged)", fp.name
                    )
                    continue

                self._load_file(fp)
                self.repo.upsert_source_snapshot(source, category, content_hash)
                categories_changed.add(category)
                logger.info("Loaded %s", fp.name)
            except Exception:
                logger.exception("Failed to load %s", fp.name)

        self._cleanup_stale(loaded_sources)

        # Score groups only for categories that need it
        if self._llm:
            scorer = GroupScorer(self._llm, self.repo, self._methodology_text)
            for category in categories_loaded:
                try:
                    groups = self.repo.get_distinct_groups(category)
                    if not groups:
                        continue
                    # Skip scoring if scores already exist and products didn't change
                    existing_scores = self.repo.get_group_scores_by_category(category)
                    if existing_scores and category not in categories_changed:
                        logger.info(
                            "Skipping group scoring for %s (no changes, %d scores exist)",
                            category, len(existing_scores),
                        )
                        continue
                    scorer.score_category(category, groups)
                    logger.info(
                        "Group scoring complete for %s (%d groups)",
                        category, len(groups),
                    )
                except Exception:
                    logger.exception(
                        "Group scoring failed for %s", category
                    )

    # ── internal ──────────────────────────────────────────────────

    def _scan(self) -> list[Path]:
        if not self.data_dir.exists():
            return []
        return sorted(
            p for p in self.data_dir.iterdir()
            if p.suffix == ".xlsx" and not p.name.startswith("~")
        )

    @staticmethod
    def _content_hash(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _load_file(self, file_path: Path) -> Optional[str]:
        source = file_path.name
        category = self._category(source)

        self.repo.clear_source(source)
        self.repo.clear_category_metadata(category)

        parsed = self.parser.parse(file_path)
        products = parsed["products"]
        field_groups: dict[str, str] = parsed["field_groups"]

        if not products:
            logger.warning("No products parsed from %s", source)
            return None

        classifications = self._classify(products)

        for fname, (ftype, dtype) in classifications.items():
            group = field_groups.get(fname)
            self.repo.insert_field_metadata(
                fname, ftype, dtype, category, field_group=group
            )

        for pdata in products:
            pid = self.repo.insert_product(
                pdata["__product_name__"], category, source
            )
            for fname, raw in pdata["__fields__"].items():
                if fname not in classifications:
                    continue
                ftype, dtype = classifications[fname]
                txt, num, bln = self.classifier.parse_value(raw, ftype, dtype)
                group = field_groups.get(fname)
                self.repo.insert_product_value(
                    pid, fname, ftype, txt, num, bln, field_group=group
                )

        return category

    def _classify(self, products: list[dict]) -> dict[str, tuple[str, str]]:
        agg: dict[str, list] = {}
        for p in products:
            for fname, val in p["__fields__"].items():
                agg.setdefault(fname, []).append(val)
        return {
            fname: self.classifier.classify(fname, vals)
            for fname, vals in agg.items()
        }

    @staticmethod
    def _category(filename: str) -> str:
        name = filename.rsplit(".", 1)[0]
        parts = name.rsplit("_", 1)
        if len(parts) > 1 and parts[1].isdigit():
            name = parts[0]
        return name

    def _cleanup_stale(self, current_sources: set[str]) -> None:
        product_sources = {p["source_file"] for p in self.repo.get_all_products()}
        snapshot_sources = {
            row["source_file"] for row in self.repo.get_source_snapshots()
        }
        for stale in (product_sources | snapshot_sources) - current_sources:
            logger.info("Removing stale source: %s", stale)
            self.repo.clear_source(stale)

    def _truncate_all(self) -> None:
        conn = self.db.get_connection()
        conn.executescript(
            "DELETE FROM source_snapshots;"
            "DELETE FROM group_scores;"
            "DELETE FROM product_values;"
            "DELETE FROM field_metadata;"
            "DELETE FROM products;"
        )
        conn.commit()
