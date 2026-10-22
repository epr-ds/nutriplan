#!/usr/bin/env python3
"""Guard against drift between the KMP AI client and its contract (AIA-703).

Parses ``contracts/ai.openapi.yaml`` and checks it against:

* the operations and schemas projected in ``AiContractSpec.kt`` (the spec-derived mock the consumer
  contract tests run the real client against): method, path, request and response schemas and
  success status must match; so must each projected schema's required and allowed properties, the
  allowed values of its enum properties, and the schema of its nested objects;
* the client models the app ships (``AiModels.kt``, and the shared models the AI contract reuses):
  a request class must carry exactly the schema's fields, and a response class may read a subset of
  them but nothing the schema does not define (with the few documented exceptions below).

The health probes in the document are for the platform, not the app, so they are left out. A new
data class in ``AiModels.kt`` must be classified below, so nothing escapes the check silently.

Run locally with::

    python scripts/check_mobile_ai_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# Shared parsing helpers (same directory).
from check_mobile_dietary_contract import _blocks, _named, _ref_name, _string_set, load_models

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "contracts" / "ai.openapi.yaml"
SHARED = REPO_ROOT / "mobile" / "shared" / "src"
CONTRACT_SPEC_PATH = (
    SHARED / "commonTest" / "kotlin" / "com" / "nutriplan" / "shared" / "contract" / "AiContractSpec.kt"
)
MODELS_DIR = SHARED / "commonMain" / "kotlin" / "com" / "nutriplan" / "shared" / "data" / "model"
CHECKED_MODEL_FILES = [MODELS_DIR / "AiModels.kt"]
# Models the AI contract reuses from the other clients.
SHARED_MODEL_FILES = [MODELS_DIR / "MealPlanModels.kt", MODELS_DIR / "RecipeModels.kt", MODELS_DIR / "AuthModels.kt"]

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
EXCLUDED_PATH_PREFIXES = ("/health",)

# Classes the client sends: exactly the schema's properties.
REQUEST_CLASSES: dict[str, str] = {
    "AiRecommendationRequest": "AIRecommendationRequest",
    "AiDietaryPreferences": "DietaryPreferencesRequest",
    "AnalyzeMealRequest": "AnalyzeMealRequest",
    "OptimizePlanRequest": "OptimizePlanRequest",
    "DietaryMacroTargets": "MacroTargets",
    # Ingredients a meal analysis may carry are the catalog's ingredient shape.
    "RecipeIngredient": "IngredientResponse",
}

# Classes the client reads: a subset of the schema's properties (it ignores the rest).
RESPONSE_CLASSES: dict[str, str] = {
    "AiRecommendations": "AIRecommendationResponse",
    "NutritionalAlignment": "NutritionalAlignment",
    "MealAnalysis": "NutritionalAnalysisResponse",
    "Recipe": "RecipeResponse",
    "MealPlan": "MealPlanResponse",
    "PlanMeal": "MealResponse",
    "PlanMealRecipe": "RecipeResponse",
    "NutritionalInfo": "NutritionalInfo",
    "NutritionalSummary": "NutritionalSummary",
    "NutritionalTargets": "NutritionalTargets",
}

# Fields a shared response class reads that the AI contract does not send: the class is shared with
# the Dietary client, where they exist. They are optional with defaults, so an AI reply without them
# reads fine; anything else the client reads must be in the AI contract.
TOLERATED_EXTRA_FIELDS: dict[str, set[str]] = {
    "PlanMeal": {"dayIndex", "satisfactionLevel"},
    "NutritionalSummary": {"progress"},
}


def load_spec() -> tuple[dict, dict[str, dict]]:
    document = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    operations: dict[tuple[str, str], dict] = {}
    for path, item in document.get("paths", {}).items():
        if path.startswith(EXCLUDED_PATH_PREFIXES):
            continue
        for method, op in item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {})
            success = sorted(code for code in op.get("responses", {}) if str(code).startswith("2"))
            response = None
            if success:
                content = op["responses"][success[0]].get("content", {}).get("application/json", {})
                response = _ref_name(content.get("schema"))
            operations[(method.upper(), path)] = {
                "request": _ref_name(body.get("schema")),
                "response": response,
                "status": int(success[0]) if success else 0,
            }

    schemas: dict[str, dict] = {}
    for name, schema in document.get("components", {}).get("schemas", {}).items():
        properties = schema.get("properties", {})
        schemas[name] = {
            "required": set(schema.get("required", [])),
            "properties": set(properties),
            "enums": {key: set(prop["enum"]) for key, prop in properties.items() if "enum" in prop},
            "nested": {
                key: _ref_name(prop)
                for key, prop in properties.items()
                if _ref_name(prop) and "properties" in document["components"]["schemas"].get(_ref_name(prop), {})
            },
        }
    return operations, schemas


def _string_map(block: str, name: str) -> dict[str, str]:
    match = re.search(rf"\b{name}\s*=\s*mapOf\(((?:[^()]|\([^()]*\))*)\)", block)
    return dict(re.findall(r'"(\w+)"\s+to\s+"(\w+)"', match.group(1))) if match else {}


def _set_map(block: str, name: str) -> dict[str, set[str]]:
    match = re.search(rf"\b{name}\s*=\s*mapOf\(((?:[^()]|\([^()]*\))*)\)", block)
    if not match:
        return {}
    return {key: _string_set(f"({values})") for key, values in re.findall(r'"(\w+)"\s+to\s+setOf\(([^)]*)\)', match.group(1))}


def load_contract_spec() -> tuple[dict, dict[str, dict]]:
    text = CONTRACT_SPEC_PATH.read_text(encoding="utf-8")
    operations_part, _, schemas_part = text.partition("val schemas")

    operations: dict[tuple[str, str], dict] = {}
    for block in _blocks(operations_part, "Operation("):
        if block.strip().startswith("val ") or "String" in block:
            continue  # the data class declaration itself
        method, path = re.findall(r'"([^"]*)"', block)[:2]
        request, response = _named(block, "request"), _named(block, "response")
        operations[(method, path)] = {
            "request": request.strip('"') if request and request != "null" else None,
            "response": response.strip('"') if response and response != "null" else None,
            "status": int(_named(block, "status") or 0),
        }

    schemas: dict[str, dict] = {}
    for match in re.finditer(r'"(\w+)"\s+to\s+Schema\(', schemas_part):
        block = _blocks(schemas_part[match.start() :], "Schema(")[0]
        schemas[match.group(1)] = {
            "required": _string_set(_named(block, "required")),
            "properties": _string_set(_named(block, "properties")),
            "enums": _set_map(block, "enums"),
            "nested": _string_map(block, "nested"),
        }
    return operations, schemas


def check() -> list[str]:
    errors: list[str] = []
    spec_ops, spec_schemas = load_spec()
    mock_ops, mock_schemas = load_contract_spec()

    # 1. The mock serves exactly the documented operations.
    if set(spec_ops) != set(mock_ops):
        errors.append(
            f"operation drift: only in spec {sorted(set(spec_ops) - set(mock_ops))}; "
            f"only in mock {sorted(set(mock_ops) - set(spec_ops))}"
        )
    for key in sorted(set(spec_ops) & set(mock_ops)):
        for field in ("request", "response", "status"):
            if spec_ops[key][field] != mock_ops[key][field]:
                errors.append(
                    f"{key[0]} {key[1]}: {field} is {spec_ops[key][field]!r} in the spec "
                    f"but {mock_ops[key][field]!r} in the mock"
                )

    # 2. The mock's schemas are the spec's, enums and nested objects included.
    referenced = {op[f] for op in mock_ops.values() for f in ("request", "response") if op[f]}
    referenced |= {nested for schema in mock_schemas.values() for nested in schema["nested"].values()}
    for name in sorted(referenced):
        if name not in mock_schemas:
            errors.append(f"mock has no schema for '{name}'")
            continue
        if name not in spec_schemas:
            errors.append(f"mock references schema '{name}' not present in the spec")
            continue
        mock, spec = mock_schemas[name], spec_schemas[name]
        for field in ("required", "properties"):
            if mock[field] != spec[field]:
                errors.append(f"schema drift in {name}.{field}: spec {sorted(spec[field])}; mock {sorted(mock[field])}")
        if mock["enums"] != spec["enums"]:
            errors.append(f"enum drift in {name}: spec {spec['enums']}; mock {mock['enums']}")
        # Request bodies are validated all the way down, so every nested object must be projected.
        request_side = any(op["request"] == name for op in mock_ops.values()) or any(
            name in schema["nested"].values() for schema in mock_schemas.values()
        )
        if request_side and mock["nested"] != spec["nested"]:
            errors.append(f"nested-object drift in {name}: spec {spec['nested']}; mock {mock['nested']}")

    # 3. The client's models match the spec.
    checked = load_models(CHECKED_MODEL_FILES)
    models = {**load_models(SHARED_MODEL_FILES), **checked}

    for class_name, schema_name in sorted(REQUEST_CLASSES.items()):
        fields, schema = models.get(class_name), spec_schemas.get(schema_name)
        if fields is None or schema is None:
            errors.append(f"request class '{class_name}' or schema '{schema_name}' not found")
        elif fields != schema["properties"]:
            errors.append(
                f"field drift in request {class_name} ({schema_name}): only in client "
                f"{sorted(fields - schema['properties'])}; only in spec {sorted(schema['properties'] - fields)}"
            )

    for class_name, schema_name in sorted(RESPONSE_CLASSES.items()):
        fields, schema = models.get(class_name), spec_schemas.get(schema_name)
        if fields is None or schema is None:
            errors.append(f"response class '{class_name}' or schema '{schema_name}' not found")
            continue
        extra = fields - schema["properties"] - TOLERATED_EXTRA_FIELDS.get(class_name, set())
        if extra:
            errors.append(
                f"field drift in response {class_name} ({schema_name}): the client reads {sorted(extra)}, "
                "which the AI contract does not define"
            )

    classified = set(REQUEST_CLASSES) | set(RESPONSE_CLASSES)
    unclassified = sorted(set(checked) - classified)
    if unclassified:
        errors.append(f"data classes not covered by the contract check (classify them): {unclassified}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("KMP AI client contract check FAILED:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("KMP AI client matches contracts/ai.openapi.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
