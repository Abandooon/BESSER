"""
Project exporter — assemble a portable config bundle from M1 instances.

Output bundle (03 §10.1):
* ``automation_project_manifest.json``
* ``bot_instances.json``
* ``message_templates.json``
* ``notification_targets.json``
* ``compatibility_report.json``
* ``export_metadata.json``
* ``sidecar_notes.json`` (if sidecar present)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from besser.utilities.bot_project_export.redaction import redact_config

logger = logging.getLogger(__name__)


def export_project(
    config: dict[str, Any],
    *,
    project_name: str = "",
    model_version: str = "1.0.0",
    sidecar: dict[str, Any] | None = None,
    wrapper_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export an M1 project configuration as a portable bundle.

    Parameters
    ----------
    config : dict
        The full M1 configuration instance (class-name → list-of-instances).
    project_name : str
        Human-readable project name.
    model_version : str
        Semantic version of the domain model that produced this config.
    sidecar : dict | None
        ``ReviewSidecar`` data to include as ``sidecar_notes.json``.
    wrapper_schema : dict | None
        If provided, embedded in metadata for downstream validation.

    Returns
    -------
    dict
        A bundle dict with all output files as keys.
    """
    # 1. Redact sensitive fields
    redacted, redaction_report = redact_config(config)

    # 2. Split config into logical files
    bundle: dict[str, Any] = {}

    # Main manifest — project-level fields
    project_instances = redacted.get("AutomationProject", [])
    bundle["automation_project_manifest.json"] = {
        "projects": project_instances,
    }

    # Bot instances + rules + actions
    bundle["bot_instances.json"] = {
        "bot_templates": redacted.get("BotTemplate", []),
        "bot_instances": redacted.get("BotInstance", []),
        "rules": redacted.get("Rule", []),
        "actions": redacted.get("Action", []),
        "event_triggers": redacted.get("EventTrigger", []),
        "schedule_tasks": redacted.get("ScheduleTask", []),
    }

    # Messaging
    bundle["message_templates.json"] = {
        "message_templates": redacted.get("MessageTemplate", []),
    }

    # Notifications + approval
    bundle["notification_targets.json"] = {
        "notification_targets": redacted.get("NotificationTarget", []),
        "approval_policies": redacted.get("ApprovalPolicy", []),
    }

    # Infrastructure (environments, connectors, orgs, repos)
    bundle["infrastructure.json"] = {
        "environments": redacted.get("Environment", []),
        "platform_connectors": redacted.get("PlatformConnector", []),
        "community_organizations": redacted.get("CommunityOrganization", []),
        "repositories": redacted.get("Repository", []),
    }

    # 3. High-risk confirmation items
    high_risk_items = _collect_high_risk_items(redacted)

    # 4. Compatibility report
    bundle["compatibility_report.json"] = {
        "platform_types": _collect_enum_values(redacted, "platform_type"),
        "connector_types": _collect_enum_values(redacted, "connector_type"),
        "high_risk_items": high_risk_items,
        "redaction_summary": {
            "redacted_field_count": len(redaction_report),
            "fields": redaction_report,
        },
    }

    # 5. Export metadata
    bundle["export_metadata.json"] = {
        "project_name": project_name or _infer_project_name(config),
        "model_version": model_version,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exporter": "besser.utilities.bot_project_export",
        "class_counts": {
            k: len(v) for k, v in config.items() if isinstance(v, list)
        },
    }

    # 6. Sidecar notes
    if sidecar:
        bundle["sidecar_notes.json"] = sidecar

    logger.info(
        "Export bundle assembled: %d files, %d redacted fields, %d high-risk items",
        len(bundle), len(redaction_report), len(high_risk_items),
    )
    return bundle


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_high_risk_items(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Identify actions or rules that require confirmation on import."""
    items = []
    for action in config.get("Action", []):
        if action.get("requires_approval") or action.get("action_type", "").upper() in (
            "CLOSE_ISSUE", "CALL_WEBHOOK", "CREATE_TASK",
        ):
            items.append({
                "type": "Action",
                "name": action.get("name", ""),
                "action_type": action.get("action_type", ""),
                "reason": "High-risk action type — requires confirmation on import.",
            })
    return items


def _collect_enum_values(
    config: dict[str, Any],
    field_name: str,
) -> list[str]:
    """Collect all distinct values of *field_name* across config."""
    values = set()
    for instances in config.values():
        if not isinstance(instances, list):
            continue
        for inst in instances:
            if isinstance(inst, dict) and field_name in inst:
                values.add(str(inst[field_name]))
    return sorted(values)


def _infer_project_name(config: dict[str, Any]) -> str:
    projects = config.get("AutomationProject", [])
    if projects and isinstance(projects[0], dict):
        return projects[0].get("name", "Unnamed Project")
    return "Unnamed Project"
