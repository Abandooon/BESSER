"""
Pydantic schemas that act as the **M3 JSON-Schema projection** consumed by
the first-stage LLM, as well as the intermediate data structures for the
entire requirements-to-B-UML pipeline.

Hierarchy
---------
``CandidateModel``           – raw LLM extraction output
``NormalizedCandidateModel`` – deterministically cleaned / enriched
``ReviewSummary``            – human-facing audit checklist
``ReviewSidecar``            – structured support semantics not in WME main chain
``ValidationReport``         – schema + reference-integrity check results

Design notes
~~~~~~~~~~~~
* The schemas deliberately mirror the *Structural metamodel* concepts
  (``Class``, ``Property``, ``BinaryAssociation``, ``Enumeration``,
  ``Constraint``) so that every candidate JSON is a well-formed M3
  instance.
* Fields that cannot yet round-trip through the WME class-diagram
  JSON are kept in ``extensions`` dicts and later routed to the
  ``ReviewSidecar``.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared value types
# ---------------------------------------------------------------------------

class PrimitiveTypeName(str, Enum):
    """Allowed primitive type names (must align with BESSER PrimitiveDataType)."""
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    DATE = "date"
    DATETIME = "datetime"
    TIME = "time"
    TIMEDELTA = "timedelta"
    ANY = "any"


class VisibilityKind(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    PACKAGE = "package"


# ---------------------------------------------------------------------------
# Candidate-level atoms
# ---------------------------------------------------------------------------

class CandidateProperty(BaseModel):
    """One attribute of a candidate class."""
    name: str
    type: str  # may be primitive name, enum name, or class name
    visibility: VisibilityKind = VisibilityKind.PUBLIC
    is_id: bool = False
    is_read_only: bool = False
    is_optional: bool = False
    default_value: Any | None = None
    multiplicity: str = "1..1"  # e.g. "0..*", "1..1"
    description: str = ""
    extensions: dict[str, Any] = Field(default_factory=dict)


class CandidateEnumerationLiteral(BaseModel):
    name: str
    description: str = ""


class CandidateEnumeration(BaseModel):
    name: str
    literals: list[CandidateEnumerationLiteral]
    description: str = ""


class CandidateClass(BaseModel):
    name: str
    is_abstract: bool = False
    attributes: list[CandidateProperty] = Field(default_factory=list)
    description: str = ""
    extensions: dict[str, Any] = Field(default_factory=dict)


class CandidateAssociationEnd(BaseModel):
    """One end of a binary association."""
    role: str  # role name (lowerCamelCase)
    type: str  # class name the end points to
    multiplicity: str = "1..1"
    is_navigable: bool = True
    is_composite: bool = False


class CandidateAssociation(BaseModel):
    name: str
    end1: CandidateAssociationEnd
    end2: CandidateAssociationEnd
    description: str = ""


class CandidateConstraint(BaseModel):
    name: str
    context: str  # class name
    expression: str
    language: str = "OCL"
    description: str = ""


class CandidateUnresolvedItem(BaseModel):
    """An item the LLM could not confidently classify."""
    source_text: str
    reason: str
    suggestion: str = ""


# ---------------------------------------------------------------------------
# CandidateModel — raw LLM output
# ---------------------------------------------------------------------------

class CandidateModel(BaseModel):
    """Schema for the first-stage LLM candidate extraction.

    This is the **M3 projection schema** — an instance of this schema
    is a candidate M2 domain metamodel expressed as JSON.
    """
    domain_name: str = ""
    classes: list[CandidateClass] = Field(default_factory=list)
    enumerations: list[CandidateEnumeration] = Field(default_factory=list)
    associations: list[CandidateAssociation] = Field(default_factory=list)
    constraints: list[CandidateConstraint] = Field(default_factory=list)
    unresolved_items: list[CandidateUnresolvedItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# NormalizedCandidateModel — cleaned & enriched
# ---------------------------------------------------------------------------

class NormalizedProperty(BaseModel):
    """Post-normalization attribute."""
    name: str
    type: str
    visibility: VisibilityKind = VisibilityKind.PUBLIC
    is_id: bool = False
    is_read_only: bool = False
    is_optional: bool = False
    default_value: Any | None = None
    multiplicity: str = "1..1"
    description: str = ""
    extensions: dict[str, Any] = Field(default_factory=dict)


class NormalizedClass(BaseModel):
    name: str
    is_abstract: bool = False
    attributes: list[NormalizedProperty] = Field(default_factory=list)
    description: str = ""
    extensions: dict[str, Any] = Field(default_factory=dict)


class NormalizedEnumerationLiteral(BaseModel):
    name: str
    description: str = ""


class NormalizedEnumeration(BaseModel):
    name: str
    literals: list[NormalizedEnumerationLiteral]
    description: str = ""


class NormalizedAssociationEnd(BaseModel):
    role: str
    type: str
    multiplicity: str = "1..1"
    is_navigable: bool = True
    is_composite: bool = False


class NormalizedAssociation(BaseModel):
    name: str
    end1: NormalizedAssociationEnd
    end2: NormalizedAssociationEnd
    description: str = ""


class NormalizedConstraint(BaseModel):
    name: str
    context: str
    expression: str
    language: str = "OCL"
    description: str = ""


class NormalizedCandidateModel(BaseModel):
    """Deterministically normalized candidate — ready for compilation."""
    domain_name: str = ""
    classes: list[NormalizedClass] = Field(default_factory=list)
    enumerations: list[NormalizedEnumeration] = Field(default_factory=list)
    associations: list[NormalizedAssociation] = Field(default_factory=list)
    constraints: list[NormalizedConstraint] = Field(default_factory=list)
    unresolved_items: list[CandidateUnresolvedItem] = Field(default_factory=list)
    sidecar_items: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Review artefacts
# ---------------------------------------------------------------------------

class ReviewWarning(BaseModel):
    severity: str = "warning"  # "warning" | "error" | "info"
    category: str = ""
    message: str = ""
    related_element: str = ""


class ReviewSummary(BaseModel):
    """Human-facing review checklist produced after compilation."""
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
    """One structured-support-semantic item not on WME main chain."""
    owner_class: str
    field_name: str
    kind: str  # "configurable_field_spec" | "parameter_schema" | "retry_policy" | …
    payload: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class ReviewSidecar(BaseModel):
    """Carrier for structured semantics that cannot yet round-trip
    through the WME class-diagram JSON."""
    entries: list[SidecarEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    severity: str = "error"
    path: str = ""
    message: str = ""


class ValidationReport(BaseModel):
    is_valid: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)
