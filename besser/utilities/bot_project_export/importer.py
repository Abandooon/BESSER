"""
Import validator — validate an exported bundle before loading.

Runs ``check_compatibility`` and additional structural checks.
Returns a validation report that the UI can display before
the user confirms the import.
"""

from __future__ import annotations

import logging
from typing import Any

from besser.utilities.bot_project_export.compatibility import check_compatibility

logger = logging.getLogger(__name__)

# Required files in a valid export bundle
_REQUIRED_FILES = {
    "automation_project_manifest.json",
    "bot_instances.json",
    "export_metadata.json",
}


def validate_import(
    bundle: dict[str, Any],
    *,
    target_config: dict[str, Any] | None = None,
    target_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate an export bundle for import.

    Returns
    -------
    dict
        ``{ "is_valid", "errors", "warnings", "compatibility", "structure_checks" }``
    """
    errors: list[str] = []
    warnings: list[str] = []
    structure: list[dict[str, Any]] = []

    # 1. Check required files
    for required in _REQUIRED_FILES:
        if required not in bundle:
            errors.append(f"Missing required file: {required}")
            structure.append({
                "check": "required_file",
                "file": required,
                "status": "missing",
            })
        else:
            structure.append({
                "check": "required_file",
                "file": required,
                "status": "present",
            })

    # 2. Validate metadata
    meta = bundle.get("export_metadata.json", {})
    if not meta.get("model_version"):
        warnings.append("Export metadata does not specify model_version.")
    if not meta.get("exported_at"):
        warnings.append("Export metadata does not specify exported_at timestamp.")

    # 3. Validate redaction — no plain-text secrets
    redaction_issues = _check_no_plain_secrets(bundle)
    if redaction_issues:
        errors.extend(redaction_issues)

    # 4. Run compatibility checks
    compat_report = check_compatibility(
        bundle,
        target_config=target_config,
        target_schema=target_schema,
    )
    warnings.extend(compat_report.get("warnings", []))
    errors.extend(compat_report.get("errors", []))

    is_valid = len(errors) == 0

    report = {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "compatibility": compat_report,
        "structure_checks": structure,
    }

    if is_valid:
        logger.info("Import validation passed (%d warnings)", len(warnings))
    else:
        logger.warning("Import validation failed: %d errors", len(errors))

    return report


# ---------------------------------------------------------------------------
# Security check
# ---------------------------------------------------------------------------

import re

_SECRET_PATTERN = re.compile(
    r"(token|secret|credential|password|api_key|private_key)",
    re.IGNORECASE,
)
_REF_PATTERN = re.compile(r"^\$\{.+_ref\}$|Ref$", re.IGNORECASE)


def _check_no_plain_secrets(bundle: dict[str, Any]) -> list[str]:
    """Scan bundle values for unreplaced plain-text secrets."""
    issues: list[str] = []

    def _scan(obj: Any, path: str):
        if isinstance(obj, dict):
            for key, val in obj.items():
                child_path = f"{path}/{key}"
                if _SECRET_PATTERN.search(key) and isinstance(val, str):
                    if val and not _REF_PATTERN.match(val):
                        issues.append(
                            f"Plain-text secret detected at '{child_path}': "
                            "value must be a credentialRef / secretRef."
                        )
                else:
                    _scan(val, child_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _scan(item, f"{path}/{i}")

    # Only scan data files, not metadata
    for filename in ("automation_project_manifest.json", "bot_instances.json",
                     "infrastructure.json", "notification_targets.json"):
        if filename in bundle:
            _scan(bundle[filename], filename)

    return issues
