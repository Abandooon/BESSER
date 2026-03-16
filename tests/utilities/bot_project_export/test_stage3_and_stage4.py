"""
Tests for Stage 3 (patch engine, simulation) and Stage 4 (export/import).

Run:
    pytest tests/utilities/bot_project_export/ -v
"""

import pytest
from typing import Any

from besser.utilities.config_projection.patch_engine import (
    PatchOperation, parse_patch, validate_patch, apply_patch,
)
from besser.utilities.config_projection.simulate import simulate_event
from besser.utilities.bot_project_export.redaction import redact_config
from besser.utilities.bot_project_export.exporter import export_project
from besser.utilities.bot_project_export.compatibility import check_compatibility
from besser.utilities.bot_project_export.importer import validate_import


# ===================================================================
# Test data
# ===================================================================

def _sample_config() -> dict[str, Any]:
    """A minimal M1 config for testing."""
    return {
        "AutomationProject": [{
            "project_id": "proj-1",
            "name": "OSS Bot Project",
            "version": "1.0.0",
            "status": "active",
        }],
        "Environment": [{
            "environment_id": "env-1",
            "name": "production",
            "environment_type": "PRODUCTION",
            "api_base_url": "https://api.github.com",
            "credential_ref": "${github_token_ref}",
        }],
        "PlatformConnector": [{
            "connector_id": "conn-1",
            "name": "GitHub Main",
            "connector_type": "GITHUB_APP",
            "platform_type": "GITHUB",
            "token_ref": "ghp_REAL_SECRET_12345",  # ← should be redacted
        }],
        "CommunityOrganization": [],
        "Repository": [],
        "BotTemplate": [{
            "template_id": "tmpl-1",
            "name": "Welcome Bot",
            "category": "greeting",
            "risk_level": "LOW",
        }],
        "BotInstance": [{
            "instance_id": "inst-1",
            "name": "Welcome Bot Prod",
            "priority": 10,
            "is_enabled": True,
            "template_id": "tmpl-1",
        }],
        "EventTrigger": [{
            "trigger_id": "trig-1",
            "name": "New PR Trigger",
            "event_type": "PR_CREATED",
            "is_enabled": True,
        }, {
            "trigger_id": "trig-2",
            "name": "Issue Created",
            "event_type": "ISSUE_CREATED",
            "is_enabled": True,
            "filter_expression": "label:bug",
        }],
        "Rule": [{
            "rule_id": "rule-1",
            "name": "Welcome new contributor",
            "priority": 10,
            "is_enabled": True,
            "trigger_id": "trig-1",
        }],
        "Action": [{
            "action_id": "act-1",
            "name": "Post welcome comment",
            "action_type": "POST_COMMENT",
            "requires_approval": False,
            "execution_order": 1,
            "rule_id": "rule-1",
        }, {
            "action_id": "act-2",
            "name": "Close stale issue",
            "action_type": "CLOSE_ISSUE",
            "requires_approval": True,
            "execution_order": 2,
            "rule_id": "rule-1",
        }],
        "MessageTemplate": [],
        "NotificationTarget": [],
        "ApprovalPolicy": [],
        "ScheduleTask": [],
    }


def _sample_schema() -> dict[str, Any]:
    """A minimal wrapper schema for patch validation."""
    return {
        "$defs": {
            "BotInstance": {
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string", "x-is-id": True},
                    "priority": {"type": "integer"},
                    "is_enabled": {"type": "boolean"},
                    "token_ref": {"type": "string", "readOnly": True},
                },
            },
            "Action": {
                "type": "object",
                "properties": {
                    "action_id": {"type": "string", "x-is-id": True},
                    "requires_approval": {"type": "boolean"},
                },
            },
        },
    }


# ===================================================================
# 1. Patch engine tests
# ===================================================================

