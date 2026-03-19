"""
Document reading, LLM provider adaptation, and candidate extraction.

This module calls an LLM with the M3-projection-schema-constrained prompt
and parses the response into a ``CandidateModel``.

Supported providers
-------------------
* ``openai``     – OpenAI Chat Completions API
* ``anthropic``  – Anthropic Messages API
"""

from __future__ import annotations

import json
import os
import re
import logging
from typing import Any

from besser.utilities.requirements_to_buml.m3_schema_projector import CandidateModel
from besser.utilities.requirements_to_buml.prompting import (
    build_system_prompt,
    build_user_prompt,
)

logger = logging.getLogger(__name__)


def read_document(path: str) -> str:
    """Read a requirements document from *path* (Markdown or plain text)."""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_json_fences(text: str) -> str:
    """Remove optional ```json … ``` markdown fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# LLM provider adapters
# ---------------------------------------------------------------------------

def _call_openai(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    api_key: str | None,
    base_url: str | None = "https://api.openai-proxy.org/v1",
    temperature: float = 1.0
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError("pip install -U openai") from exc

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("No OpenAI API key. Pass api_key= or set OPENAI_API_KEY.")

    resolved_base_url = (
        base_url
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("OPENAI_API_BASE")
    )

    client_kwargs = {"api_key": key}
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url

    client = OpenAI(**client_kwargs)

    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    content = resp.choices[0].message.content
    if not content:
        raise ValueError("OpenAI response did not contain message content.")
    return content



_PROVIDERS: dict[str, Any] = {
    "openai": _call_openai
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_candidate(
    document_text: str,
    *,
    provider: str = "openai",
    model: str = "gpt-5-nano",
    api_key: str | None = None,
    base_url: str | None = None,
    domain_hint: str | None = None,
    core_class_hints: str | None = None,
    temperature: float = 1.0
) -> CandidateModel:
    """
    Extract a ``CandidateModel`` from a natural-language requirements doc.

    Parameters
    ----------
    provider : str
        Supported providers: "openai".
    model : str
        Provider model identifier.
    api_key : str | None
        Explicit API key; falls back to environment variable.
    base_url : str | None
        Optional OpenAI-compatible endpoint base URL. Used only when
        ``provider="openai"``.
    domain_hint : str | None
        Domain-specific guidance. ``None`` means domain-agnostic.
    """
    call_fn = _PROVIDERS.get(provider)
    if call_fn is None:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {list(_PROVIDERS)}")

    # build_user_prompt handles None → domain-agnostic, registry keys, free text
    user_prompt = build_user_prompt(
        document_text=document_text,
        domain_hint=domain_hint,
        core_class_hints=core_class_hints,
    )

    system_prompt = build_system_prompt()

    logger.info("Calling %s / %s for candidate extraction …", provider, model)

    raw_text = call_fn(
        system_prompt,
        user_prompt,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature
    )

    cleaned = _strip_json_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON:\n%s", cleaned[:2000])
        raise ValueError(f"LLM output is not valid JSON: {exc}") from exc

    candidate = CandidateModel.model_validate(data)
    logger.info(
        "Extracted: %d classes, %d enums, %d associations",
        len(candidate.classes), len(candidate.enumerations), len(candidate.associations),
    )
    return candidate
