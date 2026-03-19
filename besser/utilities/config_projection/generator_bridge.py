"""
Generator bridge — DomainModel → BESSER generators → usable output.

This module wraps BESSER's existing ``PydanticGenerator`` so that other
pipeline stages (wrapper_schema_builder, editor_workflow_api) can obtain
JSON Schema and Pydantic classes **from the same code path** as the
official generators, instead of hand-writing duplicate type mapping.

Chain::

    DomainModel
      → PydanticGenerator.generate()   (writes pydantic_classes.py)
      → dynamic import                 (loads generated BaseModel subclasses)
      → .model_json_schema()           (standard JSON Schema dict)

This is the MDE-correct model transformation: M2 → generator → M2 projection.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import tempfile
from typing import Any

from pydantic import BaseModel

from besser.BUML.metamodel.structural import DomainModel, Class, Enumeration
from besser.generators.pydantic_classes import PydanticGenerator

logger = logging.getLogger(__name__)


def generate_pydantic_models(
    domain_model: DomainModel,
) -> dict[str, type[BaseModel]]:
    """Generate Pydantic model classes from *domain_model* via BESSER's generator.

    Returns a dict ``{class_name: PydanticModelClass}``.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = PydanticGenerator(model=domain_model, output_dir=tmpdir)
        gen.generate()

        fpath = os.path.join(tmpdir, "pydantic_classes.py")
        if not os.path.exists(fpath):
            raise RuntimeError("PydanticGenerator did not produce pydantic_classes.py")

        import re
        raw = open(fpath, encoding="utf-8").read()
        raw = re.sub(r'    @field_validator.*?return v\n', '', raw, flags=re.DOTALL)
        open(fpath, "w", encoding="utf-8").write(raw)

        spec = importlib.util.spec_from_file_location("_gen_pydantic", fpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        models: dict[str, type[BaseModel]] = {}
        for name in dir(mod):
            obj = getattr(mod, name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseModel)
                and obj is not BaseModel
            ):
                models[name] = obj

        # Resolve forward references: rebuild each model with the full
        # namespace of all generated models so cross-references work.
        namespace = dict(models)
        for model_cls in models.values():
            try:
                model_cls.model_rebuild(_types_namespace=namespace)
            except Exception:
                pass  # best-effort; schema generation will catch real failures

        logger.info("Bridge: generated %d Pydantic models from DomainModel", len(models))
        return models


def generate_base_json_schema(
    domain_model: DomainModel,
) -> dict[str, Any]:
    """Generate a unified JSON Schema from *domain_model* via PydanticGenerator.

    Returns a JSON Schema dict with ``$defs`` for every class/enum, and
    top-level ``properties`` mapping each class to an array of instances.

    This schema is the **base** — ``wrapper_schema_builder`` layers
    additional metadata (``x-is-id``, ``readOnly``, field groups, etc.)
    on top.
    """
    models = generate_pydantic_models(domain_model)

    if not models:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": domain_model.name,
            "type": "object",
            "properties": {},
            "$defs": {},
        }

    # Collect per-model schemas and merge $defs.
    # We call model_json_schema() on each model individually (where
    # forward refs are resolved within the generated module) and merge
    # all $defs into a single namespace.
    merged_defs: dict[str, Any] = {}
    top_properties: dict[str, Any] = {}

    for name, model_cls in sorted(models.items()):
        try:
            individual = model_cls.model_json_schema()
        except Exception as exc:
            logger.warning("Skipping %s schema: %s", name, exc)
            continue

        ind_defs = individual.get("$defs", {})

        # When cross-references exist, Pydantic puts the class itself
        # into $defs and the top-level is just a $ref.  When no
        # cross-refs, the class schema IS the top-level.
        if name in ind_defs:
            merged_defs[name] = ind_defs[name]
        else:
            model_schema = {k: v for k, v in individual.items()
                           if k not in ("$defs", "$schema")}
            merged_defs[name] = model_schema

        # Also merge all other $defs (enums, referenced classes)
        for def_name, def_schema in ind_defs.items():
            if def_name not in merged_defs:
                merged_defs[def_name] = def_schema

        # Top-level: each class is an array of instances
        top_properties[name] = {
            "type": "array",
            "items": {"$ref": f"#/$defs/{name}"},
        }

    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": domain_model.name,
        "type": "object",
        "properties": top_properties,
        "$defs": merged_defs,
    }

    logger.info(
        "Bridge: base schema has %d $defs, %d top-level properties",
        len(merged_defs), len(top_properties),
    )
    return schema


def generate_pydantic_file(
    domain_model: DomainModel,
    output_dir: str,
) -> str:
    """Generate ``pydantic_classes.py`` to *output_dir* (passthrough to BESSER).

    Returns the file path.
    """
    gen = PydanticGenerator(model=domain_model, output_dir=output_dir)
    gen.generate()
    return os.path.join(output_dir, "pydantic_classes.py")


def generate_rest_api_file(
    domain_model: DomainModel,
    output_dir: str,
) -> str:
    """Generate REST API code via BESSER's RESTGenerator (if available).

    Returns the output directory path.
    """
    try:
        from besser.generators.rest_api import RESTAPIGenerator
        gen = RESTAPIGenerator(model=domain_model, output_dir=output_dir)
        gen.generate()
        return output_dir
    except ImportError:
        logger.warning("RESTAPIGenerator not available")
        return ""
