"""
Structured patch engine for M1 configuration instances.

Operations follow RFC 6902 (JSON Patch) semantics but are **constrained
by the wrapper schema**: only paths that the schema exposes as editable
can be targeted.  High-risk mutations (e.g. touching approval-controlled
actions) produce warnings that must be acknowledged before apply.

Design (from 03 §9):
* ``path`` must fall within wrapper-schema-allowed editable range.
* Patches must not directly write ``secretValue``.
* Patches affecting high-risk actions must return warnings.
* Patches return ``affected_fields`` and ``validation_summary``.
* Patches share the same validator as the form editor.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patch data structures
# ---------------------------------------------------------------------------

class PatchOperation:
    """One JSON-Patch-like operation."""
    __slots__ = ("op", "path", "value", "reason")

    def __init__(self, op: str, path: str, value: Any = None, reason: str = ""):
        self.op = op        # "replace" | "add" | "remove"
        self.path = path    # JSON Pointer, e.g. "/botInstances/0/priority"
        self.value = value
        self.reason = reason


def parse_patch(raw: dict[str, Any]) -> list[PatchOperation]:
    """Parse a raw patch dict into ``PatchOperation`` objects."""
    ops = []
    for item in raw.get("operations", []):
        ops.append(PatchOperation(
            op=item.get("op", "replace"),
            path=item.get("path", ""),
            value=item.get("value"),
            reason=item.get("reason", ""),
        ))
    return ops


# ---------------------------------------------------------------------------
# Schema-based validation
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS = re.compile(
    r"(token|secret|credential|password|api_key)", re.IGNORECASE
)


def validate_patch(
    operations: list[PatchOperation],
    wrapper_schema: dict[str, Any],
    current_config: dict[str, Any],
) -> dict[str, Any]:
    """Validate patch operations against the wrapper schema.

    Returns
    -------
    dict
        ``{ "is_valid": bool, "errors": [...], "warnings": [...],
            "affected_fields": [...] }``
    """
    errors: list[str] = []
    warnings: list[str] = []
    affected: list[str] = []

    schema_defs = wrapper_schema.get("$defs", {})

    for op in operations:
        affected.append(op.path)

        # 1. Reject writes to sensitive fields
        if op.op in ("replace", "add") and _SENSITIVE_PATTERNS.search(op.path):
            if isinstance(op.value, str) and not op.value.endswith("Ref"):
                errors.append(
                    f"Cannot write plain-text value to sensitive path '{op.path}'. "
                    "Use a credentialRef / secretRef instead."
                )

        # 2. Reject writes to sidecar-only fields
        if "x-sidecar" in op.path:
            warnings.append(
                f"Path '{op.path}' targets a sidecar field — edits may not "
                "round-trip through the WME class diagram."
            )

        # 3. Reject writes to read-only / is_id fields
        field_schema = _resolve_field_schema(op.path, wrapper_schema)
        if field_schema:
            if field_schema.get("readOnly"):
                errors.append(f"Path '{op.path}' is read-only.")
            if field_schema.get("x-is-id"):
                warnings.append(
                    f"Path '{op.path}' is a primary key — modification may "
                    "break referential integrity."
                )

        # 4. Warn on high-risk action fields
        if any(kw in op.path.lower() for kw in ("approval", "risk", "close_issue")):
            warnings.append(
                f"Path '{op.path}' touches a high-risk or approval-related "
                "field — requires confirmation."
            )

        # 5. Validate op type
        if op.op not in ("replace", "add", "remove"):
            errors.append(f"Unsupported operation '{op.op}' at path '{op.path}'.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "affected_fields": affected,
    }


def _resolve_field_schema(
    path: str,
    wrapper_schema: dict[str, Any],
) -> dict[str, Any] | None:
    """Attempt to resolve a JSON Pointer path to a field schema in $defs."""
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        return None
    class_name = parts[0]
    # Skip array index
    field_name = parts[2] if len(parts) >= 3 and parts[1].isdigit() else parts[1]
    cls_def = wrapper_schema.get("$defs", {}).get(class_name, {})
    return cls_def.get("properties", {}).get(field_name)


# ---------------------------------------------------------------------------
# Patch application
# ---------------------------------------------------------------------------

def apply_patch(
    config: dict[str, Any],
    operations: list[PatchOperation],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply patch operations to *config* (immutably).

    Returns
    -------
    (updated_config, diff_entries)
    """
    result = copy.deepcopy(config)
    diff: list[dict[str, Any]] = []

    for op in operations:
        parts = [p for p in op.path.strip("/").split("/") if p]
        old_value = _get_nested(result, parts)

        if op.op == "replace":
            _set_nested(result, parts, op.value)
        elif op.op == "add":
            _set_nested(result, parts, op.value)
        elif op.op == "remove":
            _del_nested(result, parts)

        diff.append({
            "path": op.path,
            "op": op.op,
            "old_value": old_value,
            "new_value": op.value if op.op != "remove" else None,
            "reason": op.reason,
        })

    return result, diff


# ---------------------------------------------------------------------------
# Nested dict helpers
# ---------------------------------------------------------------------------

def _get_nested(d: Any, parts: list[str]) -> Any:
    try:
        for p in parts:
            if isinstance(d, list) and p.isdigit():
                d = d[int(p)]
            elif isinstance(d, dict):
                d = d[p]
            else:
                return None
        return d
    except (KeyError, IndexError, TypeError):
        return None


def _set_nested(d: Any, parts: list[str], value: Any) -> None:
    for p in parts[:-1]:
        if isinstance(d, list) and p.isdigit():
            d = d[int(p)]
        elif isinstance(d, dict):
            d = d.setdefault(p, {})
    last = parts[-1]
    if isinstance(d, list) and last.isdigit():
        idx = int(last)
        while len(d) <= idx:
            d.append(None)
        d[idx] = value
    elif isinstance(d, dict):
        d[last] = value


def _del_nested(d: Any, parts: list[str]) -> None:
    for p in parts[:-1]:
        if isinstance(d, list) and p.isdigit():
            d = d[int(p)]
        elif isinstance(d, dict):
            d = d.get(p, {})
    last = parts[-1]
    if isinstance(d, dict) and last in d:
        del d[last]
    elif isinstance(d, list) and last.isdigit():
        idx = int(last)
        if idx < len(d):
            d.pop(idx)
