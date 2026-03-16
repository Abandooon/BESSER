"""
config_projection — Generate M2-compatible projections from a confirmed
BESSER ``DomainModel``.

Projections produced
--------------------
* **wrapper_schema**  – JSON Schema for M1 instance editing, chat-patch
  validation, and config workbench rendering.
* **field_groups**    – Logical groupings of fields for form layout.
* **editor_hints**    – UI metadata (display hints, conditional visibility,
  read-only markers, reference pickers).

All projections derive from the single confirmed ``DomainModel`` (M2).
They are **not** a second truth source.
"""

from besser.utilities.config_projection.wrapper_schema_builder import (
    build_wrapper_schema,
)
from besser.utilities.config_projection.field_group_builder import (
    build_field_groups,
)
from besser.utilities.config_projection.editor_hints_builder import (
    build_editor_hints,
)
from besser.utilities.config_projection.sidecar_merger import (
    merge_sidecar_into_schema,
)
