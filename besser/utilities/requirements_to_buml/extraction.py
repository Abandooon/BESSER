"""
Document reading, LLM provider adaptation, and candidate extraction.

This module calls an LLM with the M3-projection-schema-constrained prompt
and parses the response into a ``CandidateModel``.

Supported providers
-------------------
* ``openai``     – OpenAI Chat Completions API (default)
* ``anthropic``  – Anthropic Messages API

The provider is selected via the ``provider`` parameter.  API keys fall
back to the standard environment variables (``OPENAI_API_KEY``,
``ANTHROPIC_API_KEY``) when not passed explicitly.
"""

from __future__ import annotations

import json
import os
import re
import logging
from typing import Any

from besser.utilities.requirements_to_buml.schemas import CandidateModel
from besser.utilities.requirements_to_buml.prompting import (
    SYSTEM_PROMPT,
    build_user_prompt,
    OSS_BOT_DOMAIN_HINT,
    OSS_BOT_CORE_CLASS_HINTS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Document helpers
# ---------------------------------------------------------------------------

def read_document(path: str) -> str:
    """Read a requirements document from *path* (Markdown or plain text)."""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _strip_json_fences(text: str) -> str:
    """Remove optional ```json … ``` markdown fences from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        # remove opening fence (```json or ```)
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        # remove closing fence
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
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> str:
    """Call OpenAI Chat Completions and return the assistant message text."""
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for provider='openai'. "
            "Install it with: pip install openai"
        ) from exc

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "No OpenAI API key provided. Pass api_key= or set OPENAI_API_KEY."
        )

    client = openai.OpenAI(api_key=key)
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _call_anthropic(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    api_key: str | None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> str:
    """Call Anthropic Messages API and return the assistant message text."""
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "The 'anthropic' package is required for provider='anthropic'. "
            "Install it with: pip install anthropic"
        ) from exc

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError(
            "No Anthropic API key provided. Pass api_key= or set ANTHROPIC_API_KEY."
        )

    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model=model,
        system=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # Anthropic returns a list of content blocks
    return "".join(
        block.text for block in response.content if hasattr(block, "text")
    )


_PROVIDERS: dict[str, Any] = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_candidate(
    document_text: str,
    *,
    provider: str = "openai",
    model: str = "gpt-4o",
    api_key: str | None = None,
    domain_hint: str | None = None,
    core_class_hints: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> CandidateModel:
    """Extract a ``CandidateModel`` from a natural-language requirements doc.

    Parameters
    ----------
    document_text : str
        The full text of the requirements document.
    provider : str
        ``"openai"`` or ``"anthropic"``.
    model : str
        LLM model identifier (e.g. ``"gpt-4o"``, ``"claude-sonnet-4-20250514"``).
    api_key : str | None
        Explicit API key (falls back to env var).
    domain_hint : str | None
        Domain-specific guidance injected into the prompt.  When *None*,
        the OSS Bot domain hint is used as the default.
    core_class_hints : str | None
        Comma-separated list of suggested core class names.
    temperature : float
        Sampling temperature.
    max_tokens : int
        Maximum response tokens.

    Returns
    -------
    CandidateModel
        Parsed and validated candidate domain metamodel.
    """
    call_fn = _PROVIDERS.get(provider)
    if call_fn is None:
        raise ValueError(
            f"Unknown provider '{provider}'. Supported: {list(_PROVIDERS)}"
        )

    # Assemble prompts
    user_prompt = build_user_prompt(
        document_text=document_text,
        domain_hint=domain_hint or OSS_BOT_DOMAIN_HINT,
        core_class_hints=core_class_hints or OSS_BOT_CORE_CLASS_HINTS,
    )

    logger.info("Calling %s / %s for candidate extraction …", provider, model)

    raw_text = call_fn(
        SYSTEM_PROMPT,
        user_prompt,
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Parse JSON
    cleaned = _strip_json_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON:\n%s", cleaned[:2000])
        raise ValueError(
            f"LLM output is not valid JSON: {exc}"
        ) from exc

    # Validate against CandidateModel schema
    candidate = CandidateModel.model_validate(data)
    logger.info(
        "Extracted candidate: %d classes, %d enums, %d associations",
        len(candidate.classes),
        len(candidate.enumerations),
        len(candidate.associations),
    )
    return candidate
