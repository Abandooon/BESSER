"""
Instance extraction — use wrapper schema (M2) to constrain LLM generation of M1 instances.

This is the Stage 2→3 bridge: given a confirmed DomainModel and its wrapper schema,
build a prompt that constrains LLM output to valid M1 configuration instance JSON.

Architecture (symmetric to Stage 1):
    Stage 1: M3 schema (from structural.py) → constrains LLM → CandidateModel (M2)
    Stage 2: M2 schema (from wrapper_schema)  → constrains LLM → M1 instance JSON

Chain::

    DomainModel
      → build_wrapper_schema()          (M2 → JSON Schema)
      → _build_instance_schema()        (flatten associations to ID refs)
      → _build_instance_prompts()       (embed schema in prompt)
      → LLM call                        (constrained output)
      → M1 instance JSON                (validated against wrapper schema)
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema flattening — convert $ref associations to ID string references
# ---------------------------------------------------------------------------

def _build_instance_schema(wrapper_schema: dict[str, Any]) -> dict[str, Any]:
    """Transform wrapper schema into an instance-filling schema.

    Changes:
    1. Association fields that are ``$ref`` to another class → ``string``
       (the ID value of the referenced instance).
    2. Association fields that are ``array of $ref`` → ``array of string``.
    3. Remove circular ``$ref`` nesting so LLM sees a flat structure.
    4. Keep enums as ``$ref`` (LLM needs to see allowed values).

    The original wrapper_schema is NOT mutated.
    """
    schema = copy.deepcopy(wrapper_schema)
    defs = schema.get("$defs", {})

    # Collect class names vs enum names
    class_names = set()
    enum_names = set()
    for def_name, def_body in defs.items():
        if def_body.get("type") == "object":
            class_names.add(def_name)
        elif "enum" in def_body:
            enum_names.add(def_name)

    # For each class definition, flatten association fields
    for class_name in class_names:
        class_def = defs.get(class_name, {})
        props = class_def.get("properties", {})
        required = class_def.get("required", [])

        for field_name, field_schema in list(props.items()):
            ref = field_schema.get("$ref", "")
            ref_target = ref.split("/")[-1] if ref else ""

            # Case 1: direct $ref to another class → string ID
            if ref_target in class_names:
                id_field = _find_id_field(defs.get(ref_target, {}))
                desc = f"ID reference to {ref_target}"
                if id_field:
                    desc += f" (the {id_field} value)"
                props[field_name] = {
                    "type": "string",
                    "title": field_schema.get("title", field_name),
                    "description": desc,
                    "x-reference-to": ref_target,
                }
                # Preserve x-association
                if "x-association" in field_schema:
                    props[field_name]["x-association"] = field_schema["x-association"]
                continue

            # Case 2: array of $ref to another class → array of string IDs
            if field_schema.get("type") == "array":
                items = field_schema.get("items", {})
                items_ref = items.get("$ref", "")
                items_target = items_ref.split("/")[-1] if items_ref else ""

                if items_target in class_names:
                    id_field = _find_id_field(defs.get(items_target, {}))
                    desc = f"Array of ID references to {items_target}"
                    if id_field:
                        desc += f" (each is a {id_field} value)"
                    props[field_name] = {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": field_schema.get("title", field_name),
                        "description": desc,
                        "x-reference-to": items_target,
                    }
                    if "x-association" in field_schema:
                        props[field_name]["x-association"] = field_schema["x-association"]
                    continue

            # Case 2b: array of integer/number with x-association marker
            #   PydanticGenerator renders N:M ends as List[int], not $ref.
            #   Detect via x-association marker and force to string IDs.
            if (field_schema.get("type") == "array"
                    and field_schema.get("x-association")
                    and field_schema.get("items", {}).get("type") in ("integer", "number")):
                id_field = _find_id_field(defs.get(
                    field_schema.get("x-reference-to", ""), {}))
                desc = f"Array of ID references (N:M association '{field_schema['x-association']}')"
                if id_field:
                    desc += f" — each is a {id_field} value"
                props[field_name] = {
                    "type": "array",
                    "items": {"type": "string"},
                    "title": field_schema.get("title", field_name),
                    "description": desc,
                    "x-association": field_schema["x-association"],
                }
                continue

            # Case 2c: array of integer without x-association but field name
            #   suggests a relationship (heuristic fallback for missed ends)
            if (field_schema.get("type") == "array"
                    and field_schema.get("items", {}).get("type") in ("integer", "number")
                    and any(field_name.endswith(s) for s in ("s", "_ids", "_list"))):
                props[field_name] = {
                    "type": "array",
                    "items": {"type": "string"},
                    "title": field_schema.get("title", field_name),
                    "description": f"Array of ID references for {field_name}",
                }
                continue

            # Case 3: enum $ref → keep as-is (LLM needs to see enum values)
            # Case 4: primitive field → keep as-is

    # Remove class defs from $defs (only keep enums) to reduce prompt size
    schema["$defs"] = {k: v for k, v in defs.items() if k in enum_names}

    # Inline class definitions into top-level properties
    schema["properties"] = {}
    for class_name in sorted(class_names):
        class_def = defs.get(class_name, {})
        # Remove nested $ref artifacts
        clean_def = {k: v for k, v in class_def.items() if k != "$defs"}
        schema["properties"][class_name] = {
            "type": "array",
            "items": clean_def,
            "description": f"Array of {class_name} instances",
        }

    schema["description"] = "Instance schema — fill with concrete configuration data"
    return schema


def _find_id_field(class_def: dict) -> Optional[str]:
    """Find the field marked with x-is-id in a class definition."""
    for field_name, field_schema in class_def.get("properties", {}).items():
        if field_schema.get("x-is-id"):
            return field_name
    return None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_instance_prompts(
    wrapper_schema: dict[str, Any],
    document_text: str,
    *,
    instance_hints: Optional[str] = None,
) -> tuple[str, str]:
    """Build system + user prompts for M1 instance generation.

    Parameters
    ----------
    wrapper_schema : dict
        The full wrapper schema from ``build_wrapper_schema()``.
    document_text : str
        The original requirements document (for context).
    instance_hints : str | None
        Optional hints about what instances to generate.

    Returns
    -------
    tuple[str, str]
        (system_prompt, user_prompt)
    """
    instance_schema = _build_instance_schema(wrapper_schema)

    system_prompt = f"""You are a configuration instance generator for an MDE (Model-Driven Engineering) system.

