"""
Build a **wrapper JSON Schema** from a confirmed BESSER ``DomainModel``.

The wrapper schema is the single contract consumed by:
* Config Workbench form renderer
* Chat-based structured patch validator
* Export / import compatibility checker

It is an M2 → M1 projection — NOT a new truth source.

Type mapping follows the same primitives as BESSER and the existing
Pydantic / JSON Schema generators, but outputs *standard* JSON Schema
(Draft 2020-12 compatible) rather than NGSI-LD.
"""

from __future__ import annotations

import logging
from typing import Any

from besser.BUML.metamodel.structural import (
    DomainModel,
    Class,
    Enumeration,
    Property,
    BinaryAssociation,
    PrimitiveDataType,
    UNLIMITED_MAX_MULTIPLICITY,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primitive type → JSON Schema mapping
# ---------------------------------------------------------------------------

_PRIMITIVE_SCHEMA: dict[str, dict[str, Any]] = {
    "str":       {"type": "string"},
    "int":       {"type": "integer"},
    "float":     {"type": "number"},
    "bool":      {"type": "boolean"},
    "date":      {"type": "string", "format": "date"},
    "datetime":  {"type": "string", "format": "date-time"},
    "time":      {"type": "string", "format": "time"},
    "timedelta": {"type": "string", "description": "ISO-8601 duration"},
    "any":       {},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_wrapper_schema(
    domain_model: DomainModel,
    *,
    schema_id: str | None = None,
    include_associations: bool = True,
) -> dict[str, Any]:
    """Build a JSON Schema from *domain_model*.

    Parameters
    ----------
    domain_model : DomainModel
        The confirmed M2 centre representation.
    schema_id : str | None
        Optional ``$id`` for the root schema.
    include_associations : bool
        If *True*, association ends are included as ``$ref`` or array-of-``$ref``
        properties on owning classes.

    Returns
    -------
    dict
        A JSON Schema document with ``$defs`` for every class and enum.
    """
    defs: dict[str, Any] = {}

    # ---- Enumerations ------------------------------------------------
    for enum in domain_model.get_enumerations():
        defs[enum.name] = _enum_schema(enum)

    # ---- Classes -----------------------------------------------------
    class_list = list(domain_model.get_classes())
    for cls in class_list:
        defs[cls.name] = _class_schema(cls, domain_model, include_associations)

    # ---- Root schema -------------------------------------------------
    root: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": domain_model.name,
        "description": f"Wrapper schema for domain '{domain_model.name}'",
        "type": "object",
        "$defs": defs,
    }
    if schema_id:
        root["$id"] = schema_id

    # Root properties: one key per domain class, each an array of instances
    root["properties"] = {}
    for cls in class_list:
        root["properties"][cls.name] = {
            "type": "array",
            "items": {"$ref": f"#/$defs/{cls.name}"},
            "description": f"Instances of {cls.name}",
        }

    logger.info(
        "Wrapper schema built: %d class defs, %d enum defs",
        len(class_list),
        len(list(domain_model.get_enumerations())),
    )
    return root


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _enum_schema(enum: Enumeration) -> dict[str, Any]:
    """Build a JSON Schema fragment for an enumeration."""
    literals = sorted(lit.name for lit in enum.literals)
    return {
        "type": "string",
        "enum": literals,
        "description": (
            getattr(enum.metadata, "description", "") if enum.metadata else ""
        ),
    }


def _class_schema(
    cls: Class,
    domain_model: DomainModel,
    include_associations: bool,
) -> dict[str, Any]:
    """Build a JSON Schema fragment for a class."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    # ---- Attributes --------------------------------------------------
    for attr in sorted(cls.attributes, key=lambda a: a.name):
        prop_schema = _property_schema(attr)
        properties[attr.name] = prop_schema
        if not attr.is_optional and attr.default_value is None:
            required.append(attr.name)

    # ---- Association ends (as reference properties) ------------------
    if include_associations:
        for assoc in cls.associations:
            if not isinstance(assoc, BinaryAssociation):
                continue
            ends = list(assoc.ends)
            for end in ends:
                # Skip the end that points TO this class — we want the
                # "outgoing" end (the one whose type != cls).
                if end.type == cls:
                    continue
                prop_schema = _association_end_schema(end)
                properties[end.name] = prop_schema
                # Required if min multiplicity > 0
                if end.multiplicity.min > 0:
                    required.append(end.name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
        "description": (
            getattr(cls.metadata, "description", "") if cls.metadata else ""
        ),
    }
    if required:
        schema["required"] = sorted(set(required))
    if cls.is_abstract:
        schema["x-abstract"] = True

    return schema


def _property_schema(prop: Property) -> dict[str, Any]:
    """Map a B-UML Property to a JSON Schema property."""
    base = _type_to_schema(prop.type)

    # Multi-valued → array
    if prop.multiplicity.max > 1 or prop.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY:
        schema: dict[str, Any] = {
            "type": "array",
            "items": base,
        }
        if prop.multiplicity.min > 0:
            schema["minItems"] = prop.multiplicity.min
        if prop.multiplicity.max != UNLIMITED_MAX_MULTIPLICITY:
            schema["maxItems"] = prop.multiplicity.max
    else:
        schema = dict(base)

    # Optional → nullable
    if prop.is_optional:
        if "type" in schema:
            schema["type"] = [schema["type"], "null"]
        else:
            schema["oneOf"] = [base, {"type": "null"}]

    # Default value
    if prop.default_value is not None:
        schema["default"] = prop.default_value

    # Metadata
    if prop.is_id:
        schema["x-is-id"] = True
    if prop.is_read_only:
        schema["readOnly"] = True
    if prop.metadata and prop.metadata.description:
        schema["description"] = prop.metadata.description

    return schema


def _association_end_schema(end: Property) -> dict[str, Any]:
    """Map an association end to a JSON Schema reference property."""
    ref = {"$ref": f"#/$defs/{end.type.name}"}

    if end.multiplicity.max > 1 or end.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY:
        schema: dict[str, Any] = {
            "type": "array",
            "items": ref,
            "description": f"Association to {end.type.name}",
        }
        if end.multiplicity.min > 0:
            schema["minItems"] = end.multiplicity.min
        if end.multiplicity.max != UNLIMITED_MAX_MULTIPLICITY:
            schema["maxItems"] = end.multiplicity.max
    else:
        schema = dict(ref)
        schema["description"] = f"Association to {end.type.name}"

    if end.is_composite:
        schema["x-composite"] = True

    return schema


def _type_to_schema(type_obj: Any) -> dict[str, Any]:
    """Convert a B-UML type to a JSON Schema type fragment."""
    if isinstance(type_obj, PrimitiveDataType):
        return dict(_PRIMITIVE_SCHEMA.get(type_obj.name, {"type": "string"}))
    if isinstance(type_obj, Enumeration):
        return {"$ref": f"#/$defs/{type_obj.name}"}
    if isinstance(type_obj, Class):
        return {"$ref": f"#/$defs/{type_obj.name}"}
    # Fallback
    return {"type": "string"}
