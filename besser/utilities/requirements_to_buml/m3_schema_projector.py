"""
M3 Schema Projector — the SINGLE source of truth for all pipeline schemas.

**This module replaces the old hand-written ``schemas.py``.**

It introspects ``besser.BUML.metamodel.structural.structural`` (the M3
layer) at import time and dynamically builds:

1. **Pydantic models** — ``CandidateProperty``, ``CandidateClass``,
   ``CandidateModel``, etc. via ``pydantic.create_model()``.
2. **JSON Schema** — ``project_m3_to_json_schema()`` returns
   ``CandidateModel.model_json_schema()``, the exact schema embedded
   in the LLM prompt to constrain output format.

Design rationale (02 §2.1):
    "The first stage is NOT 'roughly align' — it is directly using the
     Structural metamodel as the source meta-metamodel for model
     transformation."

Downstream modules import from here instead of the deleted ``schemas.py``::

    from besser.utilities.requirements_to_buml.m3_schema_projector import (
        CandidateModel, CandidateClass, CandidateProperty, ...
        NormalizedCandidateModel, ReviewSummary, ValidationReport, ...
        project_m3_to_json_schema,
    )
"""

from __future__ import annotations

import inspect
from datetime import datetime, date, time, timedelta
from typing import Any

from pydantic import BaseModel, Field, create_model

from besser.BUML.metamodel.structural.structural import (
    Property,
    Class,
    BinaryAssociation,
    Enumeration,
    EnumerationLiteral,
    Constraint,
    Multiplicity,
    DomainModel,
    Type,
    Element,
)


# =====================================================================
# 1. M3 Introspection
# =====================================================================

def _introspect_init(cls: type) -> dict[str, dict]:
    """Extract ``{param: {py_type, default, required}}`` from ``cls.__init__``."""
    sig = inspect.signature(cls.__init__)
    try:
        from typing import get_type_hints
        hints = get_type_hints(cls.__init__)
    except Exception:
        hints = {}

    result = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = hints.get(name, param.annotation)
        has_default = param.default is not inspect.Parameter.empty
        result[name] = {
            "py_type": ann if ann is not inspect.Parameter.empty else Any,
            "default": param.default if has_default else ...,
            "required": not has_default,
        }
    return result


# =====================================================================
# 2. M3 → Python type mapping for LLM-facing schema fields
# =====================================================================

def _to_schema_type(py_type: Any, param_name: str) -> type:
    """Map an M3 init parameter type to the Python type for Pydantic field.

    Rules:
    - ``Type`` / ``Element`` references → ``str`` (name reference)
    - ``Multiplicity`` → ``str`` (serialised "min..max")
    - ``set[X]`` / ``list[X]`` → ``str`` (not exposed to LLM as collections)
    - Primitives pass through
    """
    if py_type is inspect.Parameter.empty or py_type is Any:
        return Any
    if isinstance(py_type, type):
        if issubclass(py_type, (Type, Element, Multiplicity)):
            return str
        if py_type in (str, int, float, bool):
            return py_type
        if issubclass(py_type, (datetime, date, time, timedelta)):
            return str
    return Any


def _to_schema_default(raw_default: Any) -> Any:
    """Convert an M3 default value to JSON-serialisable form."""
    if raw_default is ...:
        return ...
    if isinstance(raw_default, Multiplicity):
        m = raw_default
        return f"{m.min}..{'*' if m.max == 9999 else m.max}"
    if isinstance(raw_default, (datetime, date, time)):
        return None
    if raw_default is None:
        return None
    return raw_default


# =====================================================================
# 3. Build Pydantic models from introspection
# =====================================================================

# --- Which M3 init params to expose to LLM (explicit curation) ---
_PROPERTY_EXPOSE = {
    "name", "type", "visibility", "is_id", "is_read_only",
    "is_optional", "default_value", "multiplicity",
}

_ASSOC_END_EXPOSE = {
    "role": "name",  # Property.name → role in association context
    "type": "type",
    "multiplicity": "multiplicity",
    "is_navigable": "is_navigable",
    "is_composite": "is_composite",
}


