"""
Merge ``ReviewSidecar`` entries into the wrapper schema and editor hints.

Sidecar entries carry structured-support semantics (configurable field
specs, parameter schemas, retry policies, etc.) that cannot yet
round-trip through the WME class-diagram JSON.  This module injects
them into the M2 projections so the Config Workbench and chat-patch
layer can consume them.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from besser.utilities.requirements_to_buml.schemas import ReviewSidecar

logger = logging.getLogger(__name__)


def merge_sidecar_into_schema(
    wrapper_schema: dict[str, Any],
    sidecar: ReviewSidecar,
) -> dict[str, Any]:
    """Return a *new* wrapper schema with sidecar entries injected.

    Injection rules
    ---------------
    * For each sidecar entry whose ``owner_class`` matches a ``$defs``
      key, a property named ``x-sidecar-<field_name>`` is added to that
      class definition, carrying the payload as a sub-schema.
    * The original schema is not mutated.
    """
    if not sidecar.entries:
        return wrapper_schema

    schema = copy.deepcopy(wrapper_schema)
    defs = schema.get("$defs", {})

    injected = 0
    for entry in sidecar.entries:
        owner = entry.owner_class
        # Handle dotted owners like "BotTemplate.defaultEvents"
        top_class = owner.split(".")[0] if "." in owner else owner

        if top_class not in defs:
            logger.debug("Sidecar owner '%s' not in $defs — skipped", top_class)
            continue

        cls_def = defs[top_class]
        props = cls_def.setdefault("properties", {})

        key = f"x-sidecar-{entry.field_name}"
        props[key] = {
            "title": entry.field_name,
            "description": entry.description or f"Sidecar: {entry.kind}",
            "x-sidecar-kind": entry.kind,
            "x-sidecar-payload": entry.payload,
            "x-sidecar": True,
        }
        injected += 1

    logger.info("Merged %d sidecar entries into wrapper schema", injected)
    return schema


def merge_sidecar_into_hints(
    editor_hints: dict[str, Any],
    sidecar: ReviewSidecar,
) -> dict[str, Any]:
    """Return *new* editor hints with sidecar-driven hint enrichments.

    For each sidecar entry:
    * If ``kind`` contains "field_spec", add a ``fieldSpec`` hint on the
      owning class so the form can render dynamic sub-fields.
    * If ``kind`` contains "retry" or "rollback", add an info badge hint.
    """
    if not sidecar.entries:
        return editor_hints

    hints = copy.deepcopy(editor_hints)

    for entry in sidecar.entries:
        top_class = entry.owner_class.split(".")[0]
        if top_class not in hints:
            hints[top_class] = {}

        cls_hints = hints[top_class]
        key = entry.field_name

        if "field_spec" in entry.kind:
            cls_hints[key] = {
                "widget": "dynamic-fields",
                "fieldSpec": entry.payload,
                "sidecar": True,
                "description": entry.description,
            }
        elif "retry" in entry.kind or "rollback" in entry.kind:
            cls_hints[key] = {
                "widget": "info-badge",
                "payload": entry.payload,
                "sidecar": True,
                "description": entry.description,
            }
        else:
            cls_hints[key] = {
                "widget": "json-viewer",
                "payload": entry.payload,
                "sidecar": True,
                "description": entry.description,
            }

    return hints
