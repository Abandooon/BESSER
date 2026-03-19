"""
Build a **wrapper JSON Schema** from a confirmed BESSER ``DomainModel``.

The wrapper schema is the single contract consumed by:
* Config Workbench form renderer
* Chat-based structured patch validator
* Export / import compatibility checker

It is an M2 → M1 projection — NOT a new truth source.

Architecture (fixing Deviation B from 04_实施状态与修正方案):
    Previous version hand-wrote ``_type_to_schema`` / ``_property_schema`` /
    ``_enum_schema``, duplicating PydanticGenerator's type mapping logic.

    This version delegates base JSON Schema generation to
    ``generator_bridge.generate_base_json_schema()``, which calls BESSER's
    ``PydanticGenerator`` → dynamic import → ``.model_json_schema()``.
    Then it layers DomainModel metadata on top (``x-is-id``, ``readOnly``,
    ``x-composite``, association annotations, sidecar markers).

Chain::

    DomainModel
      → generator_bridge.generate_base_json_schema()   (base schema from PydanticGenerator)
      → _augment_with_metadata()                       (overlay is_id, is_read_only, etc.)
      → wrapper schema                                  (M2→M1 projection)
"""

from __future__ import annotations

import logging
from typing import Any

from besser.BUML.metamodel.structural import (
    DomainModel,
    BinaryAssociation,
)
from besser.utilities.config_projection.generator_bridge import (
    generate_base_json_schema,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_wrapper_schema(
    domain_model: DomainModel,
    *,
    schema_id: str | None = None,
) -> dict[str, Any]:
    """Build a wrapper JSON Schema from *domain_model*.

    1. Calls ``generator_bridge.generate_base_json_schema()`` to get the
       base schema (via BESSER's PydanticGenerator).
    2. Overlays DomainModel metadata: ``x-is-id``, ``readOnly``,
       ``x-composite``, association descriptions.

    Parameters
    ----------
    domain_model : DomainModel
        The confirmed M2 centre representation.
    schema_id : str | None
        Optional ``$id`` for the root schema.

    Returns
    -------
    dict
        A JSON Schema document with ``$defs`` for every class and enum.
    """
    # --- Step 1: base schema from PydanticGenerator ---
    schema = generate_base_json_schema(domain_model)

    if schema_id:
        schema["$id"] = schema_id

    schema["description"] = f"Wrapper schema for domain '{domain_model.name}'"

    # --- Step 2: augment with DomainModel metadata ---
    defs = schema.get("$defs", {})
    _augment_with_metadata(defs, domain_model)

    logger.info(
        "Wrapper schema built: %d defs, %d top-level properties",
        len(defs),
        len(schema.get("properties", {})),
    )
    return schema


# ---------------------------------------------------------------------------
# Metadata overlay — enrich base schema with M2 semantics
# ---------------------------------------------------------------------------

def _augment_with_metadata(
    defs: dict[str, Any],
    domain_model: DomainModel,
) -> None:
    """Mutate *defs* in place, adding metadata from DomainModel.

    The base schema from PydanticGenerator already has correct types,
    optionality, and enum references.  This function adds:
    - ``x-is-id`` on id properties
    - ``readOnly`` on read-only properties
    - ``x-abstract`` on abstract classes
    - ``x-composite`` on composite association ends
    - ``description`` from Metadata
    - association-end annotations
    """
    for cls in domain_model.get_classes():
        class_def = defs.get(cls.name)
        if class_def is None:
            continue

        props = class_def.get("properties", {})

        # --- Attribute metadata ---
        for attr in cls.attributes:
            prop_schema = props.get(attr.name)
            if prop_schema is None:
                continue

            if attr.is_id:
                prop_schema["x-is-id"] = True
            if attr.is_read_only:
                prop_schema["readOnly"] = True
            if attr.metadata and attr.metadata.description:
                prop_schema["description"] = attr.metadata.description

        # --- Class metadata ---
        if cls.is_abstract:
            class_def["x-abstract"] = True
        if cls.metadata and cls.metadata.description:
            class_def["description"] = cls.metadata.description

        # --- Association end metadata ---
        for assoc in cls.associations:
            if not isinstance(assoc, BinaryAssociation):
                continue
            for end in assoc.ends:
                if end.type == cls:
                    continue  # skip self-referencing end
                end_schema = props.get(end.name)
                if end_schema is None:
                    continue
                if end.is_composite:
                    end_schema["x-composite"] = True
                end_schema["x-association"] = assoc.name
