"""Nutrition provenance + medical disclaimer metadata (DPL-305).

Static, catalog-wide metadata: the verified data source each nutrition value is traceable to, and
the disclaimer the UI must surface alongside it. Modelled as a domain value object (not persisted,
not per-user) so the API can expose it and tests can assert its compliance properties (every
nutrient maps to a verified source, and the payload carries no medical/health claims).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# The nutrient fields every catalog nutrition value is grouped under (DPL-301).
_NUTRIENT_FIELDS = ("calories", "protein", "carbs", "fat", "sugar")

_DISCLAIMER_TEXT = (
    "Nutrition values are estimates provided for general informational purposes only and are not "
    "a substitute for professional medical advice, diagnosis or treatment. Always seek the advice "
    "of a qualified health provider with any questions about your diet or a health condition."
)


class _Model(BaseModel):
    """Base for disclaimer models: camelCase wire keys, lenient on read."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class NutritionSource(_Model):
    """A verified dataset the catalog's nutrition values are traceable to (DPL-305)."""

    id: str
    name: str
    url: str
    verified: bool = True


class NutritionDisclaimer(_Model):
    """Catalog-wide nutrition provenance + medical disclaimer metadata (DPL-305).

    ``field_sources`` maps each nutrient field to the id of the verified :class:`NutritionSource`
    it comes from (traceability); ``medical_advice`` is explicitly ``False`` so the UI and clients
    can rely on the payload making no medical/health claims.
    """

    disclaimer: str
    medical_advice: bool = False
    sources: list[NutritionSource]
    field_sources: dict[str, str]
    last_reviewed: date


def default_nutrition_disclaimer() -> NutritionDisclaimer:
    """Return the canonical catalog nutrition disclaimer + source provenance (DPL-305)."""
    source = NutritionSource(
        id="usda-fdc",
        name="USDA FoodData Central",
        url="https://fdc.nal.usda.gov/",
        verified=True,
    )
    return NutritionDisclaimer(
        disclaimer=_DISCLAIMER_TEXT,
        medical_advice=False,
        sources=[source],
        field_sources={field: source.id for field in _NUTRIENT_FIELDS},
        last_reviewed=date(2026, 1, 15),
    )
