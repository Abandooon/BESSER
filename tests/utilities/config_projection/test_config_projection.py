"""
Tests for besser.utilities.config_projection and the editor_workflow_api.

Covers: wrapper_schema_builder, field_group_builder, editor_hints_builder,
sidecar_merger, and the FastAPI /requirements + /config endpoints.

Run:
    pytest tests/utilities/config_projection/ -v
"""

import pytest
from besser.BUML.metamodel.structural import (
    Class, Property, DomainModel, PrimitiveDataType,
    Enumeration, EnumerationLiteral,
    BinaryAssociation, Constraint,
    Multiplicity, UNLIMITED_MAX_MULTIPLICITY,
    StringType, IntegerType, BooleanType, DateTimeType,
)

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
    merge_sidecar_into_hints,
)
from besser.utilities.requirements_to_buml.m3_schema_projector import (
    ReviewSidecar,
    SidecarEntry,
)

@pytest.fixture
def anyio_backend():
    return "asyncio"

# ===================================================================
# Helpers — build a small DomainModel for testing
# ===================================================================

def _build_test_domain_model() -> DomainModel:
    """Build a small DomainModel with 2 classes, 1 enum, 1 association."""
    risk_enum = Enumeration(name="RiskLevel", literals={
        EnumerationLiteral(name="LOW"),
        EnumerationLiteral(name="MEDIUM"),
        EnumerationLiteral(name="HIGH"),
    })

    bot_template = Class(name="BotTemplate")
    bot_template.add_attribute(Property(
        name="template_id", type=StringType, is_id=True))
    bot_template.add_attribute(Property(
        name="name", type=StringType))
    bot_template.add_attribute(Property(
        name="risk_level", type=risk_enum))
    bot_template.add_attribute(Property(
        name="description", type=StringType, is_optional=True))

    bot_instance = Class(name="BotInstance")
    bot_instance.add_attribute(Property(
        name="instance_id", type=StringType, is_id=True))
    bot_instance.add_attribute(Property(
        name="name", type=StringType))
    bot_instance.add_attribute(Property(
        name="priority", type=IntegerType, default_value=10))
    bot_instance.add_attribute(Property(
        name="is_enabled", type=BooleanType, default_value=True))
    bot_instance.add_attribute(Property(
        name="token_ref", type=StringType, is_optional=True))

    end_template = Property(
        name="template", type=bot_template,
        multiplicity=Multiplicity(1, 1), is_navigable=False)
    end_instances = Property(
        name="instances", type=bot_instance,
        multiplicity=Multiplicity(0, UNLIMITED_MAX_MULTIPLICITY), is_navigable=True)
    assoc = BinaryAssociation(
        name="Template_Instances", ends={end_template, end_instances})

    return DomainModel(
        name="TestDomain",
        types={bot_template, bot_instance, risk_enum},
        associations={assoc},
    )



# ===================================================================
# 1. Wrapper Schema Builder tests
# ===================================================================

