"""
Editor Workflow API — business endpoints for the requirements-import and
config-workbench pipeline.

This is a **FastAPI Router** included by ``backend.py``.  It adds the
following endpoint groups:

1. ``/besser_api/requirements/*``  — requirements import (Stage 1)
2. ``/besser_api/config/*``        — wrapper schema & patch (Stage 2–3)

All endpoints operate on the M3→M2→M1 chain defined in docs 02/03.
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

# Stage 1 — requirements → candidate → DomainModel
from besser.utilities.requirements_to_buml import requirements_to_buml
from besser.utilities.requirements_to_buml.m3_schema_projector import (
    CandidateModel,
    NormalizedCandidateModel,
    ReviewSummary,
    ReviewSidecar,
    ValidationReport,
)

# Stage 2 — DomainModel → wrapper schema / field groups / editor hints
from besser.utilities.config_projection import (
    build_wrapper_schema,
    build_field_groups,
    build_editor_hints,
    merge_sidecar_into_schema,
)
from besser.utilities.config_projection.sidecar_merger import (
    merge_sidecar_into_hints,
)

# Converters for WME integration — import the .py file directly to avoid
# pulling in the full buml_to_json/__init__.py chain (agent/gui converters
# require optional deps like deep_translator, etc.)
from besser.utilities.web_modeling_editor.backend.services.converters.buml_to_json.class_diagram_converter import (
    class_buml_to_json,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/besser_api", tags=["editor-workflow"])


# ===================================================================
# Request / Response models
# ===================================================================

class RequirementsImportRequest(BaseModel):
    """Body for ``POST /requirements/import``."""
    document_text: str
    domain_hint: Optional[str] = None
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: Optional[str] = None


class RequirementsImportFromCandidateRequest(BaseModel):
    """Body for ``POST /requirements/import-candidate`` (skip LLM)."""
    candidate: dict[str, Any]


class RequirementsImportResponse(BaseModel):
    candidate: dict[str, Any]
    normalized: dict[str, Any]
    review_summary: dict[str, Any]
    review_sidecar: dict[str, Any]
    validation_report: dict[str, Any]
    editor_import_payload: dict[str, Any]


class ConfigSchemaRequest(BaseModel):
    """Body for ``POST /config/schema``."""
    editor_import_payload: dict[str, Any]
    sidecar: Optional[dict[str, Any]] = None
    render_profile: Optional[str] = None


class ConfigSchemaResponse(BaseModel):
    wrapper_schema: dict[str, Any]
    field_groups: dict[str, Any]
    editor_hints: dict[str, Any]


class PatchPreviewRequest(BaseModel):
    """Body for ``POST /config/patch/preview``."""
    wrapper_schema: dict[str, Any]
    current_config: dict[str, Any]
    change_request: str
    patch: Optional[dict[str, Any]] = None
    context: Optional[dict[str, Any]] = None


class PatchApplyRequest(BaseModel):
    """Body for ``POST /config/patch/apply``."""
    current_config: dict[str, Any]
    patch: dict[str, Any]
    wrapper_schema: dict[str, Any]


# ===================================================================
# 1. Requirements import endpoints
# ===================================================================

@router.post("/requirements/import", response_model=RequirementsImportResponse)
async def import_requirements(req: RequirementsImportRequest):
    """Full LLM-based requirements import.

    Pipeline: document → LLM extraction → normalize → validate →
    compile DomainModel → review + sidecar → WME JSON payload.
    """
    try:
        result = requirements_to_buml(
            document_text=req.document_text,
            provider=req.provider,
            model=req.model,
            api_key=req.api_key,
            domain_hint=req.domain_hint,
        )
        return _build_import_response(result)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Requirements import failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/requirements/import-candidate", response_model=RequirementsImportResponse)
async def import_from_candidate(req: RequirementsImportFromCandidateRequest):
    """Import from a pre-built candidate JSON (skip LLM).

    Useful for testing, replay, and manual editing of candidate models.
    """
    try:
        result = requirements_to_buml(
            document_text="(skipped)",
            skip_llm=True,
            candidate_json=req.candidate,
        )
        return _build_import_response(result)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Candidate import failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


@router.post("/requirements/import-file", response_model=RequirementsImportResponse)
async def import_requirements_file(
    file: UploadFile = File(...),
    domain_hint: str = Form(default=""),
    provider: str = Form(default="openai"),
    model: str = Form(default="gpt-4o"),
    api_key: str = Form(default=""),
):
    """Upload a requirements document file and import."""
    try:
        content = await file.read()
        document_text = content.decode("utf-8")

        result = requirements_to_buml(
            document_text=document_text,
            provider=provider,
            model=model,
            api_key=api_key or None,
            domain_hint=domain_hint or None,
        )
        return _build_import_response(result)

    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("File import failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")


# ===================================================================
# 2. Config schema endpoints (Stage 2)
# ===================================================================

@router.post("/config/schema", response_model=ConfigSchemaResponse)
async def generate_config_schema(req: ConfigSchemaRequest):
    """Generate wrapper schema, field groups, and editor hints.

    Input: the ``editor_import_payload`` (WME JSON from requirements
    import) which is re-parsed into a ``DomainModel``.
    """
    try:
        from besser.utilities.web_modeling_editor.backend.services.converters.json_to_buml.class_diagram_processor import (
            process_class_diagram,
        )

        # Re-hydrate DomainModel from WME JSON
        dm = process_class_diagram({
            "title": req.editor_import_payload.get("title", "imported"),
            "model": {
                "elements": req.editor_import_payload.get("elements", {}),
                "relationships": req.editor_import_payload.get("relationships", {}),
            },
        })

        # Build projections
        wrapper_schema = build_wrapper_schema(dm)
        field_groups = build_field_groups(dm)
        editor_hints = build_editor_hints(dm)

        # Merge sidecar if provided
        if req.sidecar:
            sidecar = ReviewSidecar.model_validate(req.sidecar)
            wrapper_schema = merge_sidecar_into_schema(wrapper_schema, sidecar)
            editor_hints = merge_sidecar_into_hints(editor_hints, sidecar)

        return ConfigSchemaResponse(
            wrapper_schema=wrapper_schema,
            field_groups=field_groups,
            editor_hints=editor_hints,
        )

    except Exception as e:
        logger.error("Config schema generation failed: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Schema generation failed: {e}")


@router.post("/config/schema/from-model")
async def generate_config_schema_from_model(input_data: dict[str, Any]):
    """Generate projections directly from a confirmed class diagram model.

    Body: ``{ "title": str, "model": { "elements": {}, "relationships": {} } }``
    """
    try:
        from besser.utilities.web_modeling_editor.backend.services.converters.json_to_buml.class_diagram_processor import (
            process_class_diagram,
        )

        dm = process_class_diagram(input_data)
        wrapper_schema = build_wrapper_schema(dm)
        field_groups = build_field_groups(dm)
        editor_hints = build_editor_hints(dm)

        return {
            "wrapper_schema": wrapper_schema,
            "field_groups": field_groups,
            "editor_hints": editor_hints,
        }

    except Exception as e:
        logger.error("Schema from model failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ===================================================================
# 3. Patch endpoints (Stage 3)
# ===================================================================

@router.post("/config/patch/preview")
async def patch_preview(req: PatchPreviewRequest):
    """Preview a structured patch: validate operations against the
    wrapper schema and return affected fields + warnings."""
    from besser.utilities.config_projection.patch_engine import (
        parse_patch, validate_patch,
    )
    operations = parse_patch(req.patch if isinstance(req.patch, dict) else {"operations": []})

    # If change_request is a natural-language string and no operations
    # are provided, return a hint that LLM integration is pending.
    if not operations and req.change_request:
        return {
            "patch": {"operations": [], "metadata": {"source": "chat", "schemaVersion": "v1"}},
            "affected_fields": [],
            "warnings": [
                "Natural-language patch generation requires LLM integration "
                "(not yet wired). Please provide structured operations."
            ],
            "validation_summary": {"is_valid": True, "errors": [], "warnings": []},
        }

    validation = validate_patch(operations, req.wrapper_schema, req.current_config)
    return {
        "patch": req.patch if isinstance(req.patch, dict) else {"operations": []},
        "affected_fields": validation["affected_fields"],
        "warnings": validation["warnings"],
        "validation_summary": {
            "is_valid": validation["is_valid"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
    }


@router.post("/config/patch/apply")
async def patch_apply(req: PatchApplyRequest):
    """Apply a structured patch to a configuration instance."""
    from besser.utilities.config_projection.patch_engine import (
        parse_patch, validate_patch, apply_patch,
    )
    operations = parse_patch(req.patch)
    validation = validate_patch(operations, req.wrapper_schema, req.current_config)

    if not validation["is_valid"]:
        return {
            "updated_config": req.current_config,
            "diff": [],
            "conflicts": [],
            "validation_errors": validation["errors"],
        }

    updated, diff = apply_patch(req.current_config, operations)
    return {
        "updated_config": updated,
        "diff": diff,
        "conflicts": [],
        "validation_errors": [],
    }


# ===================================================================
# 4. Simulation endpoint (Stage 3)
# ===================================================================

class SimulateRequest(BaseModel):
    sample_event: dict[str, Any]
    config: dict[str, Any]
    wrapper_schema: Optional[dict[str, Any]] = None


@router.post("/bots/simulate")
async def simulate_bot(req: SimulateRequest):
    """Simulate a sample event against a bot configuration."""
    from besser.utilities.config_projection.simulate import simulate_event
    return simulate_event(req.sample_event, req.config, req.wrapper_schema)


@router.post("/events/preview-match")
async def preview_event_match(req: SimulateRequest):
    """Preview which triggers and rules a sample event would match."""
    from besser.utilities.config_projection.simulate import simulate_event
    return simulate_event(req.sample_event, req.config, req.wrapper_schema)


# ===================================================================
# 5. Export / Import endpoints (Stage 4)
# ===================================================================

class ExportRequest(BaseModel):
    config: dict[str, Any]
    project_name: str = ""
    model_version: str = "1.0.0"
    sidecar: Optional[dict[str, Any]] = None
    wrapper_schema: Optional[dict[str, Any]] = None


class ImportValidateRequest(BaseModel):
    bundle: dict[str, Any]
    target_config: Optional[dict[str, Any]] = None
    target_schema: Optional[dict[str, Any]] = None


@router.post("/projects/export-config")
async def export_config(req: ExportRequest):
    """Export an M1 project configuration as a portable bundle."""
    from besser.utilities.bot_project_export import export_project
    try:
        bundle = export_project(
            config=req.config,
            project_name=req.project_name,
            model_version=req.model_version,
            sidecar=req.sidecar,
            wrapper_schema=req.wrapper_schema,
        )
        return bundle
    except Exception as e:
        logger.error("Export failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.post("/projects/import-config/validate")
async def validate_import_config(req: ImportValidateRequest):
    """Validate an export bundle before importing."""
    from besser.utilities.bot_project_export import validate_import
    try:
        report = validate_import(
            bundle=req.bundle,
            target_config=req.target_config,
            target_schema=req.target_schema,
        )
        return report
    except Exception as e:
        logger.error("Import validation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Validation failed: {e}")


# ===================================================================
# Internal helpers
# ===================================================================

def _build_import_response(result: dict) -> RequirementsImportResponse:
    """Convert the ``requirements_to_buml()`` output dict into the API response."""
    domain_model = result["domain_model"]

    # Generate WME-compatible JSON (editor_import_payload)
    editor_payload = class_buml_to_json(domain_model)

    return RequirementsImportResponse(
        candidate=result["candidate"].model_dump(),
        normalized=result["normalized"].model_dump(),
        review_summary=result["review_summary"].model_dump(),
        review_sidecar=result["review_sidecar"].model_dump(),
        validation_report=result["validation_report"].model_dump(),
        editor_import_payload=editor_payload,
    )
