"""
requirements_to_buml — Convert natural-language requirements documents into
candidate B-UML DomainModel instances.

Public API
----------
- ``requirements_to_buml``  : end-to-end convenience function
- ``extract_candidate``     : LLM-based candidate extraction
- ``normalize_candidate``   : deterministic normalization pass
- ``compile_to_domain_model``: compile normalized JSON → DomainModel
- ``generate_review``       : produce review_summary + review_sidecar
- ``validate_candidate``    : schema & reference-integrity checks

Schemas (Pydantic v2)
---------------------
- ``CandidateModel`` / ``NormalizedCandidateModel``
- ``ReviewSummary`` / ``ReviewSidecar``
"""

from besser.utilities.requirements_to_buml.extraction import extract_candidate
from besser.utilities.requirements_to_buml.normalization import normalize_candidate
from besser.utilities.requirements_to_buml.compilation import compile_to_domain_model
from besser.utilities.requirements_to_buml.review import generate_review
from besser.utilities.requirements_to_buml.validation import validate_candidate
from besser.utilities.requirements_to_buml.m3_schema_projector import (
    CandidateModel,
    NormalizedCandidateModel,
    ReviewSummary,
    ReviewSidecar,
)


def requirements_to_buml(
    document_text: str,
    *,
    provider: str = "openai",
    model: str = "gpt-5-nano",
    api_key: str | None = None,
    base_url: str | None = None,
    domain_hint: str | None = None,
    skip_llm: bool = False,
    candidate_json: dict | None = None,
):
    """End-to-end: requirements document → DomainModel + review artefacts.

    Parameters
    ----------
    document_text : str
        Raw requirements document (Markdown / plain text).
    provider : str
        LLM provider name (``"openai"`` | ``"anthropic"``).
    model : str
        Model identifier string.
    api_key : str | None
        API key; falls back to env vars if *None*.
    domain_hint : str | None
        Optional domain-specific hint injected into the prompt.
    skip_llm : bool
        If *True*, ``candidate_json`` must be supplied and the LLM
        extraction step is skipped (useful for testing / replay).
    candidate_json : dict | None
        Pre-built candidate dict — used when *skip_llm* is *True*.

    Returns
    -------
    dict
        ``{ "domain_model", "candidate", "normalized", "review_summary",
            "review_sidecar", "validation_report" }``
    """
    # --- Step 1: extract candidate ----------------------------------------
    if skip_llm:
        if candidate_json is None:
            raise ValueError("candidate_json is required when skip_llm=True")
        candidate = CandidateModel.model_validate(candidate_json)
    else:
        candidate = extract_candidate(
            document_text,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            domain_hint=domain_hint,
        )

    # --- Step 2: normalize ------------------------------------------------
    normalized = normalize_candidate(candidate)

    # --- Step 3: validate -------------------------------------------------
    validation_report = validate_candidate(normalized)

    # --- Step 4: compile --------------------------------------------------
    domain_model = compile_to_domain_model(normalized)

    # --- Step 5: review ---------------------------------------------------
    review_summary, review_sidecar = generate_review(normalized, domain_model)

    return {
        "domain_model": domain_model,
        "candidate": candidate,
        "normalized": normalized,
        "review_summary": review_summary,
        "review_sidecar": review_sidecar,
        "validation_report": validation_report,
    }
