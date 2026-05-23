from __future__ import annotations

from typing import Any


class SchemaValidationError(ValueError):
    pass


def validate_json_schema(schema: dict[str, Any], value: Any, *, path: str = "$") -> list[str]:
    """Small JSON-schema subset validator used to avoid an extra dependency.

    Supports the subset used by skill manifests: object, array, string,
    integer, number, boolean, enum, required, properties, and items.
    """

    errors: list[str] = []
    _validate(schema or {}, value, path, errors)
    return errors


def assert_json_schema(schema: dict[str, Any], value: Any, *, path: str = "$") -> None:
    errors = validate_json_schema(schema, value, path=path)
    if errors:
        raise SchemaValidationError("; ".join(errors))


def _validate(schema: dict[str, Any], value: Any, path: str, errors: list[str]) -> None:
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_matches_type(kind, value) for kind in expected):
            errors.append(f"{path} expected one of {expected}")
            return
    elif expected and not _matches_type(str(expected), value):
        errors.append(f"{path} expected {expected}")
        return

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path} expected one of {enum}")

    if expected == "object" or isinstance(value, dict):
        if not isinstance(value, dict):
            return
        required = schema.get("required") or []
        for field in required:
            if field not in value or value.get(field) in (None, ""):
                errors.append(f"{path}.{field} is required")
        properties = schema.get("properties") or {}
        if isinstance(properties, dict):
            for field, spec in properties.items():
                if field in value and isinstance(spec, dict):
                    _validate(spec, value[field], f"{path}.{field}", errors)
    elif expected == "array" or isinstance(value, list):
        if not isinstance(value, list):
            return
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(item_schema, item, f"{path}[{index}]", errors)


def _matches_type(kind: str, value: Any) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    return True

