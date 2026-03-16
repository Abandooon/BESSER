"""
Compile a ``NormalizedCandidateModel`` (JSON representation) into a
BESSER ``DomainModel`` (the M2 centre representation).

This module uses **only programmatic construction** (direct calls to
``Class()``, ``Property()``, ``BinaryAssociation()`` etc.) — it never
invokes ``parse_buml_content`` or any ``exec()``-based path.

This satisfies Gatecheck D from 03_BESSER修改与原型实现方案:
> requirements import 主路径不得依赖执行不可信文本
"""

from __future__ import annotations

import logging
from typing import Any

from besser.BUML.metamodel.structural import (
    DomainModel,
    Class,
    Property,
    BinaryAssociation,
    Enumeration,
    EnumerationLiteral,
    Generalization,
    Constraint,
    Multiplicity,
    PrimitiveDataType,
    Metadata,
    UNLIMITED_MAX_MULTIPLICITY,
    StringType,
    IntegerType,
    FloatType,
    BooleanType,
    DateType,
    DateTimeType,
    TimeType,
    TimeDeltaType,
    AnyType,
)
from besser.utilities.requirements_to_buml.m3_schema_projector import (
    NormalizedCandidateModel,
    NormalizedClass,
    NormalizedProperty,
    NormalizedAssociation,
    NormalizedAssociationEnd,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primitive-type singleton lookup
# ---------------------------------------------------------------------------

_PRIMITIVE_MAP: dict[str, PrimitiveDataType] = {
    "str": StringType,
    "int": IntegerType,
    "float": FloatType,
    "bool": BooleanType,
    "date": DateType,
    "datetime": DateTimeType,
    "time": TimeType,
    "timedelta": TimeDeltaType,
    "any": AnyType,
}


# ---------------------------------------------------------------------------
# Multiplicity parsing
# ---------------------------------------------------------------------------

def _parse_multiplicity(raw: str) -> Multiplicity:
    """Parse a canonical ``'min..max'`` string into a ``Multiplicity``."""
    if not raw or raw == "1..1":
        return Multiplicity(1, 1)
    parts = raw.split("..")
    try:
        lo = int(parts[0])
    except (ValueError, IndexError):
        lo = 1
    try:
        hi_str = parts[1] if len(parts) > 1 else parts[0]
        hi = UNLIMITED_MAX_MULTIPLICITY if hi_str == "*" else int(hi_str)
    except (ValueError, IndexError):
        hi = lo
    return Multiplicity(lo, hi)


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def compile_to_domain_model(
    normalized: NormalizedCandidateModel,
) -> DomainModel:
    """Compile a ``NormalizedCandidateModel`` into a BESSER ``DomainModel``.

    Construction order
    ------------------
    1. Enumerations (so classes can reference them as attribute types).
    2. Classes (skeleton, no attributes yet — so association ends can
       reference class types).
    3. Class attributes (resolve types against the type registry).
    4. Associations (both ends reference existing classes).
    5. Constraints.
    6. Assemble DomainModel.

    Parameters
    ----------
    normalized : NormalizedCandidateModel
        The output of ``normalize_candidate()``.

    Returns
    -------
    DomainModel
        A fully constructed BESSER DomainModel.
    """

    # ---- 1. Build enumerations -------------------------------------------
    enum_registry: dict[str, Enumeration] = {}
    for norm_enum in normalized.enumerations:
        literals = set()
        for lit in norm_enum.literals:
            literals.add(EnumerationLiteral(name=lit.name))
        enum_obj = Enumeration(name=norm_enum.name, literals=literals)
        if norm_enum.description:
            enum_obj.metadata = Metadata(description=norm_enum.description)
        enum_registry[norm_enum.name] = enum_obj

    # ---- 2. Build class skeletons ----------------------------------------
    class_registry: dict[str, Class] = {}
    for norm_cls in normalized.classes:
        metadata = None
        if norm_cls.description:
            metadata = Metadata(description=norm_cls.description)
        cls = Class(
            name=norm_cls.name,
            is_abstract=norm_cls.is_abstract,
            metadata=metadata,
        )
        class_registry[norm_cls.name] = cls

    # ---- 3. Add attributes to classes ------------------------------------
    for norm_cls in normalized.classes:
        cls = class_registry[norm_cls.name]
        for norm_attr in norm_cls.attributes:
            type_obj = _resolve_type(norm_attr.type, class_registry, enum_registry)
            prop = Property(
                name=norm_attr.name,
                type=type_obj,
                visibility=norm_attr.visibility.value,
                is_id=norm_attr.is_id,
                is_read_only=norm_attr.is_read_only,
                is_optional=norm_attr.is_optional,
                default_value=norm_attr.default_value,
                multiplicity=_parse_multiplicity(norm_attr.multiplicity),
            )
            cls.add_attribute(prop)

    # ---- 4. Build associations -------------------------------------------
    assoc_set: set[BinaryAssociation] = set()
    for norm_assoc in normalized.associations:
        end1_cls = class_registry.get(norm_assoc.end1.type)
        end2_cls = class_registry.get(norm_assoc.end2.type)

        if end1_cls is None:
            logger.warning(
                "Association '%s' end1 references unknown class '%s' — skipped",
                norm_assoc.name,
                norm_assoc.end1.type,
            )
            continue
        if end2_cls is None:
            logger.warning(
                "Association '%s' end2 references unknown class '%s' — skipped",
                norm_assoc.name,
                norm_assoc.end2.type,
            )
            continue

        end1_prop = Property(
            name=norm_assoc.end1.role,
            type=end1_cls,
            multiplicity=_parse_multiplicity(norm_assoc.end1.multiplicity),
            is_navigable=norm_assoc.end1.is_navigable,
            is_composite=norm_assoc.end1.is_composite,
        )
        end2_prop = Property(
            name=norm_assoc.end2.role,
            type=end2_cls,
            multiplicity=_parse_multiplicity(norm_assoc.end2.multiplicity),
            is_navigable=norm_assoc.end2.is_navigable,
            is_composite=norm_assoc.end2.is_composite,
        )

        try:
            assoc = BinaryAssociation(
                name=norm_assoc.name,
                ends={end1_prop, end2_prop},
            )
            assoc_set.add(assoc)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Could not create association '%s': %s — skipped",
                norm_assoc.name,
                exc,
            )

    # ---- 5. Build constraints --------------------------------------------
    constraint_set: set[Constraint] = set()
    for norm_constr in normalized.constraints:
        ctx_cls = class_registry.get(norm_constr.context)
        if ctx_cls is None:
            logger.warning(
                "Constraint '%s' references unknown class '%s' — skipped",
                norm_constr.name,
                norm_constr.context,
            )
            continue
        constr = Constraint(
            name=norm_constr.name,
            context=ctx_cls,
            expression=norm_constr.expression,
            language=norm_constr.language,
        )
        constraint_set.add(constr)

    # ---- 6. Assemble DomainModel -----------------------------------------
    all_types = set(class_registry.values()) | set(enum_registry.values())

    domain_model = DomainModel(
        name=normalized.domain_name or "Domain",
        types=all_types,
        associations=assoc_set,
        constraints=constraint_set,
    )

    logger.info(
        "Compiled DomainModel '%s': %d types, %d associations, %d constraints",
        domain_model.name,
        len([t for t in domain_model.types if isinstance(t, (Class, Enumeration))]),
        len(domain_model.associations),
        len(domain_model.constraints),
    )
    return domain_model


# ---------------------------------------------------------------------------
# Type resolution helper
# ---------------------------------------------------------------------------

def _resolve_type(
    type_name: str,
    class_registry: dict[str, Class],
    enum_registry: dict[str, Enumeration],
) -> Any:
    """Resolve a type name to a BESSER type object.

    Resolution order:
    1. BESSER primitive singletons
    2. Known enumerations
    3. Known classes
    4. Fallback to ``StringType``
    """
    # 1. Primitive
    if type_name in _PRIMITIVE_MAP:
        return _PRIMITIVE_MAP[type_name]
    # 2. Enumeration
    if type_name in enum_registry:
        return enum_registry[type_name]
    # 3. Class
    if type_name in class_registry:
        return class_registry[type_name]
    # 4. Fallback
    logger.warning("Type '%s' not found — falling back to StringType", type_name)
    return StringType
