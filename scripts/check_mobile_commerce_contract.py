#!/usr/bin/env python3
"""Guard against drift between the KMP Commerce client and its contract (COM-803).

Parses ``contracts/commerce.openapi.yaml`` and checks it against:

* the operations and schemas projected in ``CommerceContractSpec.kt`` (the spec-derived mock the
  consumer contract tests run the real client against): method, path, request and response schemas,
  success status, list responses, query parameters (and which are required, and their enum values),
  header parameters and whether a body is required must match; so must each projected schema's
  required and allowed properties and, for the schemas the client sends, the allowed values of its
  enum properties, the schema of its nested objects and the schema of its array items;
* the client models the app ships (``CommerceModels.kt``): a request class must carry exactly the
  schema's fields, a response class may read a subset of them but nothing the schema does not
  define, and the query class must use exactly the operation's query parameters.

The payment and kitchen webhooks in the document are called by providers, not the app, so they are
left out. An inline array-item schema is named ``Schema.property`` (``GrocerySearchRequest.items``).
A new data class in ``CommerceModels.kt`` must be classified below, so nothing escapes the check.

Run locally with::

    python scripts/check_mobile_commerce_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# Shared parsing helpers (same directory).
from check_mobile_ai_contract import _set_map
from check_mobile_dietary_contract import _blocks, _named, _ref_name, _string_set, load_models

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "contracts" / "commerce.openapi.yaml"
SHARED = REPO_ROOT / "mobile" / "shared" / "src"
CONTRACT_SPEC_PATH = (
    SHARED / "commonTest" / "kotlin" / "com" / "nutriplan" / "shared" / "contract" / "CommerceContractSpec.kt"
)
MODELS_DIR = SHARED / "commonMain" / "kotlin" / "com" / "nutriplan" / "shared" / "data" / "model"
CHECKED_MODEL_FILES = [MODELS_DIR / "CommerceModels.kt"]

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
EXCLUDED_PATH_PREFIXES = ("/webhooks/",)

# Classes the client sends: exactly the schema's properties.
REQUEST_CLASSES: dict[str, str] = {
    "CreateOrderRequest": "CreateOrderRequest",
    "OrderAddress": "AddressRequest",
    "PaymentMethodRequest": "PaymentMethodRequest",
    "CancelOrderRequest": "CancelOrderRequest",
    "SavePaymentMethodRequest": "SavePaymentMethodRequest",
    "GrocerySearchRequest": "GrocerySearchRequest",
    "GrocerySearchItem": "GrocerySearchRequest.items",
}

# Classes the client reads: a subset of the schema's properties (it ignores the rest).
RESPONSE_CLASSES: dict[str, str] = {
    "Order": "OrderResponse",
    "OrderItem": "OrderItemResponse",
    "Money": "MoneyResponse",
    "PaymentVoucher": "VoucherResponse",
    "BankTransfer": "TransferResponse",
    "PaymentApproval": "ApprovalResponse",
    "Refund": "RefundResponse",
    "GroceryOrder": "GroceryOrderResponse",
    "PaymentMethod": "PaymentMethodResponse",
    "KitchenAvailability": "AvailabilityResponse",
    "FulfillmentProvider": "ProviderResponse",
}

# Classes that build query strings: exactly the operation's query parameters.
QUERY_CLASSES: dict[str, tuple[str, str]] = {
    "OrderListQuery": ("GET", "/orders"),
}

_NAME_MAP_ENTRY = re.compile(r'"([\w.]+)"\s+to\s+"([\w.]+)"')

OPERATION_FIELDS = ("request", "response", "status", "list", "query", "requiredQuery", "queryEnums", "headers", "bodyRequired")


def _schema_shape(name: str, schema: dict, all_schemas: dict, out: dict[str, dict]) -> None:
    """Record ``schema`` (and any inline array-item schema it declares) in ``out``."""
    properties = schema.get("properties", {})
    nested: dict[str, str] = {}
    arrays: dict[str, str] = {}
    for key, prop in properties.items():
        ref = _ref_name(prop)
        if ref and "properties" in all_schemas.get(ref, {}):
            nested[key] = ref
        if isinstance(prop, dict) and prop.get("type") == "array":
            items = prop.get("items", {})
            item_ref = _ref_name(items)
            if item_ref and "properties" in all_schemas.get(item_ref, {}):
                arrays[key] = item_ref
            elif isinstance(items, dict) and "properties" in items:
                inline = f"{name}.{key}"
                arrays[key] = inline
                _schema_shape(inline, items, all_schemas, out)
    out[name] = {
        "required": set(schema.get("required", [])),
        "properties": set(properties),
        "enums": {key: set(prop["enum"]) for key, prop in properties.items() if isinstance(prop, dict) and "enum" in prop},
        "nested": nested,
        "arrays": arrays,
    }


def load_spec() -> tuple[dict, dict[str, dict]]:
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
            request_body = op.get("requestBody", {})
            body = request_body.get("content", {}).get("application/json", {})
            request = _ref_name(body.get("schema"))

            success = sorted(code for code in op.get("responses", {}) if str(code).startswith("2"))
            status = int(success[0]) if success else 0
            response, is_list = None, False
            if success:
                content = op["responses"][success[0]].get("content", {}).get("application/json", {})
                schema = content.get("schema")
                if isinstance(schema, dict) and schema.get("type") == "array":
                    is_list, response = True, _ref_name(schema.get("items"))
                else:
                    response = _ref_name(schema)

            query: set[str] = set()
            required_query: set[str] = set()
            query_enums: dict[str, set[str]] = {}
            headers: set[str] = set()
            for param in op.get("parameters", []):
                resolved = shared_params.get(_ref_name(param), param) if _ref_name(param) else param
                if resolved.get("in") == "query":
                    query.add(resolved["name"])
                    if resolved.get("required"):
                        required_query.add(resolved["name"])
                    if "enum" in resolved.get("schema", {}):
                        query_enums[resolved["name"]] = set(resolved["schema"]["enum"])
                elif resolved.get("in") == "header":
                    headers.add(resolved["name"])

            operations[(method.upper(), path)] = {
                "request": request,
                "response": response,
                "status": status,
                "list": is_list,
                "query": query,
                "requiredQuery": required_query,
                "queryEnums": query_enums,
                "headers": headers,
                # OpenAPI's default is an optional body; only meaningful when there is one.
                "bodyRequired": bool(request_body.get("required", False)) if request else True,
            }

    schemas: dict[str, dict] = {}
    all_schemas = components.get("schemas", {})
    for name, schema in all_schemas.items():
        _schema_shape(name, schema, all_schemas, schemas)
    return operations, schemas


def _name_map(block: str, name: str) -> dict[str, str]:
    match = re.search(rf"\b{name}\s*=\s*mapOf\(((?:[^()]|\([^()]*\))*)\)", block)
    return dict(_NAME_MAP_ENTRY.findall(match.group(1))) if match else {}


def load_contract_spec() -> tuple[dict, dict[str, dict]]:
    text = CONTRACT_SPEC_PATH.read_text(encoding="utf-8")
    operations_part, _, schemas_part = text.partition("val schemas")

    operations: dict[tuple[str, str], dict] = {}
    for block in _blocks(operations_part, "Operation("):
        if block.strip().startswith("val ") or "String" in block:
            continue  # the data class declaration itself
        method, path = re.findall(r'"([^"]*)"', block)[:2]
        request, response = _named(block, "request"), _named(block, "response")
        body_required = _named(block, "bodyRequired")
        operations[(method, path)] = {
            "request": request.strip('"') if request and request != "null" else None,
            "response": response.strip('"') if response and response != "null" else None,
            "status": int(_named(block, "status") or 0),
            "list": _named(block, "list") == "true",
            "query": _string_set(_named(block, "query")),
            "requiredQuery": _string_set(_named(block, "requiredQuery")),
            "queryEnums": _set_map(block, "queryEnums"),
            "headers": _string_set(_named(block, "headers")),
            "bodyRequired": body_required != "false",
        }

    schemas: dict[str, dict] = {}
    for match in re.finditer(r'"([\w.]+)"\s+to\s+Schema\(', schemas_part):
        block = _blocks(schemas_part[match.start() :], "Schema(")[0]
        schemas[match.group(1)] = {
            "required": _string_set(_named(block, "required")),
            "properties": _string_set(_named(block, "properties")),
            "enums": _set_map(block, "enums"),
            "nested": _name_map(block, "nested"),
            "arrays": _name_map(block, "arrays"),
        }
    return operations, schemas


def _show(value):
    return sorted(value) if isinstance(value, set) else value


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
        for field in OPERATION_FIELDS:
            if spec_ops[key][field] != mock_ops[key][field]:
                errors.append(
                    f"{key[0]} {key[1]}: {field} is {_show(spec_ops[key][field])!r} in the spec "
                    f"but {_show(mock_ops[key][field])!r} in the mock"
                )

    # 2. The mock's schemas are the spec's. The schemas the client sends (request bodies and what
    #    they nest, transitively) are validated all the way down, so their enum values, nested objects
    #    and array items must match too; responses are only shaped.
    request_side: set[str] = {op["request"] for op in mock_ops.values() if op["request"]}
    pending = list(request_side)
    while pending:
        schema = mock_schemas.get(pending.pop(), {})
        for child in [*schema.get("nested", {}).values(), *schema.get("arrays", {}).values()]:
            if child not in request_side:
                request_side.add(child)
                pending.append(child)
    referenced = request_side | {op["response"] for op in mock_ops.values() if op["response"]}
    for name in sorted(referenced):
        if name not in mock_schemas:
            errors.append(f"mock has no schema for '{name}'")
            continue
        if name not in spec_schemas:
            errors.append(f"mock references schema '{name}' not present in the spec")
            continue
        mock, spec = mock_schemas[name], spec_schemas[name]
        fields = ("required", "properties", "enums", "nested", "arrays") if name in request_side else ("required", "properties")
        for field in fields:
            if mock[field] != spec[field]:
                errors.append(f"schema drift in {name}.{field}: spec {_show(spec[field])}; mock {_show(mock[field])}")

    # 3. The client's models match the spec.
    models = load_models(CHECKED_MODEL_FILES)

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

    classified = set(REQUEST_CLASSES) | set(RESPONSE_CLASSES) | set(QUERY_CLASSES)
    unclassified = sorted(set(models) - classified)
    if unclassified:
        errors.append(f"data classes not covered by the contract check (classify them): {unclassified}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("KMP Commerce client contract check FAILED:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("KMP Commerce client matches contracts/commerce.openapi.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
