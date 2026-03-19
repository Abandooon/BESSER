"""
Prompt templates for first-stage LLM extraction.

The system prompt embeds the **exact JSON Schema** auto-generated from
BESSER Structural metamodel introspection.  This constrains LLM output
format directly, reducing distribution skew — the LLM sees the precise
schema it must conform to, not a prose paraphrase of it.

Design (02 §2.1 + 04 §2.1):
- Schema is ``CandidateModel.model_json_schema()`` from
  ``m3_schema_projector``; NOT hand-written.
- Domain hints are opt-in; default is domain-agnostic.
"""

from __future__ import annotations

import json
from functools import lru_cache

from besser.utilities.requirements_to_buml.m3_schema_projector import (
    project_m3_to_json_schema,
)


@lru_cache(maxsize=1)
def _m3_schema_str() -> str:
    return json.dumps(project_m3_to_json_schema(), indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# System prompt — schema-first, minimal prose
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are a domain-modeling expert.  Read the user's requirements document and output a **single JSON object** conforming to the JSON Schema below.

## JSON Schema (auto-generated from BESSER Structural metamodel — this is the exact contract)

```json
{m3_schema}
```

## Rules
1. Output is a **candidate domain metamodel** (M2), NOT a configuration instance (M1).
2. Relationships MUST be associations, NOT string attributes.
3. Bounded-value concepts MUST be enumerations.
4. Uncertain items → ``unresolved_items``.
5. Complex sub-structures (field specs, retry policies) → ``extensions`` dict on owning class/attribute.
6. Each class SHOULD have one attribute with ``is_id: true``.
7. Attribute names: snake_case.  Class names: PascalCase.  Enum literals: UPPER_CASE.
8. Output ONLY the JSON object.
"""


def build_system_prompt() -> str:
    """Build system prompt with auto-projected M3 JSON Schema embedded."""
    return _SYSTEM_PROMPT_TEMPLATE.format(m3_schema=_m3_schema_str())


SYSTEM_PROMPT = build_system_prompt()


# ---------------------------------------------------------------------------
# User prompt
# ---------------------------------------------------------------------------

OSS_BOT_DOMAIN_HINT = """\
OSS community bot orchestration domain.
Key concepts: AutomationProject, Environment, PlatformConnector,
CommunityOrganization, Repository, BotTemplate (blueprint) vs
BotInstance (activation), EventTrigger, Rule, Action,
MessageTemplate, NotificationTarget, ApprovalPolicy, ScheduleTask.
Guidance: BotTemplate/BotInstance separate; BotInstance→Repository as association;
Rule/Action separate; Action params & field specs → extensions."""

OSS_BOT_CORE_CLASS_HINTS = """\
AutomationProject, Environment, PlatformConnector, CommunityOrganization,
Repository, BotTemplate, BotInstance, EventTrigger, Rule, Action,
MessageTemplate, NotificationTarget, ApprovalPolicy, ScheduleTask"""

DOMAIN_HINT_REGISTRY: dict[str, tuple[str, str]] = {
    "oss_bot": (OSS_BOT_DOMAIN_HINT, OSS_BOT_CORE_CLASS_HINTS),
}


def build_user_prompt(document_text, domain_hint=None, core_class_hints=None):
    if domain_hint in DOMAIN_HINT_REGISTRY:
        hint_text, default_classes = DOMAIN_HINT_REGISTRY[domain_hint]
        domain_hint = hint_text
        if core_class_hints is None:
            core_class_hints = default_classes

    parts = [f"## Requirements document\n\n{document_text}"]
    if domain_hint:
        parts.append(f"## Domain hint\n{domain_hint}")
    if core_class_hints:
        parts.append(f"## Candidate core classes\n{core_class_hints}")
    parts.append(
        "## Reminders\n"
        "- Output a candidate domain metamodel (M2), NOT a configuration instance.\n"
        "- Associations, not string foreign keys. Enumerations, not free strings.\n"
        "- Uncertain items → unresolved_items. Complex sub-structures → extensions.\n"
        "- Output ONLY a single JSON object."
    )
    return "\n\n".join(parts)