def _build_model_fields(
    cls: type,
    expose: set[str],
    *,
    type_overrides: dict[str, type] | None = None,
    extra_fields: dict | None = None,
) -> dict:
    """Build ``create_model`` field definitions from M3 introspection.

    Args:
        cls: The M3 meta-class to introspect.
        expose: Set of ``__init__`` param names to include.
        type_overrides: ``{param_name: python_type}`` to force a type.
        extra_fields: Additional fields not from M3 (e.g. ``description``).

    Returns:
        dict suitable for ``**kwargs`` to ``create_model()``.
    """
    m3 = _introspect_init(cls)
    overrides = type_overrides or {}
    fields = {}

    for pname in expose:
        if pname not in m3:
            continue
        info = m3[pname]
        py_type = overrides.get(pname, _to_schema_type(info["py_type"], pname))
        default = _to_schema_default(info["default"])

        if default is ...:
            fields[pname] = (py_type, ...)
        else:
            fields[pname] = (py_type, default)

    if extra_fields:
        fields.update(extra_fields)

    return fields


# ------------------------------------------------------------------
# CandidateProperty  (from Property.__init__)
# ------------------------------------------------------------------
_prop_fields = _build_model_fields(
    Property, _PROPERTY_EXPOSE,
    type_overrides={"type": str, "multiplicity": str, "default_value": Any},
    extra_fields={
        "description": (str, ""),
        "extensions": (dict[str, Any], Field(default_factory=dict)),
    },
)

CandidateProperty = create_model("CandidateProperty", **_prop_fields)
CandidateProperty.__doc__ = (
    "Attribute of a candidate class — fields auto-projected from "
    "``Property.__init__`` in the BESSER Structural metamodel."
)

# ------------------------------------------------------------------
# CandidateEnumerationLiteral  (from EnumerationLiteral.__init__)
# ------------------------------------------------------------------
CandidateEnumerationLiteral = create_model(
    "CandidateEnumerationLiteral",
    name=(str, ...),
    description=(str, ""),
)

# ------------------------------------------------------------------
# CandidateEnumeration  (from Enumeration.__init__)
# ------------------------------------------------------------------
CandidateEnumeration = create_model(
    "CandidateEnumeration",
    name=(str, ...),
    literals=(list[CandidateEnumerationLiteral], ...),
    description=(str, ""),
)

# ------------------------------------------------------------------
# CandidateClass  (from Class.__init__)
# ------------------------------------------------------------------
CandidateClass = create_model(
    "CandidateClass",
    name=(str, ...),
    is_abstract=(bool, False),
    attributes=(list[CandidateProperty], Field(default_factory=list)),
    description=(str, ""),
    extensions=(dict[str, Any], Field(default_factory=dict)),
)

# ------------------------------------------------------------------
# CandidateAssociationEnd  (from Property.__init__, subset)
# ------------------------------------------------------------------
CandidateAssociationEnd = create_model(
    "CandidateAssociationEnd",
    role=(str, ...),
    type=(str, ...),
    multiplicity=(str, "1..1"),
    is_navigable=(bool, True),
    is_composite=(bool, False),
)

# ------------------------------------------------------------------
# CandidateAssociation  (from BinaryAssociation.__init__)
# ------------------------------------------------------------------
CandidateAssociation = create_model(
    "CandidateAssociation",
    name=(str, ...),
    end1=(CandidateAssociationEnd, ...),
    end2=(CandidateAssociationEnd, ...),
    description=(str, ""),
)

# ------------------------------------------------------------------
# CandidateConstraint  (from Constraint.__init__)
# ------------------------------------------------------------------
CandidateConstraint = create_model(
    "CandidateConstraint",
    name=(str, ...),
    context=(str, ...),
    expression=(str, ...),
    language=(str, "OCL"),
    description=(str, ""),
)

# ------------------------------------------------------------------
# CandidateUnresolvedItem  (pipeline artifact, not from M3)
# ------------------------------------------------------------------
CandidateUnresolvedItem = create_model(
    "CandidateUnresolvedItem",
    source_text=(str, ...),
    reason=(str, ...),
    suggestion=(str, ""),
)

