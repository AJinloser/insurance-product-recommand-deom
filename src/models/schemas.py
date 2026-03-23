from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    """Field classification for the insurance product schema."""
    HARD = "hard"
    SOFT = "soft"


class UserProfile(BaseModel):
    """Structured user profile for personalised recommendations."""
    age: Optional[int] = None
    has_social_insurance: Optional[bool] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    location: Optional[str] = None
    health_conditions: Optional[list[str]] = None
    family_members: Optional[int] = None
    extra: Optional[dict[str, Any]] = None


class RecommendationInput(BaseModel):
    """Input contract for the recommendation engine."""
    dialogue_history: list[dict[str, str]] = Field(default_factory=list)
    query: str
    user_profile: UserProfile = Field(default_factory=UserProfile)


class ProductRecommendation(BaseModel):
    """A single product recommendation with reasoning."""
    product_id: int
    product_name: str
    recommendation_reason: str


class RecommendationOutput(BaseModel):
    """Output contract for the recommendation engine."""
    status: Literal["success", "failed"]
    recommendations: list[ProductRecommendation] = Field(default_factory=list)
    error_message: Optional[str] = None


class CategorySelection(BaseModel):
    """Result of the category selection step."""
    category: str
    reasoning: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"


class GroupWeight(BaseModel):
    """A single group weight for weighted ranking."""
    group: str
    weight: float


class RankedProduct(BaseModel):
    """A product with its computed weighted score."""
    product_id: int
    product_name: str
    final_score: float
    group_scores: dict[str, float] = Field(default_factory=dict)
