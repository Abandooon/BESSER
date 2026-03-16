"""
Prompt templates for the first-stage LLM extraction.

The prompts encode the **M3 projection contract**: the LLM must produce
a JSON object conforming to ``CandidateModel`` — which is itself a
serialisation of the BESSER Structural metamodel concepts.

Design rules (from 02_需求到候选B-UML规范):
- Output is a **candidate domain metamodel** (M2), NOT a config instance (M1).
- Relationships must be expressed as associations, not string attributes.
- Enumerable concepts must be enumerations, not free strings.
- Uncertain items go to ``unresolved_items``.
- Structured-support semantics (field specs, retry policies, etc.) go to
  ``extensions`` and are later routed to the sidecar.
"""

from __future__ import annotations

from besser.utilities.requirements_to_buml.schemas import CandidateModel


def _schema_json() -> str:
    """Return the CandidateModel JSON Schema as a compact string."""
    return CandidateModel.model_json_schema(mode="serialization").__repr__()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a domain-modeling expert that produces **candidate B-UML domain metamodels** from natural-language requirements documents.

## Your task
Read the user-supplied requirements document and output a **single JSON object** that conforms to the schema described below.

## Output schema (M3 projection)
The JSON must contain the following top-level keys:
- `domain_name`     (str) – a short PascalCase identifier for the domain.
- `classes`         (list) – candidate domain classes.
- `enumerations`    (list) – candidate enumerations.
- `associations`    (list) – candidate binary associations between classes.
- `constraints`     (list) – candidate OCL or textual constraints.
- `unresolved_items`(list) – items you could not confidently classify.
- `metadata`        (dict) – any extra information.

### Class structure
```json
{
  "name": "PascalCaseName",
  "is_abstract": false,
  "attributes": [
    {
      "name": "lowerCamelCaseOrSnakeCase",
      "type": "str | int | float | bool | date | datetime | time | timedelta | any | EnumName | ClassName",
      "visibility": "public",
      "is_id": false,
      "is_read_only": false,
      "is_optional": false,
      "default_value": null,
      "multiplicity": "1..1",
      "description": "",
      "extensions": {}
    }
  ],
  "description": "",
  "extensions": {}
}
```

### Association structure
```json
{
  "name": "SourceClass_TargetClass",
  "end1": { "role": "source", "type": "SourceClass", "multiplicity": "1..1", "is_navigable": true, "is_composite": false },
  "end2": { "role": "targets", "type": "TargetClass", "multiplicity": "0..*", "is_navigable": true, "is_composite": false },
  "description": ""
}
```

### Enumeration structure
```json
{
  "name": "PascalCaseName",
  "literals": [ { "name": "UPPER_CASE_NAME", "description": "" } ],
  "description": ""
}
```

### Constraint structure
```json
{
  "name": "constraint_name",
  "context": "ClassName",
  "expression": "OCL or natural-language expression",
  "language": "OCL",
  "description": ""
}
```

## Strict rules
1. You are producing a **candidate domain metamodel** (M2), NOT a configuration instance (M1). Do NOT output concrete config values like specific bot names, specific repo URLs, or runtime settings.
2. Relationships between classes MUST be expressed as **associations**, not as string-typed attributes. For example, "所属模板" MUST become an association from BotInstance to BotTemplate, NOT a `templateName: str` attribute.
3. Concepts that have a fixed set of values (e.g. platform types, risk levels, action types) MUST be expressed as **enumerations**.
4. If a concept cannot be confidently classified, put it in `unresolved_items` with a `reason` and optional `suggestion`.
5. Structured-support semantics that are complex sub-structures (e.g. configurable field specifications, parameter schemas, retry policies, rollback hints) should be placed in the `extensions` dict of the owning class or attribute. They will be routed to the review sidecar. Do NOT force them into new top-level classes unless they are genuinely independent domain entities.
6. Each class SHOULD have exactly one attribute with `is_id: true`.
7. Attribute names MUST be lowerCamelCase or snake_case — pick one convention and be consistent.
8. Class names MUST be PascalCase.
9. Enumeration literal names MUST be UPPER_CASE.
10. Output ONLY the JSON object — no markdown fences, no commentary.
"""


# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = """\
## Requirements document

{document_text}

## Domain hint
{domain_hint}

## Candidate core classes (suggested — you may add or adjust)
{core_class_hints}

## Reminders
- Output a **candidate domain metamodel** (M2), NOT a configuration instance.
- Prefer associations over string-typed foreign-key attributes.
- Prefer enumerations over free-form string fields where values are bounded.
- Any uncertain items → `unresolved_items`.
- Complex sub-structures (field specs, retry policies, etc.) → `extensions`.
- Output ONLY a single JSON object — no wrapping, no commentary.
"""


# ---------------------------------------------------------------------------
# Domain hints
# ---------------------------------------------------------------------------

DEFAULT_DOMAIN_HINT = "General software engineering domain."

OSS_BOT_DOMAIN_HINT = """\
This is an OSS (Open Source Software) community bot orchestration domain.
Key domain concepts include:
- AutomationProject, Environment, PlatformConnector
- CommunityOrganization, Repository
- BotTemplate (defines reusable bot blueprints) vs BotInstance (a concrete activation)
- EventTrigger, Rule, Action
- MessageTemplate, NotificationTarget, ApprovalPolicy, ScheduleTask

Important modeling guidance:
- BotTemplate and BotInstance MUST be separate classes with a template→instance association.
- BotInstance MUST have an association to Repository (not a string attribute).
- Rule and Action MUST be separate classes.
- ApprovalPolicy, NotificationTarget, MessageTemplate should be first-class domain classes reusable across rules/actions.
- Action parameters and BotTemplate configurable-field-specs are structured-support semantics — put them in `extensions`, not as new top-level classes.
- High-risk actions should be linked to ApprovalPolicy via an association or constraint.
"""

OSS_BOT_CORE_CLASS_HINTS = """\
AutomationProject, Environment, PlatformConnector, CommunityOrganization,
Repository, BotTemplate, BotInstance, EventTrigger, Rule, Action,
MessageTemplate, NotificationTarget, ApprovalPolicy, ScheduleTask
"""


def build_user_prompt(
    document_text: str,
    domain_hint: str | None = None,
    core_class_hints: str | None = None,
) -> str:
    """Assemble the user prompt from document + hints."""
    return USER_PROMPT_TEMPLATE.format(
        document_text=document_text,
        domain_hint=domain_hint or DEFAULT_DOMAIN_HINT,
        core_class_hints=core_class_hints or "(none provided — infer from document)",
    )