# ------------------------------------------------------------------
# CandidateModel  (top-level, mirrors DomainModel structure)
# ------------------------------------------------------------------
CandidateModel = create_model(
    "CandidateModel",
    domain_name=(str, ""),
    classes=(list[CandidateClass], Field(default_factory=list)),
    enumerations=(list[CandidateEnumeration], Field(default_factory=list)),
    associations=(list[CandidateAssociation], Field(default_factory=list)),
    constraints=(list[CandidateConstraint], Field(default_factory=list)),
    unresolved_items=(list[CandidateUnresolvedItem], Field(default_factory=list)),
    metadata=(dict[str, Any], Field(default_factory=dict)),
)
CandidateModel.__doc__ = (
    "Top-level candidate model — an M2 domain metamodel expressed as JSON. "
    "All sub-model fields are auto-projected from BESSER Structural metamodel."
)


# =====================================================================
# 4. Normalized models (= Candidate models + sidecar)
#    MDE: normalisation transforms an M2 instance into a cleaned M2
#    instance of the SAME type. Only NormalizedCandidateModel adds
#    sidecar_items.
# =====================================================================

# Aliases — same type, normalisation just cleans values
NormalizedProperty = CandidateProperty
NormalizedClass = CandidateClass
NormalizedEnumerationLiteral = CandidateEnumerationLiteral
NormalizedEnumeration = CandidateEnumeration
NormalizedAssociationEnd = CandidateAssociationEnd
NormalizedAssociation = CandidateAssociation
NormalizedConstraint = CandidateConstraint

NormalizedCandidateModel = create_model(
    "NormalizedCandidateModel",
    domain_name=(str, ""),
    classes=(list[CandidateClass], Field(default_factory=list)),
    enumerations=(list[CandidateEnumeration], Field(default_factory=list)),
    associations=(list[CandidateAssociation], Field(default_factory=list)),
    constraints=(list[CandidateConstraint], Field(default_factory=list)),
    unresolved_items=(list[CandidateUnresolvedItem], Field(default_factory=list)),
    sidecar_items=(list[dict[str, Any]], Field(default_factory=list)),
    metadata=(dict[str, Any], Field(default_factory=dict)),
)


# =====================================================================
# 5. Review & Validation types (pipeline artifacts, not M3)
# =====================================================================

class ReviewWarning(BaseModel):
    severity: str = "warning"
    category: str = ""
    message: str = ""
    related_element: str = ""


class ReviewSummary(BaseModel):
    class_names: list[str] = Field(default_factory=list)
    enumeration_names: list[str] = Field(default_factory=list)
    association_names: list[str] = Field(default_factory=list)
    constraint_names: list[str] = Field(default_factory=list)
    unresolved_items: list[CandidateUnresolvedItem] = Field(default_factory=list)
    warnings: list[ReviewWarning] = Field(default_factory=list)
    sidecar_item_count: int = 0
    round_trip_risks: list[str] = Field(default_factory=list)
    high_priority_checks: list[str] = Field(default_factory=list)


class SidecarEntry(BaseModel):
    owner_class: str
    field_name: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class ReviewSidecar(BaseModel):
    entries: list[SidecarEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    severity: str = "error"
    path: str = ""
    message: str = ""


class ValidationReport(BaseModel):
    is_valid: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)


# =====================================================================
# 6. Public API — JSON Schema projection
# =====================================================================

def project_m3_to_json_schema() -> dict:
    """Return the CandidateModel JSON Schema, auto-derived from M3.

    This is the **authoritative** schema embedded in the LLM prompt.
    It is generated by Pydantic from models that were themselves
    generated by introspecting BESSER Structural metamodel.
    """
    return CandidateModel.model_json_schema()


def get_m3_property_fields() -> dict[str, dict]:
    """Return raw introspection of ``Property.__init__`` (for debugging)."""
    return _introspect_init(Property)


def get_m3_introspection_report() -> dict:
    """Summary of all introspected meta-classes (for debugging)."""
    return {
        "Property": _introspect_init(Property),
        "Class": _introspect_init(Class),
        "BinaryAssociation": _introspect_init(BinaryAssociation),
        "Enumeration": _introspect_init(Enumeration),
        "EnumerationLiteral": _introspect_init(EnumerationLiteral),
        "Constraint": _introspect_init(Constraint),
        "Multiplicity": _introspect_init(Multiplicity),
        "DomainModel": _introspect_init(DomainModel),
    }
