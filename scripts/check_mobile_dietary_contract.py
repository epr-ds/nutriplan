#!/usr/bin/env python3
"""Guard against drift between the KMP Dietary client and its contract (DPL-703).

Parses ``contracts/dietary.openapi.yaml`` and checks it against:

* the operations and schemas projected in ``DietaryContractSpec.kt`` (the spec-derived mock the
  consumer contract tests run the real client against): method, path, request and response
  schemas, success status, list responses and query parameters must match exactly;
* the client models the app ships (``MealPlanModels.kt``, ``RecipeModels.kt``): a request class
  must carry exactly the schema's fields, a response class may read a subset of them but nothing
  the schema does not define, and a query class must use exactly the operation's query parameters.

The ``/ai/*`` operations in the same document are served by the AI service and consumed by the AI
client (AIA-703), so they are left out here, as are the AI models in ``RecipeModels.kt``. A new data
class in the checked files must be classified below, so nothing escapes the check silently.

Run locally with::

    python scripts/check_mobile_dietary_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "contracts" / "dietary.openapi.yaml"
SHARED = REPO_ROOT / "mobile" / "shared" / "src"
CONTRACT_SPEC_PATH = (
    SHARED / "commonTest" / "kotlin" / "com" / "nutriplan" / "shared" / "contract" / "DietaryContractSpec.kt"
)
MODELS_DIR = SHARED / "commonMain" / "kotlin" / "com" / "nutriplan" / "shared" / "data" / "model"
CHECKED_MODEL_FILES = [MODELS_DIR / "MealPlanModels.kt", MODELS_DIR / "RecipeModels.kt"]
SHARED_MODEL_FILES = [MODELS_DIR / "AuthModels.kt"]

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
EXCLUDED_PATH_PREFIXES = ("/ai/",)

# Classes the client sends: exactly the schema's properties.
REQUEST_CLASSES: dict[str, str] = {
    "CreateMealPlanRequest": "CreateMealPlanRequest",
    "AddMealRequest": "AddMealRequest",
    "UpdateMealRequest": "UpdateMealRequest",
    "UpdateMealPlanStatusRequest": "UpdateMealPlanStatusRequest",
    # Nested in CreateMealPlanRequest; the class lives with the Identity models.
    "DietaryMacroTargets": "MacroTargets",
}

# Classes the client reads: a subset of the schema's properties (it ignores the rest).
RESPONSE_CLASSES: dict[str, str] = {
    "MealPlanSummary": "MealPlanSummaryResponse",
    "MealPlan": "MealPlanResponse",
    "PlanMeal": "MealResponse",
    "PlanMealRecipe": "RecipeResponse",
    "Recipe": "RecipeResponse",
    "RecipeIngredient": "IngredientResponse",
    "NutritionalInfo": "NutritionalInfo",
    "NutritionalSummary": "NutritionalSummary",
    "NutritionalTargets": "NutritionalTargets",
    "NutritionalProgress": "NutritionalProgress",
    "NutrientProgress": "NutrientProgress",
    "NutritionDisclaimer": "NutritionDisclaimerResponse",
    "NutritionSource": "NutritionSource",
}

# Classes that build query strings: exactly the operation's query parameters.
QUERY_CLASSES: dict[str, tuple[str, str]] = {
    "MealPlanQuery": ("GET", "/meal-plans"),
    "RecipeSearchQuery": ("GET", "/recipes"),
}

# Classes in the checked files that belong to the AI contract (checked by AIA-703).
AI_CLASSES = {
    "NutritionInfo",
    "MacroTargets",
    "NutritionEstimate",
    "AIRecommendationRequest",
    "DietaryPreferencesSchema",
    "AIRecommendationResponse",
    "RecommendedRecipe",
    "NutritionalAlignment",
    "MealIngredient",
    "NutritionalAnalysisResponse",
}

_CLASS_RE = re.compile(r"data class\s+(\w+)\s*\((.*?)\n\)", re.DOTALL)
_FIELD_RE = re.compile(r"\bval\s+(\w+)\s*:")
_STRING_RE = re.compile(r'"([^"]*)"')


def _ref_name(node: dict | None) -> str | None:
    if not isinstance(node, dict):
        return None
    ref = node.get("$ref")
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def load_spec() -> tuple[dict, dict[str, dict[str, set[str]]]]:
    document = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    components = document.get("components", {})
    shared_params = components.get("parameters", {})

    operations: dict[tuple[str, str], dict] = {}
    for path, item in document.get("paths", {}).items():
        if path.startswith(EXCLUDED_PATH_PREFIXES):
            continue
        for method, op in item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {})
            request = _ref_name(body.get("schema"))

            success = sorted(code for code in op.get("responses", {}) if str(code).startswith("2"))
            status = int(success[0]) if success else 0
            response = None
            is_list = False
            if success:
                content = op["responses"][success[0]].get("content", {}).get("application/json", {})
                schema = content.get("schema")
                if isinstance(schema, dict) and schema.get("type") == "array":
                    is_list = True
                    response = _ref_name(schema.get("items"))
                else:
                    response = _ref_name(schema)

            query: set[str] = set()
            for param in op.get("parameters", []):
                resolved = shared_params.get(_ref_name(param), param) if _ref_name(param) else param
                if resolved.get("in") == "query":
                    query.add(resolved["name"])

            operations[(method.upper(), path)] = {
                "request": request,
                "response": response,
                "status": status,
                "list": is_list,
                "query": query,
            }

    schemas: dict[str, dict[str, set[str]]] = {}
    for name, schema in components.get("schemas", {}).items():
        schemas[name] = {
            "required": set(schema.get("required", [])),
            "properties": set(schema.get("properties", {})),
        }
    return operations, schemas


def _blocks(text: str, opener: str) -> list[str]:
    """Return the argument text of every ``opener(...)`` call, matching parentheses."""
    blocks = []
    start = text.find(opener)
    while start != -1:
        depth = 0
        i = start + len(opener) - 1
        while i < len(text):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[start + len(opener) : i])
                    break
            i += 1
        start = text.find(opener, i)
    return blocks


def _named(block: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*(\"[^\"]*\"|null|true|false|\d+|setOf\([^)]*\)|emptySet\(\))", block)
    return match.group(1) if match else None


def _string_set(value: str | None) -> set[str]:
    return set(_STRING_RE.findall(value or ""))


def load_contract_spec() -> tuple[dict, dict[str, dict[str, set[str]]]]:
    text = CONTRACT_SPEC_PATH.read_text(encoding="utf-8")
    operations_part, _, schemas_part = text.partition("val schemas")

    operations: dict[tuple[str, str], dict] = {}
    for block in _blocks(operations_part, "Operation("):
        if block.strip().startswith("val ") or "String" in block:
            continue  # the data class declaration itself
        method, path = _STRING_RE.findall(block)[:2]
        request = _named(block, "request")
        response = _named(block, "response")
        operations[(method, path)] = {
            "request": request.strip('"') if request and request != "null" else None,
            "response": response.strip('"') if response and response != "null" else None,
            "status": int(_named(block, "status") or 0),
            "list": _named(block, "list") == "true",
            "query": _string_set(_named(block, "query")),
        }

    schemas: dict[str, dict[str, set[str]]] = {}
    for match in re.finditer(r'"(\w+)"\s+to\s+Schema\(', schemas_part):
        block = _blocks(schemas_part[match.start() :], "Schema(")[0]
        schemas[match.group(1)] = {
            "required": _string_set(_named(block, "required")),
            "properties": _string_set(_named(block, "properties")),
        }
    return operations, schemas


def load_models(paths: list[Path]) -> dict[str, set[str]]:
    models: dict[str, set[str]] = {}
    for path in paths:
        for name, body in _CLASS_RE.findall(path.read_text(encoding="utf-8")):
            # Local-only properties are never on the wire.
            wire_lines = [line for line in body.splitlines() if "@Transient" not in line]
            models[name] = set(_FIELD_RE.findall("\n".join(wire_lines)))
    return models


def check() -> list[str]:
    errors: list[str] = []
    spec_ops, spec_schemas = load_spec()
    mock_ops, mock_schemas = load_contract_spec()

    # 1. The mock serves exactly the documented operations, with the documented shapes.
    only_spec = sorted(set(spec_ops) - set(mock_ops))
    only_mock = sorted(set(mock_ops) - set(spec_ops))
    if only_spec or only_mock:
        errors.append(f"operation drift: only in spec {only_spec}; only in mock {only_mock}")
    for key in sorted(set(spec_ops) & set(mock_ops)):
        spec_op, mock_op = spec_ops[key], mock_ops[key]
        for field in ("request", "response", "status", "list", "query"):
            if spec_op[field] != mock_op[field]:
                errors.append(
                    f"{key[0]} {key[1]}: {field} is {sorted(spec_op[field]) if field == 'query' else spec_op[field]!r} "
                    f"in the spec but {sorted(mock_op[field]) if field == 'query' else mock_op[field]!r} in the mock"
                )

    # 2. The mock's schemas are the spec's.
    referenced = {op[f] for op in mock_ops.values() for f in ("request", "response") if op[f]}
    for name in sorted(referenced):
        if name not in mock_schemas:
            errors.append(f"mock has no schema for '{name}'")
        elif name not in spec_schemas:
            errors.append(f"mock references schema '{name}' not present in the spec")
        elif mock_schemas[name] != spec_schemas[name]:
            errors.append(
                f"schema drift in {name}: spec required {sorted(spec_schemas[name]['required'])} "
                f"properties {sorted(spec_schemas[name]['properties'])}; mock required "
                f"{sorted(mock_schemas[name]['required'])} properties {sorted(mock_schemas[name]['properties'])}"
            )

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
        elif not fields <= schema["properties"]:
            errors.append(
                f"field drift in response {class_name} ({schema_name}): the client reads "
                f"{sorted(fields - schema['properties'])}, which the spec does not define"
            )

    for class_name, key in sorted(QUERY_CLASSES.items()):
        fields, op = models.get(class_name), spec_ops.get(key)
        if fields is None or op is None:
            errors.append(f"query class '{class_name}' or operation {key} not found")
        elif fields != op["query"]:
            errors.append(
                f"query drift in {class_name} ({key[0]} {key[1]}): only in client "
                f"{sorted(fields - op['query'])}; only in spec {sorted(op['query'] - fields)}"
            )

    classified = set(REQUEST_CLASSES) | set(RESPONSE_CLASSES) | set(QUERY_CLASSES) | AI_CLASSES
    unclassified = sorted(set(checked) - classified)
    if unclassified:
        errors.append(f"data classes not covered by the contract check (classify them): {unclassified}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("KMP Dietary client contract check FAILED:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("KMP Dietary client matches contracts/dietary.openapi.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
