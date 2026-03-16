"""
Build **editor hints** — UI metadata that tells the Config Workbench
*how* to render each field.

Hints include:
* ``widget``         – suggested control type (text, select, toggle, ref-picker …)
* ``readOnly``       – field should not be editable
* ``conditional``    – visibility conditions (show field X only when field Y = Z)
* ``placeholder``    – example / guidance text
* ``referenceTo``    – for association ends, which class the picker should query

All hints derive deterministically from the confirmed ``DomainModel``
and optional ``ReviewSidecar``.
"""

from __future__ import annotations

import logging
from typing import Any

from besser.BUML.metamodel.structural import (
    DomainModel,
    Class,
    Enumeration,
    PrimitiveDataType,
    BinaryAssociation,
    UNLIMITED_MAX_MULTIPLICITY,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Widget inference
# ---------------------------------------------------------------------------

_PRIMITIVE_WIDGETS: dict[str, str] = {
    "str":       "text",
    "int":       "number",
    "float":     "number",
    "bool":      "toggle",
    "date":      "date-picker",
    "datetime":  "datetime-picker",
    "time":      "time-picker",
    "timedelta": "text",
    "any":       "text",
}


def _infer_widget(attr) -> str:
    """Infer the best widget type for an attribute."""
    if isinstance(attr.type, Enumeration):
        return "select"
    if isinstance(attr.type, Class):
        return "ref-picker"
    if isinstance(attr.type, PrimitiveDataType):
        widget = _PRIMITIVE_WIDGETS.get(attr.type.name, "text")
        # Multi-valued primitives → tag-input
        if attr.multiplicity.max > 1 or attr.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY:
            return "tag-input"
        return widget
    return "text"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_editor_hints(
    domain_model: DomainModel,
) -> dict[str, Any]:
    """Return editor-hint metadata for every class in *domain_model*.

    Returns
    -------
    dict
        ``{ "ClassName": { "fieldName": { hint_keys… } } }``
    """
    result: dict[str, dict[str, Any]] = {}

    for cls in domain_model.get_classes():
        result[cls.name] = _hints_for_class(cls, domain_model)

    logger.info("Editor hints built for %d classes", len(result))
    return result


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _hints_for_class(
    cls: Class,
    domain_model: DomainModel,
) -> dict[str, Any]:
    """Build hints for every field of *cls*."""
    hints: dict[str, Any] = {}

    for attr in sorted(cls.attributes, key=lambda a: a.name):
        h: dict[str, Any] = {
            "widget": _infer_widget(attr),
        }
        if attr.is_read_only:
            h["readOnly"] = True
        if attr.is_id:
            h["isPrimaryKey"] = True
        if attr.is_optional:
            h["optional"] = True
        if isinstance(attr.type, Enumeration):
            h["options"] = sorted(lit.name for lit in attr.type.literals)
        if attr.default_value is not None:
            h["placeholder"] = str(attr.default_value)
        # Credential / secret hint
        lower_name = attr.name.lower()
        if any(kw in lower_name for kw in ("token", "secret", "credential", "password", "api_key")):
            h["widget"] = "secret"
            h["sensitive"] = True

        hints[attr.name] = h

    # Association ends
    for assoc in cls.associations:
        if not isinstance(assoc, BinaryAssociation):
            continue
        for end in assoc.ends:
            if end.type == cls:
                continue
            h = {
                "widget": "ref-picker",
                "referenceTo": end.type.name,
            }
            if end.multiplicity.max > 1 or end.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY:
                h["widget"] = "multi-ref-picker"
                h["multi"] = True
            if end.multiplicity.min > 0:
                h["required"] = True
            if end.is_composite:
                h["composite"] = True
            hints[end.name] = h

    return hints
