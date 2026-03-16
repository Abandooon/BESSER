"""
Deterministic normalization of a ``CandidateModel`` into a
``NormalizedCandidateModel``.

Normalization rules (from 02_需求到候选B-UML规范 §7):
- 7.1 Name normalization: PascalCase classes, consistent attribute casing,
       UPPER_CASE enum literals, de-duplicate synonyms.
- 7.2 Type normalization: map to BESSER-supported primitives, collect
       enums, route complex sub-structures to sidecar.
- 7.3 Relationship normalization: re-check if string attrs should be
       associations.
- 7.4 Constraint normalization: prefer multiplicity / enum over free text.
- 7.5 Sidecar routing: extensions that cannot round-trip → sidecar_items.
"""

from __future__ import annotations

import re
import logging
from typing import Any

from besser.utilities.requirements_to_buml.schemas import (
    CandidateModel,
    CandidateClass,
    CandidateProperty,
    NormalizedCandidateModel,
    NormalizedClass,
    NormalizedProperty,
    NormalizedEnumeration,
    NormalizedEnumerationLiteral,
    NormalizedAssociation,
    NormalizedAssociationEnd,
    NormalizedConstraint,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------

def _to_pascal_case(name: str) -> str:
    """Convert an arbitrary name to PascalCase."""
    # Already PascalCase? Quick check
    if name and name[0].isupper() and "_" not in name and " " not in name:
        return name
    # Split on underscores, spaces, or camelCase boundaries
    parts = re.sub(r"([a-z])([A-Z])", r"\1_\2", name).replace("-", "_").replace(" ", "_").split("_")
    return "".join(p.capitalize() for p in parts if p)


def _to_snake_case(name: str) -> str:
    """Convert an arbitrary name to snake_case."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return s.replace("-", "_").replace(" ", "_").lower()


def _to_upper_case(name: str) -> str:
    """Convert a name to UPPER_SNAKE_CASE for enum literals."""
    return _to_snake_case(name).upper()


# ---------------------------------------------------------------------------
# Type normalization
# ---------------------------------------------------------------------------

# Mapping from loose type names to BESSER PrimitiveDataType names
_TYPE_ALIASES: dict[str, str] = {
    "string": "str",
    "text": "str",
    "integer": "int",
    "long": "int",
    "double": "float",
    "number": "float",
    "boolean": "bool",
    "timestamp": "datetime",
    "duration": "timedelta",
}

_VALID_PRIMITIVES = {"str", "int", "float", "bool", "date", "datetime", "time", "timedelta", "any"}


def _normalize_type_name(
    raw_type: str,
    known_classes: set[str],
    known_enums: set[str],
) -> str:
    """Map *raw_type* to a valid BESSER type reference."""
    lower = raw_type.lower().strip()
    # 1. Direct alias match
    if lower in _TYPE_ALIASES:
        return _TYPE_ALIASES[lower]
    if lower in _VALID_PRIMITIVES:
        return lower
    # 2. Known enum or class (case-insensitive lookup, return canonical name)
    for n in known_enums:
        if n.lower() == lower:
            return n
    for n in known_classes:
        if n.lower() == lower:
            return n
    # 3. Attempt PascalCase match
    pascal = _to_pascal_case(raw_type)
    if pascal in known_classes or pascal in known_enums:
        return pascal
    # 4. Fall back to str with a warning
    logger.warning("Unknown type '%s' — falling back to 'str'", raw_type)
    return "str"


# ---------------------------------------------------------------------------
# Sidecar extension routing
# ---------------------------------------------------------------------------

# Extension keys that should be routed to the sidecar
_SIDECAR_EXTENSION_KEYS = {
    "configurableFieldSpecs",
    "configurable_field_specs",
    "defaultTriggerEvents",
    "default_trigger_events",
    "parameterSchemaRef",
    "parameter_schema_ref",
    "parameterBindings",
    "parameter_bindings",
    "retryPolicy",
    "retry_policy",
    "rollbackHint",
    "rollback_hint",
    "editorHints",
    "editor_hints",
    "uiDisplayHints",
    "ui_display_hints",
}


def _extract_sidecar_items(
    class_name: str,
    extensions: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract sidecar-worthy entries from extensions."""
    items = []
    for key, value in extensions.items():
        if key in _SIDECAR_EXTENSION_KEYS or isinstance(value, (dict, list)):
            items.append({
                "owner_class": class_name,
                "field_name": key,
                "kind": _to_snake_case(key),
                "payload": value if isinstance(value, dict) else {"value": value},
                "description": "",
            })
    return items


# ---------------------------------------------------------------------------
# Multiplicity normalization
# ---------------------------------------------------------------------------

def _normalize_multiplicity(raw: str) -> str:
    """Ensure a multiplicity string is in canonical ``min..max`` form."""
    raw = raw.strip()
    if not raw:
        return "1..1"
    if raw == "*":
        return "0..*"
    if ".." in raw:
        parts = raw.split("..")
        lo = parts[0].strip()
        hi = parts[1].strip() if len(parts) > 1 else lo
        lo = lo if lo != "*" else "0"
        hi = hi if hi else lo
        return f"{lo}..{hi}"
    # single number
    if raw.isdigit():
        return f"{raw}..{raw}"
    return "1..1"


# ---------------------------------------------------------------------------
# Main normalization
# ---------------------------------------------------------------------------

def normalize_candidate(candidate: CandidateModel) -> NormalizedCandidateModel:
    """Normalize a ``CandidateModel`` into a ``NormalizedCandidateModel``.

    This is a **deterministic** pass — no LLM calls.  It applies naming
    conventions, type mappings, sidecar extraction, and multiplicity
    canonicalization.
    """
    # Build lookup sets for type resolution
    known_classes = {_to_pascal_case(c.name) for c in candidate.classes}
    known_enums = {_to_pascal_case(e.name) for e in candidate.enumerations}

    sidecar_items: list[dict[str, Any]] = []

    # --- Normalize enumerations -------------------------------------------
    norm_enums: list[NormalizedEnumeration] = []
    for enum in candidate.enumerations:
        norm_literals = [
            NormalizedEnumerationLiteral(
                name=_to_upper_case(lit.name),
                description=lit.description,
            )
            for lit in enum.literals
        ]
        norm_enums.append(NormalizedEnumeration(
            name=_to_pascal_case(enum.name),
            literals=norm_literals,
            description=enum.description,
        ))

    # --- Normalize classes ------------------------------------------------
    norm_classes: list[NormalizedClass] = []
    for cls in candidate.classes:
        pascal_name = _to_pascal_case(cls.name)
        cls_sidecar = _extract_sidecar_items(pascal_name, cls.extensions)
        sidecar_items.extend(cls_sidecar)

        norm_attrs: list[NormalizedProperty] = []
        for attr in cls.attributes:
            snake_name = _to_snake_case(attr.name)
            resolved_type = _normalize_type_name(attr.type, known_classes, known_enums)

            # Extract attribute-level sidecar items
            attr_sidecar = _extract_sidecar_items(
                f"{pascal_name}.{snake_name}", attr.extensions
            )
            sidecar_items.extend(attr_sidecar)

            # Keep only non-sidecar extensions
            remaining_ext = {
                k: v for k, v in attr.extensions.items()
                if k not in _SIDECAR_EXTENSION_KEYS and not isinstance(v, (dict, list))
            }

            norm_attrs.append(NormalizedProperty(
                name=snake_name,
                type=resolved_type,
                visibility=attr.visibility,
                is_id=attr.is_id,
                is_read_only=attr.is_read_only,
                is_optional=attr.is_optional,
                default_value=attr.default_value,
                multiplicity=_normalize_multiplicity(attr.multiplicity),
                description=attr.description,
                extensions=remaining_ext,
            ))

        # Keep only non-sidecar class-level extensions
        remaining_cls_ext = {
            k: v for k, v in cls.extensions.items()
            if k not in _SIDECAR_EXTENSION_KEYS and not isinstance(v, (dict, list))
        }

        norm_classes.append(NormalizedClass(
            name=pascal_name,
            is_abstract=cls.is_abstract,
            attributes=norm_attrs,
            description=cls.description,
            extensions=remaining_cls_ext,
        ))

    # --- Normalize associations -------------------------------------------
    norm_assocs: list[NormalizedAssociation] = []
    for assoc in candidate.associations:
        norm_assocs.append(NormalizedAssociation(
            name=assoc.name,
            end1=NormalizedAssociationEnd(
                role=_to_snake_case(assoc.end1.role),
                type=_to_pascal_case(assoc.end1.type),
                multiplicity=_normalize_multiplicity(assoc.end1.multiplicity),
                is_navigable=assoc.end1.is_navigable,
                is_composite=assoc.end1.is_composite,
            ),
            end2=NormalizedAssociationEnd(
                role=_to_snake_case(assoc.end2.role),
                type=_to_pascal_case(assoc.end2.type),
                multiplicity=_normalize_multiplicity(assoc.end2.multiplicity),
                is_navigable=assoc.end2.is_navigable,
                is_composite=assoc.end2.is_composite,
            ),
            description=assoc.description,
        ))

    # --- Normalize constraints --------------------------------------------
    norm_constraints: list[NormalizedConstraint] = []
    for constr in candidate.constraints:
        norm_constraints.append(NormalizedConstraint(
            name=_to_snake_case(constr.name),
            context=_to_pascal_case(constr.context),
            expression=constr.expression,
            language=constr.language,
            description=constr.description,
        ))

    result = NormalizedCandidateModel(
        domain_name=_to_pascal_case(candidate.domain_name) if candidate.domain_name else "Domain",
        classes=norm_classes,
        enumerations=norm_enums,
        associations=norm_assocs,
        constraints=norm_constraints,
        unresolved_items=list(candidate.unresolved_items),
        sidecar_items=sidecar_items,
        metadata=candidate.metadata,
    )

    logger.info(
        "Normalization complete: %d classes, %d enums, %d assocs, %d sidecar items",
        len(result.classes),
        len(result.enumerations),
        len(result.associations),
        len(result.sidecar_items),
    )
    return result
