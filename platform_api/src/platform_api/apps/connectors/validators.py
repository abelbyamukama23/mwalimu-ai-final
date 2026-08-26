"""Validators for JSON Schema definitions and connection configuration payloads."""

from __future__ import annotations

from typing import Any

import jsonschema
from django.core.exceptions import ValidationError as DjangoValidationError
from jsonschema.exceptions import (
    SchemaError,
)
from jsonschema.exceptions import (
    ValidationError as JsonSchemaValidationError,
)
from rest_framework.exceptions import ValidationError as DRFValidationError


def validate_json_schema_definition(
    schema: Any,
    field_name: str = "schema",
) -> None:
    """Validate that a dictionary is a valid Draft 2020-12 / Draft 7 JSON Schema.

    Args:
        schema: The schema object to validate.
        field_name: Field name for error reporting.

    Raises:
        DjangoValidationError: If the schema definition is malformed.
    """
    if not schema:
        return
    if not isinstance(schema, dict):
        raise DjangoValidationError(
            {field_name: "Schema definition must be a valid JSON object/dictionary."}
        )
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise DjangoValidationError(
            {field_name: f"Invalid JSON Schema specification: {exc.message}"}
        ) from exc


def validate_data_against_schema(
    data: Any,
    schema: dict[str, Any] | None,
    field_name: str = "configuration",
) -> None:
    """Validate a data payload against a JSON Schema definition.

    Args:
        data: The payload dictionary to validate.
        schema: The JSON Schema definition.
        field_name: The field name for DRF / Django error formatting.

    Raises:
        DRFValidationError: If data does not conform to the schema.
    """
    if not schema:
        return
    if not isinstance(data, dict):
        raise DRFValidationError({field_name: "Data payload must be a JSON object."})

    try:
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(data)
    except JsonSchemaValidationError as exc:
        path = ".".join(str(p) for p in exc.path) if exc.path else "root"
        raise DRFValidationError(
            {field_name: f"Schema validation failed at '{path}': {exc.message}"}
        ) from exc
