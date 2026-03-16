"""
Generate ``ReviewSummary`` and ``ReviewSidecar`` from a compiled
``NormalizedCandidateModel`` + ``DomainModel``.

The review artefacts serve two purposes:
1. **ReviewSummary** — human-facing checklist for the candidate-review panel.
2. **ReviewSidecar** — structured-support semantics that cannot yet
   round-trip through the WME class-diagram JSON main chain.

High-priority checks (from 02_需求到候选B-UML规范 §9):
- AutomationProject ≠ CommunityOrganization
- BotTemplate / BotInstance correctly separated
- BotInstance → Repository is an association, not a string
- Rule / Action boundary is clean
- High-risk actions linked to ApprovalPolicy
- Template field specs and action parameter semantics are fully carried
- No accidental abstract-inheritance-driven dynamic forms
- Sidecar items that should migrate back to main chain are flagged
"""

from __future__ import annotations

import logging

from besser.BUML.metamodel.structural import (
    DomainModel,
    Class,
    Enumeration,
    BinaryAssociation,
)
from besser.utilities.requirements_to_buml.schemas import (
    NormalizedCandidateModel,
    ReviewSummary,
    ReviewSidecar,
    ReviewWarning,
    SidecarEntry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# High-priority domain-specific checks
# ---------------------------------------------------------------------------

def _check_class_separation(
    normalized: NormalizedCandidateModel,
    warnings: list[ReviewWarning],
) -> None:
    """Warn if key class pairs are missing or possibly conflated."""
    class_names = {c.name for c in normalized.classes}

    pairs = [
        ("BotTemplate", "BotInstance", "BotTemplate/BotInstance must be separate classes."),
        ("Rule", "Action", "Rule/Action must be separate classes."),
        ("AutomationProject", "CommunityOrganization",
         "AutomationProject and CommunityOrganization must not be conflated."),
    ]
    for a, b, msg in pairs:
        if a not in class_names:
            warnings.append(ReviewWarning(
                severity="warning",
                category="missing_class",
                message=f"Expected class '{a}' not found.",
                related_element=a,
            ))
        if b not in class_names:
            warnings.append(ReviewWarning(
                severity="warning",
                category="missing_class",
                message=f"Expected class '{b}' not found.",
                related_element=b,
            ))


def _check_associations_not_strings(
    normalized: NormalizedCandidateModel,
    warnings: list[ReviewWarning],
) -> None:
    """Warn if key relationships appear as string attributes instead of associations."""
    assoc_pairs = set()
    for assoc in normalized.associations:
        assoc_pairs.add((assoc.end1.type, assoc.end2.type))
        assoc_pairs.add((assoc.end2.type, assoc.end1.type))

    required_relations = [
        ("BotInstance", "Repository", "bot_instance_repositories"),
        ("BotInstance", "BotTemplate", "bot_instance_template"),
        ("Rule", "EventTrigger", "rule_trigger"),
        ("Action", "ApprovalPolicy", "action_approval"),
    ]
    for src, tgt, label in required_relations:
        if (src, tgt) not in assoc_pairs:
            # Check if it's been incorrectly modeled as a string attribute
            for cls in normalized.classes:
                if cls.name == src:
                    for attr in cls.attributes:
                        lower_name = attr.name.lower()
                        lower_tgt = tgt.lower()
                        if lower_tgt in lower_name or lower_name.endswith("_id"):
                            warnings.append(ReviewWarning(
                                severity="warning",
                                category="string_instead_of_assoc",
                                message=(
                                    f"'{src}.{attr.name}' might be a string-typed "
                                    f"foreign key that should be an association to '{tgt}'."
                                ),
                                related_element=f"{src}.{attr.name}",
                            ))


def _check_high_risk_approval(
    normalized: NormalizedCandidateModel,
    warnings: list[ReviewWarning],
) -> None:
    """Warn if high-risk action patterns lack ApprovalPolicy links."""
    has_approval_assoc = any(
        "ApprovalPolicy" in (a.end1.type, a.end2.type)
        for a in normalized.associations
    )
    has_approval_class = any(c.name == "ApprovalPolicy" for c in normalized.classes)

    if has_approval_class and not has_approval_assoc:
        warnings.append(ReviewWarning(
            severity="warning",
            category="missing_approval_link",
            message=(
                "ApprovalPolicy class exists but no association links it to "
                "Action or Rule. High-risk actions may lack approval enforcement."
            ),
            related_element="ApprovalPolicy",
        ))


def _check_inheritance_complexity(
    normalized: NormalizedCandidateModel,
    warnings: list[ReviewWarning],
) -> None:
    """Warn if abstract classes suggest inheritance-driven dynamic forms."""
    abstract_count = sum(1 for c in normalized.classes if c.is_abstract)
    if abstract_count > 2:
        warnings.append(ReviewWarning(
            severity="info",
            category="inheritance_complexity",
            message=(
                f"Found {abstract_count} abstract classes. First-phase design "
                "should prefer composition and explicit type/kind discriminators "
                "over deep inheritance for form generation."
            ),
            related_element="(multiple)",
        ))


# ---------------------------------------------------------------------------
# Round-trip risk assessment
# ---------------------------------------------------------------------------

_ROUNDTRIP_RISK_NOTES = [
    "Attribute-level multiplicity (e.g. 0..*) requires the is_id/is_read_only/multiplicity "
    "converter fix (02-besser_debug §1.1–1.3) to be applied.",
    "GeneralizationSet (is_disjoint/is_complete) is not yet round-tripped by WME converters.",
    "Aggregation relationships may degrade to bidirectional after round-trip.",
    "Class-level is_read_only is not serialised in WME export direction.",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_review(
    normalized: NormalizedCandidateModel,
    domain_model: DomainModel,
) -> tuple[ReviewSummary, ReviewSidecar]:
    """Produce review artefacts from a compiled model.

    Returns
    -------
    (ReviewSummary, ReviewSidecar)
    """
    warnings: list[ReviewWarning] = []

    # Domain-specific checks
    _check_class_separation(normalized, warnings)
    _check_associations_not_strings(normalized, warnings)
    _check_high_risk_approval(normalized, warnings)
    _check_inheritance_complexity(normalized, warnings)

    # Build sidecar from collected items
    sidecar_entries: list[SidecarEntry] = []
    for item in normalized.sidecar_items:
        sidecar_entries.append(SidecarEntry(
            owner_class=item.get("owner_class", ""),
            field_name=item.get("field_name", ""),
            kind=item.get("kind", "unknown"),
            payload=item.get("payload", {}),
            description=item.get("description", ""),
        ))

    # High-priority review checks
    high_priority = [
        "Verify AutomationProject is not conflated with CommunityOrganization.",
        "Verify BotTemplate / BotInstance are correctly separated.",
        "Verify BotInstance → Repository is an association (not a string attribute).",
        "Verify Rule / Action boundary is clean.",
        "Verify high-risk actions are linked to ApprovalPolicy.",
        "Verify template field specs and action parameter semantics are fully carried.",
        "Verify no accidental abstract-inheritance-driven dynamic form design.",
        "Review sidecar items for semantics that should migrate to main chain.",
    ]

    summary = ReviewSummary(
        class_names=[c.name for c in normalized.classes],
        enumeration_names=[e.name for e in normalized.enumerations],
        association_names=[a.name for a in normalized.associations],
        constraint_names=[c.name for c in normalized.constraints],
        unresolved_items=list(normalized.unresolved_items),
        warnings=warnings,
        sidecar_item_count=len(sidecar_entries),
        round_trip_risks=list(_ROUNDTRIP_RISK_NOTES),
        high_priority_checks=high_priority,
    )

    sidecar = ReviewSidecar(
        entries=sidecar_entries,
        metadata={
            "domain_name": normalized.domain_name,
            "generated_by": "requirements_to_buml.review",
        },
    )

    logger.info(
        "Review generated: %d warnings, %d sidecar entries",
        len(warnings),
        len(sidecar_entries),
    )
    return summary, sidecar
