#!/usr/bin/env python3
"""Guard against drift between the KMP Identity client and its contract (IDN-702).

Parses ``contracts/identity.openapi.yaml`` and checks it against:

* the operations projected in ``IdentityContractSpec.kt`` (the spec-derived mock), and
* the request/response models in ``AuthModels.kt`` (the client the app actually ships).

If an endpoint is added/removed/renamed, or a schema field is added/removed/renamed on
either side, this fails — so a client change that outpaces the contract (or vice versa)
cannot merge until both are reconciled. Run locally with::

    python scripts/check_mobile_identity_contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "contracts" / "identity.openapi.yaml"
CONTRACT_SPEC_PATH = (
    REPO_ROOT
    / "mobile"
    / "shared"
    / "src"
    / "commonTest"
    / "kotlin"
    / "com"
    / "nutriplan"
    / "shared"
    / "contract"
    / "IdentityContractSpec.kt"
)
MODELS_PATH = (
    REPO_ROOT
    / "mobile"
    / "shared"
    / "src"
    / "commonMain"
    / "kotlin"
    / "com"
    / "nutriplan"
    / "shared"
    / "data"
    / "model"
    / "AuthModels.kt"
)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

# Contract schema name -> the Kotlin data class(es) that mirror it on the wire.
SCHEMA_TO_CLASSES: dict[str, list[str]] = {
    "RegisterRequest": ["RegisterRequest"],
    "LoginRequest": ["LoginRequest"],
    "OAuthRequest": ["OAuthRequest"],
    "RefreshRequest": ["RefreshRequest"],
    "AuthResponse": ["AuthResponse"],
    "UserProfileResponse": ["UserProfile"],
    "UpdateProfileRequest": ["UpdateProfileRequest"],
    "DietaryPreferencesRequest": [
        "DietaryPreferences",
        "UpdateDietaryPreferencesRequest",
    ],
    "MacroTargets": ["DietaryMacroTargets"],
    "AvatarUploadRequest": ["AvatarUploadUrlRequest"],
    "AvatarUploadResponse": ["AvatarUploadUrlResponse"],
    "AvatarConfirmRequest": ["AvatarConfirmRequest"],
    "Problem": ["Problem"],
}

_OPERATION_RE = re.compile(
    r'Operation\(\s*"([A-Z]+)",\s*"([^"]+)",\s*(?:"([^"]+)"|null),\s*(?:"([^"]+)"|null),\s*(\d+)',
    re.DOTALL,
)
_CLASS_RE = re.compile(r"data class\s+(\w+)\s*\((.*?)\n\)", re.DOTALL)
_FIELD_RE = re.compile(r"val\s+(\w+)\s*:")


def _fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_spec() -> tuple[set[tuple[str, str]], dict[str, dict[str, set[str]]]]:
    document = yaml.safe_load(SPEC_PATH.read_text())

    operations: set[tuple[str, str]] = set()
    for path, item in document.get("paths", {}).items():
        for method in item:
            if method.lower() in HTTP_METHODS:
                operations.add((method.upper(), path))

    schemas: dict[str, dict[str, set[str]]] = {}
    for name, schema in document.get("components", {}).get("schemas", {}).items():
        schemas[name] = {
            "required": set(schema.get("required", [])),
            "properties": set(schema.get("properties", {})),
        }
    return operations, schemas


def load_contract_spec() -> tuple[set[tuple[str, str]], set[str]]:
    text = CONTRACT_SPEC_PATH.read_text()
    operations: set[tuple[str, str]] = set()
    referenced_schemas: set[str] = set()
    for method, path, request_schema, response_schema, _ in _OPERATION_RE.findall(text):
        operations.add((method, path))
        if response_schema:
            referenced_schemas.add(response_schema)
        if request_schema:
            referenced_schemas.add(request_schema)
    return operations, referenced_schemas


def load_client_models() -> dict[str, set[str]]:
    text = MODELS_PATH.read_text()
    return {
        name: set(_FIELD_RE.findall(body)) for name, body in _CLASS_RE.findall(text)
    }


def check() -> list[str]:
    errors: list[str] = []
    spec_operations, spec_schemas = load_spec()
    contract_operations, contract_schema_refs = load_contract_spec()
    models = load_client_models()

    if spec_operations != contract_operations:
        only_spec = sorted(spec_operations - contract_operations)
        only_spec_mock = sorted(contract_operations - spec_operations)
        _fail(
            errors,
            f"operation drift: only in spec {only_spec}; only in mock {only_spec_mock}",
        )

    for schema_name in sorted(contract_schema_refs):
        if schema_name not in spec_schemas:
            _fail(
                errors,
                f"mock references schema '{schema_name}' not present in the spec",
            )

    for schema_name, class_names in sorted(SCHEMA_TO_CLASSES.items()):
        schema = spec_schemas.get(schema_name)
        if schema is None:
            _fail(
                errors, f"client maps '{schema_name}' but the spec has no such schema"
            )
            continue
        for class_name in class_names:
            if class_name not in models:
                _fail(
                    errors, f"client class '{class_name}' for '{schema_name}' not found"
                )
                continue
            if models[class_name] != schema["properties"]:
                only_client = sorted(models[class_name] - schema["properties"])
                only_spec = sorted(schema["properties"] - models[class_name])
                _fail(
                    errors,
                    f"field drift in {class_name} ({schema_name}): "
                    f"only in client {only_client}; only in spec {only_spec}",
                )

    mapped_classes = {name for names in SCHEMA_TO_CLASSES.values() for name in names}
    unmapped = sorted(set(models) - mapped_classes)
    if unmapped:
        _fail(
            errors, f"client data classes not covered by the contract check: {unmapped}"
        )

    # IDN-401: the KMP client must cover the full OpenAPI contract — every documented
    # schema (including error/problem schemas) must be mapped to a client model.
    unmapped_spec_schemas = sorted(set(spec_schemas) - set(SCHEMA_TO_CLASSES))
    for schema_name in unmapped_spec_schemas:
        _fail(
            errors,
            f"OpenAPI schema '{schema_name}' is not mapped to a client model; "
            "the KMP Identity client must cover the full contract",
        )

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("KMP Identity client contract check FAILED:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("KMP Identity client matches contracts/identity.openapi.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