You must output a JSON object that strictly conforms to the following JSON Schema.
The schema defines entity types as top-level arrays. Each array contains instances of that entity type.

## JSON Schema (you MUST conform to this)

```json
{json.dumps(instance_schema, indent=2, ensure_ascii=False)}
```

## Rules

1. Every required field MUST be present with a valid value.
2. Enum fields MUST use exactly one of the allowed enum values.
3. Association fields are ID references (strings). Use the x-is-id field value of the referenced instance.
4. All ID values must be unique within their entity type.
5. All ID references must point to an instance that exists in your output.
6. Sensitive fields (secret_ref, credential_ref, token_ref) MUST use placeholder format: "${{SECRET_NAME}}".
7. datetime fields use ISO 8601 format: "2025-01-01T00:00:00Z".
8. Optional fields (with "default": null) can be omitted or set to null.
9. Output ONLY the JSON object. No explanation, no markdown fences, no comments."""

    user_prompt = "## Requirements document (source context)\n\n"
    user_prompt += document_text[:8000]  # Truncate to avoid token overflow

    if instance_hints:
        user_prompt += f"\n\n## Instance generation hints\n\n{instance_hints}"
    else:
        user_prompt += """

## Instance generation instructions

Generate a realistic MVP configuration that includes:
- 1 AutomationProject with status ACTIVE
- 2 Environments (DESIGN, PRODUCTION)
- 2 PlatformConnectors (one GITHUB_TOKEN, one GITLAB_TOKEN)
- 1 CommunityOrganization with 3 Repositories
- 3 BotTemplates (NEW_CONTRIBUTOR_WELCOME, STALE_ISSUE_REMINDER, ISSUE_AUTO_TRIAGE)
- 3 BotInstances (one per template), each bound to at least 1 repository
- For each BotInstance: 1-2 Rules with EventTriggers and Actions
- 2 MessageTemplates, 1 NotificationTarget, 1 ApprovalPolicy for high-risk actions
- 1 ScheduleTask for the stale issue reminder

Make the data realistic — use plausible names, expressions, and configurations
that match the OSS community bot orchestration domain described in the document."""

    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

def extract_instances(
    document_text: str,
    wrapper_schema: dict[str, Any],
    *,
    provider: str = "openai",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    instance_hints: Optional[str] = None,
) -> dict[str, Any]:
    """Generate M1 configuration instances using LLM constrained by wrapper schema.

    Parameters
    ----------
    document_text : str
        Original requirements document for context.
    wrapper_schema : dict
        The M2 wrapper schema from ``build_wrapper_schema()``.
    provider : str
        "openai" or "anthropic".
    model : str
        Model name (e.g. "gpt-4o", "claude-sonnet-4-20250514").
    api_key : str | None
        API key.
    base_url : str | None
        Custom API base URL (for proxies).
    instance_hints : str | None
        Optional hints about what instances to generate.

    Returns
    -------
    dict
        M1 instance JSON conforming to the wrapper schema.
    """
    system_prompt, user_prompt = build_instance_prompts(
        wrapper_schema, document_text, instance_hints=instance_hints,
    )

    logger.info(
        "Instance extraction: system prompt %d chars, user prompt %d chars",
        len(system_prompt), len(user_prompt),
    )

    if provider == "openai":
        return _call_openai(system_prompt, user_prompt, model, api_key, base_url)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# LLM call implementations
# ---------------------------------------------------------------------------

def _call_openai(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: Optional[str],
    base_url: Optional[str],
) -> dict[str, Any]:
    """Call OpenAI-compatible API."""
    from openai import OpenAI

    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    client = OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    return _parse_json_response(raw)



def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse LLM response, stripping markdown fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON: %s", e)
        logger.debug("Raw response:\n%s", text[:2000])
        raise ValueError(f"LLM did not return valid JSON: {e}") from e
