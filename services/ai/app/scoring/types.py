"""Value objects for nutritional-alignment scoring (AIA-106).

These mirror the Dietary Planning vocabulary (calories plus the ``protein``/``carbs``/
``fat``/``sugar`` macros, and the dietary-type names) but are defined locally: the AI
service is a separate bounded context, so it duplicates the shared kernel rather than
importing another service's domain. Everything here is frozen and JSON-friendly, so the
same shapes flow into the ``/ai/*`` response (``nutritionalAlignment``) in AIA-204.

Two ``None`` conventions matter:
- a **target** of ``None`` means *untargeted* -- that nutrient is left out of the score;
- an **actual** of ``None`` means *unknown* -- which, against a real target, cannot be
  confirmed as aligned and so scores as a miss (unknown is not zero, but it is not a pass).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

NUTRIENTS = ("calories", "protein", "carbs", "fat", "sugar")
"""The scored nutrients, in a fixed order so results are deterministic."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class NutrientProfile(_Frozen):
    """The actual nutrition of the thing being scored (a recipe or a whole plan)."""

    calories: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


class NutrientTargets(_Frozen):
    """The calorie/macro goals to score against; ``None`` leaves a nutrient untargeted."""

    calories: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    sugar: float | None = None


class Preferences(_Frozen):
    """Hard, non-nutritional constraints: required diets and ingredients to avoid.

    Both are matched case-insensitively. ``required_diets`` lists diet names the candidate
    must be compatible with (mirrors ``DietaryType``); ``excluded_ingredients`` lists tokens
    (allergens or dislikes) that must not appear among the candidate's ingredients.
    """

    required_diets: frozenset[str] = frozenset()
    excluded_ingredients: frozenset[str] = frozenset()


class ScoringCandidate(_Frozen):
    """A recipe or plan to be scored, plus the attributes preferences check against."""

    nutrition: NutrientProfile
    diets: frozenset[str] = frozenset()
    ingredients: frozenset[str] = frozenset()


class AlignmentWeights(_Frozen):
    """Relative importance of each nutrient; renormalized over the targeted ones."""

    calories: float = Field(default=1.0, ge=0.0)
    protein: float = Field(default=1.0, ge=0.0)
    carbs: float = Field(default=0.75, ge=0.0)
    fat: float = Field(default=0.75, ge=0.0)
    sugar: float = Field(default=0.5, ge=0.0)


class AlignmentComponent(_Frozen):
    """One line of the score breakdown -- a nutrient's closeness or the preference gate."""

    name: str
    score: float
    weight: float
    target: float | None = None
    actual: float | None = None
    detail: str


class NutritionalAlignment(_Frozen):
    """How well a candidate matches its targets and preferences (score + details).

    ``nutrition_score`` is the weighted closeness across targeted nutrients; ``score`` is the
    overall result after the preference gate -- a hard violation (wrong diet, excluded
    ingredient) drops it to ``0`` because the item should not be recommended, while
    ``nutrition_score`` is kept for transparency. ``aligned`` applies the scorer's threshold.
    """

    score: float
    nutrition_score: float
    aligned: bool
    components: tuple[AlignmentComponent, ...]
    violations: tuple[str, ...] = ()

    @property
    def percentage(self) -> float:
        """The overall score as a 0-100 percentage."""
        return round(self.score * 100, 2)