class TestWrapperSchemaBuilder:

    def test_basic_structure(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)

        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "BotTemplate" in schema["$defs"]
        assert "BotInstance" in schema["$defs"]
        assert "RiskLevel" in schema["$defs"]

    def test_enum_schema(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        risk = schema["$defs"]["RiskLevel"]
        assert risk["type"] == "string"
        assert set(risk["enum"]) == {"LOW", "MEDIUM", "HIGH"}

    def test_class_properties(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        bt = schema["$defs"]["BotTemplate"]
        assert "template_id" in bt["properties"]
        assert "name" in bt["properties"]
        assert "risk_level" in bt["properties"]

    def test_is_id_marker(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        tid = schema["$defs"]["BotTemplate"]["properties"]["template_id"]
        assert tid.get("x-is-id") is True

    def test_optional_nullable(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        desc = schema["$defs"]["BotTemplate"]["properties"]["description"]

        any_of = desc.get("anyOf", [])
        assert any(item.get("type") == "string" for item in any_of)
        assert any(item.get("type") == "null" for item in any_of)

    def test_default_value(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        prio = schema["$defs"]["BotInstance"]["properties"]["priority"]
        assert prio["default"] == 10

    def test_enum_ref(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        rl = schema["$defs"]["BotTemplate"]["properties"]["risk_level"]
        assert "$ref" in rl
        assert "RiskLevel" in rl["$ref"]

    def test_association_end_in_schema(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)

        bt = schema["$defs"]["BotTemplate"]
        assert "instances" in bt["properties"]
        inst_prop = bt["properties"]["instances"]
        assert inst_prop["type"] == "array"

    def test_required_fields(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        bt = schema["$defs"]["BotTemplate"]
        # template_id, name, risk_level are required (not optional, no default)
        assert "template_id" in bt.get("required", [])
        assert "name" in bt.get("required", [])

    def test_root_properties(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        assert "BotTemplate" in schema["properties"]
        assert schema["properties"]["BotTemplate"]["type"] == "array"


# ===================================================================
# 2. Field Group Builder tests
# ===================================================================

class TestFieldGroupBuilder:

    def test_basic_groups(self):
        dm = _build_test_domain_model()
        groups = build_field_groups(dm)
        assert "BotTemplate" in groups
        assert "BotInstance" in groups

    def test_identity_group(self):
        dm = _build_test_domain_model()
        groups = build_field_groups(dm)
        bt_groups = groups["BotTemplate"]
        identity = next((g for g in bt_groups if g["group"] == "Identity"), None)
        assert identity is not None
        assert "template_id" in identity["fields"]

    def test_optional_group(self):
        dm = _build_test_domain_model()
        groups = build_field_groups(dm)
        bt_groups = groups["BotTemplate"]
        optional = next((g for g in bt_groups if g["group"] == "Optional"), None)
        assert optional is not None
        assert "description" in optional["fields"]
        assert optional["collapsed"] is True

    def test_association_group(self):
        dm = _build_test_domain_model()
        groups = build_field_groups(dm)
        bt_groups = groups["BotTemplate"]
        assoc_group = next((g for g in bt_groups if g["group"] == "Associations"), None)
        assert assoc_group is not None
        assert "instances" in assoc_group["fields"]


# ===================================================================
# 3. Editor Hints Builder tests
# ===================================================================

class TestEditorHintsBuilder:

    def test_basic_hints(self):
        dm = _build_test_domain_model()
        hints = build_editor_hints(dm)
        assert "BotTemplate" in hints
        assert "BotInstance" in hints

    def test_enum_widget(self):
        dm = _build_test_domain_model()
        hints = build_editor_hints(dm)
        rl = hints["BotTemplate"]["risk_level"]
        assert rl["widget"] == "select"
        assert set(rl["options"]) == {"LOW", "MEDIUM", "HIGH"}

    def test_bool_widget(self):
        dm = _build_test_domain_model()
        hints = build_editor_hints(dm)
        ie = hints["BotInstance"]["is_enabled"]
        assert ie["widget"] == "toggle"

    def test_id_marker(self):
        dm = _build_test_domain_model()
        hints = build_editor_hints(dm)
        tid = hints["BotTemplate"]["template_id"]
        assert tid.get("isPrimaryKey") is True

    def test_secret_widget(self):
        dm = _build_test_domain_model()
        hints = build_editor_hints(dm)
        token = hints["BotInstance"]["token_ref"]
        assert token["widget"] == "secret"
        assert token["sensitive"] is True

    def test_association_ref_picker(self):
        dm = _build_test_domain_model()
        hints = build_editor_hints(dm)
        inst = hints["BotTemplate"].get("instances")
        assert inst is not None
        assert inst["widget"] == "multi-ref-picker"
        assert inst["referenceTo"] == "BotInstance"


# ===================================================================
# 4. Sidecar Merger tests
# ===================================================================

class TestSidecarMerger:

    def _sidecar(self) -> ReviewSidecar:
        return ReviewSidecar(entries=[
            SidecarEntry(
                owner_class="BotTemplate",
                field_name="configurableFieldSpecs",
                kind="configurable_field_specs",
                payload={"type": "object", "properties": {"threshold": {"type": "integer"}}},
                description="Template-specific config fields",
            ),
            SidecarEntry(
                owner_class="Action",
                field_name="retryPolicy",
                kind="retry_policy",
                payload={"max_retries": 3, "backoff": "exponential"},
                description="Retry configuration",
            ),
        ])

    def test_merge_into_schema(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        sidecar = self._sidecar()

        merged = merge_sidecar_into_schema(schema, sidecar)

        # BotTemplate should have the sidecar property
        bt = merged["$defs"]["BotTemplate"]
        assert "x-sidecar-configurableFieldSpecs" in bt["properties"]
        sc = bt["properties"]["x-sidecar-configurableFieldSpecs"]
        assert sc["x-sidecar"] is True
        assert sc["x-sidecar-kind"] == "configurable_field_specs"

    def test_merge_does_not_mutate_original(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        original_keys = set(schema["$defs"]["BotTemplate"]["properties"].keys())

        sidecar = self._sidecar()
        merge_sidecar_into_schema(schema, sidecar)

        # Original should be untouched
        assert set(schema["$defs"]["BotTemplate"]["properties"].keys()) == original_keys

    def test_merge_into_hints(self):
        dm = _build_test_domain_model()
        hints = build_editor_hints(dm)
        sidecar = self._sidecar()

        merged = merge_sidecar_into_hints(hints, sidecar)
        assert "configurableFieldSpecs" in merged.get("BotTemplate", {})
        spec = merged["BotTemplate"]["configurableFieldSpecs"]
        assert spec["widget"] == "dynamic-fields"
        assert spec["sidecar"] is True

    def test_empty_sidecar_noop(self):
        dm = _build_test_domain_model()
        schema = build_wrapper_schema(dm)
        empty = ReviewSidecar(entries=[])
        result = merge_sidecar_into_schema(schema, empty)
        assert result is schema  # exact same object, no copy



# ===================================================================
# 6. API endpoint tests (using FastAPI TestClient)
# ===================================================================

class TestEditorWorkflowAPI:
    """API tests using httpx.AsyncClient + ASGITransport.

    Works with any httpx >= 0.27 regardless of starlette version.
    """

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        from besser.utilities.web_modeling_editor.backend.api.editor_workflow_api import router
        test_app = FastAPI()
        test_app.include_router(router)
        return test_app

    @pytest.mark.anyio
    async def test_patch_preview_stub(self, app):
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/besser_api/config/patch/preview",
                json={
                    "wrapper_schema": {},
                    "current_config": {},
                    "change_request": "Change priority to 20",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "patch" in body
        assert "warnings" in body

    @pytest.mark.anyio
    async def test_patch_apply_stub(self, app):
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/besser_api/config/patch/apply",
                json={
                    "current_config": {"x": 1},
                    "patch": {"operations": []},
                    "wrapper_schema": {},
                },
            )
        assert resp.status_code == 200
        assert resp.json()["updated_config"] == {"x": 1}
