"""
Pre-import compatibility checker.

Before importing an exported bundle into a target environment, this module
verifies (03 §10.3):
* Platform types are compatible
* Connector types exist
* Target environments can be mapped
* Referenced templates / targets / policies are present
* High-risk actions are flagged for re-confirmation
* Sidecar fields are still supported in the target version
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def check_compatibility(
    bundle: dict[str, Any],
    target_config: dict[str, Any] | None = None,
    target_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run compatibility checks on an export bundle.

    Parameters
    ----------
    bundle : dict
        The export bundle produced by ``export_project()``.
    target_config : dict | None
        Existing M1 config in the target environment (for ref checks).
    target_schema : dict | None
        Wrapper schema of the target environment (for field checks).

    Returns
    -------
    dict
        ``{ "is_compatible", "errors", "warnings", "missing_refs",
            "environment_remap_suggestions", "high_risk_confirmations" }``
    """
    errors: list[str] = []
    warnings: list[str] = []
    missing_refs: list[dict[str, Any]] = []
    env_suggestions: list[dict[str, Any]] = []
    high_risk: list[dict[str, Any]] = []

    compat = bundle.get("compatibility_report.json", {})
    metadata = bundle.get("export_metadata.json", {})
    infra = bundle.get("infrastructure.json", {})
    bot_data = bundle.get("bot_instances.json", {})
    notif_data = bundle.get("notification_targets.json", {})

    # 1. Platform type compatibility
    source_platforms = set(compat.get("platform_types", []))
    if target_config:
        target_platforms = _collect_values(target_config, "platform_type")
        unsupported = source_platforms - target_platforms
        if unsupported:
            warnings.append(
                f"Platform types {unsupported} are in the bundle but not in "
                "the target environment."
            )

    # 2. Connector type compatibility
    source_connectors = set(compat.get("connector_types", []))
    if target_config:
        target_connectors = _collect_values(target_config, "connector_type")
        missing_ct = source_connectors - target_connectors
        if missing_ct:
            warnings.append(
                f"Connector types {missing_ct} are in the bundle but not "
                "configured in the target."
            )

    # 3. Environment mapping suggestions
    source_envs = infra.get("environments", [])
    if target_config:
        target_envs = target_config.get("Environment", [])
        target_env_names = {e.get("name", "") for e in target_envs if isinstance(e, dict)}
        for env in source_envs:
            env_name = env.get("name", "")
            if env_name and env_name not in target_env_names:
                env_suggestions.append({
                    "source_environment": env_name,
                    "suggestion": "Create new or remap to existing environment.",
                })

    # 4. Missing reference checks
    # Check that templates referenced by instances exist
    template_ids = {t.get("template_id") for t in bot_data.get("bot_templates", [])}
    for inst in bot_data.get("bot_instances", []):
        ref = inst.get("template_id") or inst.get("template")
        if ref and ref not in template_ids:
            missing_refs.append({
                "type": "BotTemplate",
                "referenced_by": f"BotInstance '{inst.get('name', '')}'",
                "missing_id": ref,
            })

    # Check notification targets and approval policies
    target_ids = {t.get("target_id") for t in notif_data.get("notification_targets", [])}
    policy_ids = {p.get("policy_id") for p in notif_data.get("approval_policies", [])}

    for action in bot_data.get("actions", []):
        nt_ref = action.get("notification_target")
        if nt_ref and nt_ref not in target_ids:
            missing_refs.append({
                "type": "NotificationTarget",
                "referenced_by": f"Action '{action.get('name', '')}'",
                "missing_id": nt_ref,
            })
        ap_ref = action.get("approval_policy")
        if ap_ref and ap_ref not in policy_ids:
            missing_refs.append({
                "type": "ApprovalPolicy",
                "referenced_by": f"Action '{action.get('name', '')}'",
                "missing_id": ap_ref,
            })

    # 5. High-risk confirmations
    for item in compat.get("high_risk_items", []):
        high_risk.append({
            "type": item.get("type", ""),
            "name": item.get("name", ""),
            "reason": item.get("reason", ""),
            "confirmed": False,
        })

    # 6. Schema field compatibility
    if target_schema:
        target_defs = set(target_schema.get("$defs", {}).keys())
        source_classes = set(metadata.get("class_counts", {}).keys())
        unknown = source_classes - target_defs
        if unknown:
            warnings.append(
                f"Classes {unknown} are in the bundle but not defined in "
                "the target schema."
            )

    # 7. Sidecar compatibility
    sidecar = bundle.get("sidecar_notes.json")
    if sidecar and target_schema:
        sidecar_entries = sidecar.get("entries", [])
        for entry in sidecar_entries:
            owner = entry.get("owner_class", "").split(".")[0]
            if owner and owner not in target_schema.get("$defs", {}):
                warnings.append(
                    f"Sidecar entry for '{owner}.{entry.get('field_name', '')}' "
                    "references a class not in the target schema."
                )

    is_compatible = len(errors) == 0
    if missing_refs:
        warnings.append(f"{len(missing_refs)} missing reference(s) detected.")

    report = {
        "is_compatible": is_compatible,
        "errors": errors,
        "warnings": warnings,
        "missing_refs": missing_refs,
        "environment_remap_suggestions": env_suggestions,
        "high_risk_confirmations": high_risk,
        "source_model_version": metadata.get("model_version", "unknown"),
    }

    logger.info(
        "Compatibility check: compatible=%s, %d warnings, %d missing refs",
        is_compatible, len(warnings), len(missing_refs),
    )
    return report


def _collect_values(config: dict[str, Any], field: str) -> set[str]:
    values = set()
    for instances in config.values():
        if not isinstance(instances, list):
            continue
        for inst in instances:
            if isinstance(inst, dict) and field in inst:
                values.add(str(inst[field]))
    return values
