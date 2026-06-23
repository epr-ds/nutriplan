"""Prompt templating, versioning, and localization for the AI service (AIA-103).

Completions are only as good as the prompts behind them, so prompts are first-class
here rather than string literals scattered through the endpoints: they are templated
(system/user bodies with ``$variable`` placeholders), versioned and localized
(``es``/``en``), resolved through a catalog port, and rendered through a service that
records which prompt version ran on every call. The endpoints consume this package
starting in AIA-201; nothing here imports an LLM provider, it only produces the
:class:`~app.llm.types.LLMMessage` sequence a request is built from.
"""

from app.prompts.catalog import InMemoryPromptCatalog, PromptCatalog
from app.prompts.errors import (
    DuplicatePromptError,
    MissingPromptVariableError,
    PromptError,
    PromptNotFoundError,
    UnknownLocaleError,
)
from app.prompts.library import (
    DEFAULT_TEMPLATES,
    MEAL_RECOMMENDATION_ID,
    RECOMMEND_INGREDIENT_BASED_ID,
    RECOMMEND_MEAL_PLAN_ID,
    RECOMMEND_SINGLE_MEAL_ID,
    build_default_catalog,
    build_default_renderer,
)
from app.prompts.renderer import PromptRenderer
from app.prompts.telemetry import (
    InMemoryPromptTelemetry,
    LoggingPromptTelemetry,
    PromptTelemetry,
)
from app.prompts.template import PromptTemplate
from app.prompts.types import Locale, PromptRef, RenderedPrompt

__all__ = [
    "DEFAULT_TEMPLATES",
    "DuplicatePromptError",
    "InMemoryPromptCatalog",
    "InMemoryPromptTelemetry",
    "Locale",
    "LoggingPromptTelemetry",
    "MEAL_RECOMMENDATION_ID",
    "MissingPromptVariableError",
    "PromptCatalog",
    "PromptError",
    "PromptNotFoundError",
    "PromptRef",
    "PromptRenderer",
    "PromptTelemetry",
    "PromptTemplate",
    "RECOMMEND_INGREDIENT_BASED_ID",
    "RECOMMEND_MEAL_PLAN_ID",
    "RECOMMEND_SINGLE_MEAL_ID",
    "RenderedPrompt",
    "UnknownLocaleError",
    "build_default_catalog",
    "build_default_renderer",
]
