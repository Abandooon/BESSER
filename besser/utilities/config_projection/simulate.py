"""
Simulation engine for bot instance dry-run.

Given a sample event and an M1 configuration, the simulator previews
which triggers fire, which rules match, what action sequence would
execute, and whether approval is required.

This is a **preview/validation** tool (03 §8.5), not a production
runtime engine.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def simulate_event(
    sample_event: dict[str, Any],
    config: dict[str, Any],
    wrapper_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Simulate a sample event against a bot configuration.

    Parameters
    ----------
    sample_event : dict
        ``{ "event_type": "ISSUE_CREATED", "payload": { ... } }``
    config : dict
        M1 configuration instance (keyed by class name, arrays of instances).
    wrapper_schema : dict | None
        Optional wrapper schema for richer validation.

    Returns
    -------
    dict
        ``{ "matched_triggers", "matched_rules", "action_sequence",
            "approval_required", "warnings", "unmatched_reason" }``
    """
    event_type = sample_event.get("event_type", "").upper()
    payload = sample_event.get("payload", {})

    matched_triggers: list[dict[str, Any]] = []
    matched_rules: list[dict[str, Any]] = []
    action_sequence: list[dict[str, Any]] = []
    warnings: list[str] = []
    approval_needed = False

    # --- 1. Find matching triggers ------------------------------------
    triggers = config.get("EventTrigger", [])
    for trig in triggers:
        if not trig.get("is_enabled", True):
            continue
        trig_type = trig.get("event_type", "").upper()
        if trig_type == event_type:
            # Check filter expression (simple substring match for MVP)
            filter_expr = trig.get("filter_expression", "")
            if filter_expr and not _evaluate_filter(filter_expr, payload):
                continue
            matched_triggers.append({
                "trigger_id": trig.get("trigger_id", ""),
                "name": trig.get("name", ""),
                "event_type": trig_type,
            })

    if not matched_triggers:
        return {
            "matched_triggers": [],
            "matched_rules": [],
            "action_sequence": [],
            "approval_required": False,
            "warnings": [],
            "unmatched_reason": f"No enabled trigger matches event type '{event_type}'.",
        }

    # --- 2. Find matching rules ---------------------------------------
    matched_trigger_ids = {t["trigger_id"] for t in matched_triggers}
    rules = config.get("Rule", [])
    for rule in sorted(rules, key=lambda r: r.get("priority", 0)):
        if not rule.get("is_enabled", True):
            continue
        # In a full implementation, Rule→EventTrigger would be resolved
        # via association. For MVP, match by convention (trigger_id field
        # or co-located rule-trigger pairs).
        rule_trigger = rule.get("trigger_id", rule.get("trigger", ""))
        if rule_trigger in matched_trigger_ids or not rule_trigger:
            # Evaluate condition expression (MVP: always true if empty)
            cond = rule.get("condition_expression", "")
            if cond and not _evaluate_condition(cond, payload):
                continue
            matched_rules.append({
                "rule_id": rule.get("rule_id", ""),
                "name": rule.get("name", ""),
                "priority": rule.get("priority", 0),
            })

    if not matched_rules:
        return {
            "matched_triggers": matched_triggers,
            "matched_rules": [],
            "action_sequence": [],
            "approval_required": False,
            "warnings": ["Triggers matched but no rules fired."],
            "unmatched_reason": "No enabled rule matched the trigger + conditions.",
        }

    # --- 3. Collect action sequence -----------------------------------
    actions = config.get("Action", [])
    matched_rule_ids = {r["rule_id"] for r in matched_rules}

    for action in sorted(actions, key=lambda a: a.get("execution_order", 0)):
        # Association: action belongs to a rule. MVP: match by rule_id field.
        action_rule = action.get("rule_id", action.get("rule", ""))
        if action_rule in matched_rule_ids or not action_rule:
            entry: dict[str, Any] = {
                "action_id": action.get("action_id", ""),
                "name": action.get("name", ""),
                "action_type": action.get("action_type", ""),
                "execution_order": action.get("execution_order", 0),
            }
            if action.get("requires_approval"):
                entry["requires_approval"] = True
                approval_needed = True
                warnings.append(
                    f"Action '{action.get('name', '')}' (type={action.get('action_type', '')}) "
                    "requires approval before execution."
                )
            action_sequence.append(entry)

    # --- 4. Additional warnings ---------------------------------------
    if not action_sequence:
        warnings.append("Rules matched but no actions are associated.")

    return {
        "matched_triggers": matched_triggers,
        "matched_rules": matched_rules,
        "action_sequence": action_sequence,
        "approval_required": approval_needed,
        "warnings": warnings,
        "unmatched_reason": None,
    }


# ---------------------------------------------------------------------------
# MVP filter / condition evaluators (placeholder)
# ---------------------------------------------------------------------------

def _evaluate_filter(expression: str, payload: dict[str, Any]) -> bool:
    """MVP filter evaluation — simple key-existence or substring check."""
    expr = expression.strip().lower()
    if not expr:
        return True
    # "label:bug" → check payload has a label containing "bug"
    if ":" in expr:
        key, val = expr.split(":", 1)
        data_val = str(payload.get(key.strip(), "")).lower()
        return val.strip() in data_val
    # Bare keyword → check any payload value contains it
    for v in payload.values():
        if expr in str(v).lower():
            return True
    return False


def _evaluate_condition(expression: str, payload: dict[str, Any]) -> bool:
    """MVP condition evaluation — always returns True for non-empty exprs.

    A production implementation would parse OCL or a simple DSL.
    """
    return True
