"""Recommendation use case: turn a request into a preference-aware LLM prompt (AIA-202).

This is the application layer for ``POST /ai/recommendations``. AIA-202 ships the prompt-assembly
half -- a :class:`RecommendationCommand` plus a :class:`RecommendationPromptAssembler` rendering a
distinct, localized template per context with the caller's dietary profile injected. The LLM call
and recipe mapping (AIA-203) and nutritional alignment + reasoning (AIA-204) layer on top later.
"""

from app.recommendations.assembler import (
    RecommendationPromptAssembler,
    build_recommendation_prompt_assembler,
)
from app.recommendations.commands import (
    MacroTargets,
    MealType,
    RecommendationCommand,
    RecommendationContext,
)

__all__ = [
    "MacroTargets",
    "MealType",
    "RecommendationCommand",
    "RecommendationContext",
    "RecommendationPromptAssembler",
    "build_recommendation_prompt_assembler",
]