class TestPatchEngine:

    def test_parse_patch(self):
        raw = {"operations": [
            {"op": "replace", "path": "/BotInstance/0/priority", "value": 20, "reason": "Increase priority"},
        ]}
        ops = parse_patch(raw)
        assert len(ops) == 1
        assert ops[0].op == "replace"
        assert ops[0].path == "/BotInstance/0/priority"
        assert ops[0].value == 20

    def test_apply_replace(self):
        config = {"BotInstance": [{"priority": 10}]}
        ops = [PatchOperation("replace", "/BotInstance/0/priority", 20)]
        updated, diff = apply_patch(config, ops)
        assert updated["BotInstance"][0]["priority"] == 20
        assert diff[0]["old_value"] == 10
        assert diff[0]["new_value"] == 20
        # Original is unchanged
        assert config["BotInstance"][0]["priority"] == 10

    def test_apply_add(self):
        config = {"BotInstance": [{"priority": 10}]}
        ops = [PatchOperation("add", "/BotInstance/0/description", "New field")]
        updated, _ = apply_patch(config, ops)
        assert updated["BotInstance"][0]["description"] == "New field"

    def test_apply_remove(self):
        config = {"BotInstance": [{"priority": 10, "extra": "remove_me"}]}
        ops = [PatchOperation("remove", "/BotInstance/0/extra")]
        updated, _ = apply_patch(config, ops)
        assert "extra" not in updated["BotInstance"][0]

    def test_validate_rejects_secret_write(self):
        ops = [PatchOperation("replace", "/PlatformConnector/0/token_ref", "plain_secret")]
        result = validate_patch(ops, _sample_schema(), {})
        assert len(result["errors"]) > 0
        assert "secret" in result["errors"][0].lower() or "sensitive" in result["errors"][0].lower()

    def test_validate_warns_on_read_only(self):
        ops = [PatchOperation("replace", "/BotInstance/0/token_ref", "new")]
        result = validate_patch(ops, _sample_schema(), {})
        assert any("read-only" in e for e in result["errors"])

    def test_validate_warns_on_approval_field(self):
        ops = [PatchOperation("replace", "/Action/0/requires_approval", True)]
        result = validate_patch(ops, _sample_schema(), {})
        assert any("approval" in w.lower() for w in result["warnings"])

    def test_validate_clean_patch(self):
        ops = [PatchOperation("replace", "/BotInstance/0/priority", 20)]
        result = validate_patch(ops, _sample_schema(), {})
        assert result["is_valid"] is True


# ===================================================================
# 2. Simulation tests
# ===================================================================

class TestSimulation:

    def test_matching_trigger(self):
        config = _sample_config()
        event = {"event_type": "PR_CREATED", "payload": {}}
        result = simulate_event(event, config)
        assert len(result["matched_triggers"]) >= 1
        assert result["matched_triggers"][0]["event_type"] == "PR_CREATED"

    def test_no_matching_trigger(self):
        config = _sample_config()
        event = {"event_type": "RELEASE_CREATED", "payload": {}}
        result = simulate_event(event, config)
        assert len(result["matched_triggers"]) == 0
        assert result["unmatched_reason"] is not None

    def test_filter_expression(self):
        config = _sample_config()
        # Should match trig-2 (ISSUE_CREATED with filter "label:bug")
        event = {"event_type": "ISSUE_CREATED", "payload": {"label": "bug-report"}}
        result = simulate_event(event, config)
        assert len(result["matched_triggers"]) >= 1

    def test_filter_expression_no_match(self):
        config = _sample_config()
        event = {"event_type": "ISSUE_CREATED", "payload": {"label": "feature"}}
        result = simulate_event(event, config)
        # trig-2 filter is "label:bug", "feature" doesn't match
        trigger_names = {t["name"] for t in result["matched_triggers"]}
        assert "Issue Created" not in trigger_names

    def test_action_sequence(self):
        config = _sample_config()
        event = {"event_type": "PR_CREATED", "payload": {}}
        result = simulate_event(event, config)
        assert len(result["action_sequence"]) >= 1

    def test_approval_warning(self):
        config = _sample_config()
        event = {"event_type": "PR_CREATED", "payload": {}}
        result = simulate_event(event, config)
        # act-2 requires approval
        if result["approval_required"]:
            assert any("approval" in w.lower() for w in result["warnings"])


# ===================================================================
# 3. Redaction tests
# ===================================================================

class TestRedaction:

    def test_token_redacted(self):
        config = _sample_config()
        redacted, report = redact_config(config)
        # token_ref in PlatformConnector should be redacted
        conn = redacted["PlatformConnector"][0]
        assert "ghp_REAL_SECRET" not in conn.get("token_ref", "")
        assert "_ref}" in conn.get("token_ref", "")

    def test_credential_ref_preserved(self):
        config = _sample_config()
        redacted, _ = redact_config(config)
        # credential_ref is already a ref-style key — should not be touched
        env = redacted["Environment"][0]
        assert env["credential_ref"] == "${github_token_ref}"

    def test_redaction_report(self):
        config = _sample_config()
        _, report = redact_config(config)
        assert len(report) >= 1
        paths = [r["path"] for r in report]
        assert any("token_ref" in p for p in paths)

    def test_original_untouched(self):
        config = _sample_config()
        original_token = config["PlatformConnector"][0]["token_ref"]
        redact_config(config)
        assert config["PlatformConnector"][0]["token_ref"] == original_token


# ===================================================================
# 4. Exporter tests
# ===================================================================

