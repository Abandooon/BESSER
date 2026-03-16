"""
Validation of ``NormalizedCandidateModel`` — schema conformance,
reference integrity, and structural-subset checks.

This module does **not** call an LLM.  It performs deterministic checks
that gate whether a candidate is safe to compile into a ``DomainModel``.

Check categories
----------------
1. **Schema conformance** — attribute types resolve to known primitives,
   enums, or classes.
2. **Reference integrity** — association ends and constraint contexts
   reference declared classes; enum-typed attributes reference declared
   enums.
3. **Duplicate detection** — no duplicate class / enum / association names.
4. **Structural-subset compliance** — warn about features that are
   outside the current WME round-trip-safe subset.
"""

from __future__ import annotations

import logging

from besser.utilities.requirements_to_buml.schemas import (
    NormalizedCandidateModel,
    ValidationReport,
    ValidationIssue,
)

logger = logging.getLogger(__name__)

_VALID_PRIMITIVES = {"str", "int", "float", "bool", "date", "datetime", "time", "timedelta", "any"}


def validate_candidate(
    normalized: NormalizedCandidateModel,
) -> ValidationReport:
    """Run all validation checks and return a ``ValidationReport``.

    The report's ``is_valid`` flag is *False* if any **error**-severity
    issue is found.  **Warning**-severity issues do not block compilation
    but should be surfaced in the review panel.
    """
    issues: list[ValidationIssue] = []

    known_classes = {c.name for c in normalized.classes}
    known_enums = {e.name for e in normalized.enumerations}
    known_types = known_classes | known_enums | _VALID_PRIMITIVES

    # ---- 1. Duplicate names ----------------------------------------------
    _check_duplicates("class", [c.name for c in normalized.classes], issues)
    _check_duplicates("enumeration", [e.name for e in normalized.enumerations], issues)
    _check_duplicates("association", [a.name for a in normalized.associations], issues)
    _check_duplicates("constraint", [c.name for c in normalized.constraints], issues)

    # Cross-namespace collision
    overlap = known_classes & known_enums
    for name in overlap:
        issues.append(ValidationIssue(
            severity="error",
            path=f"types/{name}",
            message=f"'{name}' is declared as both a class and an enumeration.",
        ))

    # ---- 2. Attribute type resolution ------------------------------------
    for cls in normalized.classes:
        for attr in cls.attributes:
            if attr.type not in known_types:
                issues.append(ValidationIssue(
                    severity="error",
                    path=f"classes/{cls.name}/attributes/{attr.name}",
                    message=(
                        f"Attribute type '{attr.type}' does not resolve to a "
                        "known primitive, enumeration, or class."
                    ),
                ))

    # ---- 3. Association end references -----------------------------------
    for assoc in normalized.associations:
        for label, end in [("end1", assoc.end1), ("end2", assoc.end2)]:
            if end.type not in known_classes:
                issues.append(ValidationIssue(
                    severity="error",
                    path=f"associations/{assoc.name}/{label}",
                    message=(
                        f"Association end type '{end.type}' does not reference "
                        "a declared class."
                    ),
                ))

    # ---- 4. Constraint context references --------------------------------
    for constr in normalized.constraints:
        if constr.context not in known_classes:
            issues.append(ValidationIssue(
                severity="error",
                path=f"constraints/{constr.name}",
                message=(
                    f"Constraint context '{constr.context}' does not reference "
                    "a declared class."
                ),
            ))

    # ---- 5. At most one is_id per class ----------------------------------
    for cls in normalized.classes:
        id_attrs = [a for a in cls.attributes if a.is_id]
        if len(id_attrs) > 1:
            names = ", ".join(a.name for a in id_attrs)
            issues.append(ValidationIssue(
                severity="error",
                path=f"classes/{cls.name}",
                message=f"Multiple is_id attributes found: {names}. A class may have at most one.",
            ))

    # ---- 6. Multiplicity format ------------------------------------------
    for cls in normalized.classes:
        for attr in cls.attributes:
            if not _valid_multiplicity(attr.multiplicity):
                issues.append(ValidationIssue(
                    severity="warning",
                    path=f"classes/{cls.name}/attributes/{attr.name}",
                    message=f"Multiplicity '{attr.multiplicity}' is not in canonical 'min..max' form.",
                ))
    for assoc in normalized.associations:
        for label, end in [("end1", assoc.end1), ("end2", assoc.end2)]:
            if not _valid_multiplicity(end.multiplicity):
                issues.append(ValidationIssue(
                    severity="warning",
                    path=f"associations/{assoc.name}/{label}",
                    message=f"Multiplicity '{end.multiplicity}' is not in canonical form.",
                ))

    # ---- 7. Enum literal emptiness ---------------------------------------
    for enum in normalized.enumerations:
        if not enum.literals:
            issues.append(ValidationIssue(
                severity="warning",
                path=f"enumerations/{enum.name}",
                message=f"Enumeration '{enum.name}' has no literals.",
            ))

    # ---- 8. Structural-subset warnings -----------------------------------
    _check_structural_subset_risks(normalized, issues)

    is_valid = not any(i.severity == "error" for i in issues)
    report = ValidationReport(is_valid=is_valid, issues=issues)

    if not is_valid:
        error_count = sum(1 for i in issues if i.severity == "error")
        logger.warning("Validation failed with %d error(s).", error_count)
    else:
        logger.info("Validation passed (%d warning(s)).", len(issues))

    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_duplicates(
    kind: str,
    names: list[str],
    issues: list[ValidationIssue],
) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            issues.append(ValidationIssue(
                severity="error",
                path=f"{kind}s/{name}",
                message=f"Duplicate {kind} name: '{name}'.",
            ))
        seen.add(name)


def _valid_multiplicity(m: str) -> bool:
    """Return *True* if *m* looks like ``'N..M'`` or ``'N..*'``."""
    if not m:
        return False
    if ".." not in m:
        return m.isdigit() or m == "*"
    parts = m.split("..")
    if len(parts) != 2:
        return False
    lo, hi = parts
    lo_ok = lo.isdigit()
    hi_ok = hi.isdigit() or hi == "*"
    return lo_ok and hi_ok


def _check_structural_subset_risks(
    normalized: NormalizedCandidateModel,
    issues: list[ValidationIssue],
) -> None:
    """Warn about features outside the current WME round-trip-safe subset."""
    # Multi-valued attributes need the multiplicity converter fix
    for cls in normalized.classes:
        for attr in cls.attributes:
            if attr.multiplicity not in ("1..1", "0..1", "1..1"):
                parts = attr.multiplicity.split("..")
                if len(parts) == 2 and (parts[1] == "*" or (parts[1].isdigit() and int(parts[1]) > 1)):
                    issues.append(ValidationIssue(
                        severity="info",
                        path=f"classes/{cls.name}/attributes/{attr.name}",
                        message=(
                            f"Multi-valued attribute (multiplicity {attr.multiplicity}) "
                            "requires the attribute-level multiplicity round-trip fix "
                            "(02-besser_debug §1.3)."
                        ),
                    ))

    # Abstract classes
    for cls in normalized.classes:
        if cls.is_abstract:
            issues.append(ValidationIssue(
                severity="info",
                path=f"classes/{cls.name}",
                message=(
                    f"Abstract class '{cls.name}' — verify is_abstract round-trips "
                    "correctly (generally supported)."
                ),
            ))
