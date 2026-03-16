"""
Build **field groups** for the Config Workbench form layout.

A field group is a logical section of a form (e.g. "Identity", "Behaviour",
"Associations") derived from the confirmed ``DomainModel``.  The frontend
renders each group as a collapsible card / tab.

Groups are computed deterministically — no LLM call.
"""

from __future__ import annotations

import logging
from typing import Any

from besser.BUML.metamodel.structural import (
    DomainModel,
    Class,
    BinaryAssociation,
    UNLIMITED_MAX_MULTIPLICITY,
)

logger = logging.getLogger(__name__)


def build_field_groups(
    domain_model: DomainModel,
) -> dict[str, Any]:
    """Return field-group metadata for every class in *domain_model*.

    Returns
    -------
    dict
        ``{ "ClassName": [ { "group": str, "fields": [str] } ] }``
    """
    result: dict[str, list[dict[str, Any]]] = {}

    for cls in domain_model.get_classes():
        result[cls.name] = _groups_for_class(cls, domain_model)

    logger.info("Field groups built for %d classes", len(result))
    return result


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _groups_for_class(
    cls: Class,
    domain_model: DomainModel,
) -> list[dict[str, Any]]:
    """Compute field groups for a single class."""
    groups: list[dict[str, Any]] = []

    attrs = sorted(cls.attributes, key=lambda a: a.name)

    # ---- Group 1: Identity (id + read-only fields) -------------------
    identity_fields = [a.name for a in attrs if a.is_id or a.is_read_only]
    if identity_fields:
        groups.append({
            "group": "Identity",
            "fields": identity_fields,
            "collapsed": False,
        })

    # ---- Group 2: Core (remaining required, non-association fields) ---
    core_fields = [
        a.name for a in attrs
        if not a.is_id and not a.is_read_only and not a.is_optional
    ]
    if core_fields:
        groups.append({
            "group": "Core",
            "fields": core_fields,
            "collapsed": False,
        })

    # ---- Group 3: Optional fields ------------------------------------
    optional_fields = [
        a.name for a in attrs
        if a.is_optional and not a.is_id and not a.is_read_only
    ]
    if optional_fields:
        groups.append({
            "group": "Optional",
            "fields": optional_fields,
            "collapsed": True,
        })

    # ---- Group 4: Associations (outgoing ends) -----------------------
    assoc_fields: list[str] = []
    for assoc in cls.associations:
        if not isinstance(assoc, BinaryAssociation):
            continue
        for end in assoc.ends:
            if end.type != cls:
                assoc_fields.append(end.name)
    if assoc_fields:
        groups.append({
            "group": "Associations",
            "fields": sorted(set(assoc_fields)),
            "collapsed": True,
        })

    return groups