class TestExporter:

    def test_bundle_structure(self):
        config = _sample_config()
        bundle = export_project(config, project_name="Test")
        assert "automation_project_manifest.json" in bundle
        assert "bot_instances.json" in bundle
        assert "export_metadata.json" in bundle
        assert "compatibility_report.json" in bundle
        assert "infrastructure.json" in bundle

    def test_export_metadata(self):
        config = _sample_config()
        bundle = export_project(config, project_name="Test", model_version="2.0")
        meta = bundle["export_metadata.json"]
        assert meta["project_name"] == "Test"
        assert meta["model_version"] == "2.0"
        assert "exported_at" in meta

    def test_high_risk_items(self):
        config = _sample_config()
        bundle = export_project(config)
        compat = bundle["compatibility_report.json"]
        # CLOSE_ISSUE action should be flagged
        assert len(compat["high_risk_items"]) >= 1
        types = [i["action_type"] for i in compat["high_risk_items"]]
        assert "CLOSE_ISSUE" in types

    def test_sidecar_included_when_provided(self):
        config = _sample_config()
        sidecar = {"entries": [{"owner_class": "X", "field_name": "y"}]}
        bundle = export_project(config, sidecar=sidecar)
        assert "sidecar_notes.json" in bundle

    def test_redaction_in_export(self):
        config = _sample_config()
        bundle = export_project(config)
        infra = bundle["infrastructure.json"]
        conn = infra["platform_connectors"][0]
        assert "ghp_REAL_SECRET" not in str(conn)


# ===================================================================
# 5. Compatibility + Import validation tests
# ===================================================================

class TestCompatibilityAndImport:

    def _bundle(self) -> dict:
        return export_project(_sample_config(), project_name="Test")

    def test_valid_bundle(self):
        bundle = self._bundle()
        report = validate_import(bundle)
        assert report["is_valid"] is True

    def test_missing_required_file(self):
        bundle = self._bundle()
        del bundle["automation_project_manifest.json"]
        report = validate_import(bundle)
        assert report["is_valid"] is False
        assert any("Missing" in e for e in report["errors"])

    def test_compatibility_platform_warning(self):
        bundle = self._bundle()
        # Target has no GITHUB platform
        target = {"PlatformConnector": [{"platform_type": "GITLAB"}]}
        report = check_compatibility(bundle, target_config=target)
        assert any("GITHUB" in w for w in report["warnings"])

    def test_environment_remap_suggestion(self):
        bundle = self._bundle()
        target = {"Environment": [{"name": "staging"}]}
        report = check_compatibility(bundle, target_config=target)
        assert len(report["environment_remap_suggestions"]) >= 1

    def test_high_risk_confirmations(self):
        bundle = self._bundle()
        report = check_compatibility(bundle)
        assert len(report["high_risk_confirmations"]) >= 1

    def test_no_plain_secrets_in_valid_bundle(self):
        bundle = self._bundle()
        report = validate_import(bundle)
        # After export (which redacts), there should be no secret errors
        secret_errors = [e for e in report["errors"] if "secret" in e.lower() or "plain-text" in e.lower()]
        assert len(secret_errors) == 0

    def test_plain_secret_detected_in_raw_bundle(self):
        """If someone tampers with a bundle and puts back a plain secret."""
        bundle = self._bundle()
        # Inject a plain secret into infrastructure
        bundle["infrastructure.json"]["platform_connectors"][0]["token_ref"] = "ghp_LEAKED"
        report = validate_import(bundle)
        secret_errors = [e for e in report["errors"] if "plain-text" in e.lower() or "secret" in e.lower()]
        assert len(secret_errors) >= 1


# ===================================================================
# 6. API endpoint tests (Stage 3+4)
# ===================================================================

class TestStage3And4API:

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        from besser.utilities.web_modeling_editor.backend.api.editor_workflow_api import router
        test_app = FastAPI()
        test_app.include_router(router)
        return test_app

    @pytest.mark.anyio
    async def test_patch_apply_via_api(self, app):
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/besser_api/config/patch/apply", json={
                "current_config": {"BotInstance": [{"priority": 10}]},
                "patch": {"operations": [
                    {"op": "replace", "path": "/BotInstance/0/priority", "value": 20},
                ]},
                "wrapper_schema": _sample_schema(),
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_config"]["BotInstance"][0]["priority"] == 20
        assert len(body["diff"]) == 1

    @pytest.mark.anyio
    async def test_simulate_via_api(self, app):
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/besser_api/bots/simulate", json={
                "sample_event": {"event_type": "PR_CREATED", "payload": {}},
                "config": _sample_config(),
            })
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["matched_triggers"]) >= 1

    @pytest.mark.anyio
    async def test_export_via_api(self, app):
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/besser_api/projects/export-config", json={
                "config": _sample_config(),
                "project_name": "API Test",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert "automation_project_manifest.json" in body
        assert "export_metadata.json" in body

    @pytest.mark.anyio
    async def test_import_validate_via_api(self, app):
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # First export
            export_resp = await client.post("/besser_api/projects/export-config", json={
                "config": _sample_config(),
            })
            bundle = export_resp.json()

            # Then validate import
            resp = await client.post("/besser_api/projects/import-config/validate", json={
                "bundle": bundle,
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_valid"] is True
