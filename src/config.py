from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    """Insurance recommendation engine configuration.

    Values can be injected via constructor, ``from_env()``, or by loading
    a ``.env`` file with ``python-dotenv`` before calling ``from_env()``.
    """

    data_dir: Path = Field(default_factory=lambda: _PROJECT_ROOT / "data")
    db_path: Path = Field(default_factory=lambda: _PROJECT_ROOT / "insurance.db")
    methodology_doc_path: Path = Field(
        default_factory=lambda: _PROJECT_ROOT / "docs" / "保险产品推荐方法论.md"
    )

    llm_model: str = "gpt-4o"
    llm_api_key: str = ""
    llm_base_url: Optional[str] = None
    llm_temperature: float = 0.1

    top_k_candidates: int = 10
    max_recommendations: int = 5
    top_k_ranked: int = 3

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_env(cls) -> Settings:
        """Construct settings from ``INSURANCE_*`` environment variables."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        env_map: dict[str, str] = {
            "data_dir": "INSURANCE_DATA_DIR",
            "db_path": "INSURANCE_DB_PATH",
            "methodology_doc_path": "INSURANCE_METHODOLOGY_DOC_PATH",
            "llm_model": "INSURANCE_LLM_MODEL",
            "llm_api_key": "INSURANCE_LLM_API_KEY",
            "llm_base_url": "INSURANCE_LLM_BASE_URL",
            "llm_temperature": "INSURANCE_LLM_TEMPERATURE",
            "top_k_candidates": "INSURANCE_TOP_K_CANDIDATES",
            "max_recommendations": "INSURANCE_MAX_RECOMMENDATIONS",
            "top_k_ranked": "INSURANCE_TOP_K_RANKED",
        }
        kwargs: dict = {}
        for field_name, env_var in env_map.items():
            val = os.environ.get(env_var)
            if val is not None:
                kwargs[field_name] = val
        return cls(**kwargs)
