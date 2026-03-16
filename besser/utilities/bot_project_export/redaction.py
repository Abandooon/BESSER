"""
Redaction engine — strip sensitive values from M1 configuration
before export.

Mandatory security requirement (03 §10.2):
* All token / secret / credential / password / api_key values must be
  replaced with ``credentialRef`` or ``secretRef`` placeholders.
* The redaction report lists every field that was scrubbed.
"""

from __future__ import annotations

import copy
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = re.compile(
    r"(token|secret|credential|password|api_key|webhook_secret|private_key)",
    re.IGNORECASE,
)


def redact_config(
    config: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a redacted copy of *config* and a redaction report.

    Returns
    -------
    (redacted_config, redaction_report)
        ``redaction_report`` is a list of ``{ "path", "original_key", "action" }``.
    """
    result = copy.deepcopy(config)
    report: list[dict[str, Any]] = []

    _walk_and_redact(result, "", report)

    logger.info("Redacted %d sensitive field(s)", len(report))
    return result, report


def _walk_and_redact(
    obj: Any,
    path: str,
    report: list[dict[str, Any]],
) -> None:
    """Recursively walk a nested dict/list and scrub sensitive values."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            child_path = f"{path}/{key}" if path else key
            value = obj[key]

            # If the key name matches a sensitive pattern, check the value
            if _SENSITIVE_KEYS.search(key) and isinstance(value, str):
                # Already a ref-style value → leave alone
                if value.startswith("${") and value.endswith("}"):
                    continue
                if value.endswith("Ref"):
                    continue
                # Plain-text secret → redact
                if value:
                    obj[key] = f"${{{key}_ref}}"
                    report.append({
                        "path": child_path,
                        "original_key": key,
                        "action": "replaced_with_ref",
                    })
                continue

            # Recurse into children
            _walk_and_redact(value, child_path, report)

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _walk_and_redact(item, f"{path}/{idx}", report)
