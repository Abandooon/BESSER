"""
Tests for besser.utilities.requirements_to_buml.

Covers: schemas, normalization, compilation, review, validation,
and the 14-class OSS Bot integration test.

Run:
    pytest tests/utilities/requirements_to_buml/ -v
"""

import pytest

from besser.BUML.metamodel.structural import (
    Class, Property, DomainModel, PrimitiveDataType,
    Enumeration, EnumerationLiteral,
    BinaryAssociation, Constraint,
    Multiplicity, UNLIMITED_MAX_MULTIPLICITY,
    StringType, IntegerType, BooleanType, DateTimeType,
)

from besser.utilities.requirements_to_buml.schemas import (
    CandidateModel,
    CandidateClass,
    CandidateProperty,
    CandidateEnumeration,
    CandidateEnumerationLiteral,
    CandidateAssociation,
    CandidateAssociationEnd,
    CandidateConstraint,
    CandidateUnresolvedItem,
    NormalizedCandidateModel,
    NormalizedClass,
    NormalizedProperty,
    NormalizedEnumeration,
    NormalizedEnumerationLiteral,
    NormalizedAssociation,
    NormalizedAssociationEnd,
    NormalizedConstraint,
    ReviewSummary,
    ReviewSidecar,
    ValidationReport,
)

from besser.utilities.requirements_to_buml.normalization import (
    normalize_candidate,
    _to_pascal_case,
    _to_snake_case,
    _to_upper_case,
)

from besser.utilities.requirements_to_buml.compilation import (
    compile_to_domain_model,
)

from besser.utilities.requirements_to_buml.review import generate_review

from besser.utilities.requirements_to_buml.validation import validate_candidate


# ===================================================================
# Helper: build a minimal candidate for the OSS Bot domain
# ===================================================================

def _build_oss_bot_candidate() -> CandidateModel:
    """Build a CandidateModel with all 14 core classes, 9 enums, 14 assocs."""

    enums = [
        CandidateEnumeration(name="PlatformType", literals=[
            CandidateEnumerationLiteral(name="GITHUB"),
            CandidateEnumerationLiteral(name="GITLAB"),
            CandidateEnumerationLiteral(name="WEBHOOK"),
        ]),
        CandidateEnumeration(name="ConnectorType", literals=[
            CandidateEnumerationLiteral(name="GITHUB_APP"),
            CandidateEnumerationLiteral(name="GITHUB_TOKEN"),
            CandidateEnumerationLiteral(name="GITLAB_TOKEN"),
            CandidateEnumerationLiteral(name="WEBHOOK_IN"),
            CandidateEnumerationLiteral(name="WEBHOOK_OUT"),
            CandidateEnumerationLiteral(name="ENTERPRISE_MSG"),
        ]),
        CandidateEnumeration(name="EventType", literals=[
            CandidateEnumerationLiteral(name="ISSUE_CREATED"),
            CandidateEnumerationLiteral(name="ISSUE_CLOSED"),
            CandidateEnumerationLiteral(name="PR_CREATED"),
            CandidateEnumerationLiteral(name="PR_UPDATED"),
            CandidateEnumerationLiteral(name="COMMENT_CREATED"),
            CandidateEnumerationLiteral(name="REVIEW_SUBMITTED"),
            CandidateEnumerationLiteral(name="RELEASE_CREATED"),
            CandidateEnumerationLiteral(name="SCHEDULE"),
            CandidateEnumerationLiteral(name="EXTERNAL_WEBHOOK"),
        ]),
        CandidateEnumeration(name="ActionType", literals=[
            CandidateEnumerationLiteral(name="ADD_LABEL"),
            CandidateEnumerationLiteral(name="REMOVE_LABEL"),
            CandidateEnumerationLiteral(name="POST_COMMENT"),
            CandidateEnumerationLiteral(name="ASSIGN"),
            CandidateEnumerationLiteral(name="REQUEST_REVIEW"),
            CandidateEnumerationLiteral(name="SEND_NOTIFICATION"),
            CandidateEnumerationLiteral(name="CALL_WEBHOOK"),
            CandidateEnumerationLiteral(name="CREATE_TASK"),
            CandidateEnumerationLiteral(name="CLOSE_ISSUE"),
            CandidateEnumerationLiteral(name="MARK_MANUAL"),
        ]),
        CandidateEnumeration(name="RiskLevel", literals=[
            CandidateEnumerationLiteral(name="LOW"),
            CandidateEnumerationLiteral(name="MEDIUM"),
            CandidateEnumerationLiteral(name="HIGH"),
        ]),
        CandidateEnumeration(name="TargetType", literals=[
            CandidateEnumerationLiteral(name="EMAIL"),
            CandidateEnumerationLiteral(name="SLACK"),
            CandidateEnumerationLiteral(name="TEAMS"),
            CandidateEnumerationLiteral(name="WEBHOOK"),
            CandidateEnumerationLiteral(name="MENTION"),
        ]),
        CandidateEnumeration(name="Visibility", literals=[
            CandidateEnumerationLiteral(name="PUBLIC"),
            CandidateEnumerationLiteral(name="PRIVATE"),
            CandidateEnumerationLiteral(name="INTERNAL"),
        ]),
        CandidateEnumeration(name="RepositoryType", literals=[
            CandidateEnumerationLiteral(name="CODE"),
            CandidateEnumerationLiteral(name="DOCS"),
            CandidateEnumerationLiteral(name="GOVERNANCE"),
        ]),
        CandidateEnumeration(name="EnvironmentType", literals=[
            CandidateEnumerationLiteral(name="DESIGN"),
            CandidateEnumerationLiteral(name="TEST"),
            CandidateEnumerationLiteral(name="PRODUCTION"),
        ]),
    ]

    classes = [
        CandidateClass(name="AutomationProject", attributes=[
            CandidateProperty(name="project_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="description", type="str", is_optional=True),
            CandidateProperty(name="version", type="str", default_value="1.0.0"),
            CandidateProperty(name="status", type="str", default_value="draft"),
            CandidateProperty(name="created_at", type="datetime"),
            CandidateProperty(name="updated_at", type="datetime"),
        ]),
        CandidateClass(name="Environment", attributes=[
            CandidateProperty(name="environment_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="environment_type", type="EnvironmentType"),
            CandidateProperty(name="api_base_url", type="str", is_optional=True),
            CandidateProperty(name="credential_ref", type="str", is_optional=True),
            CandidateProperty(name="is_enabled", type="bool", default_value=True),
        ]),
        CandidateClass(name="PlatformConnector", attributes=[
            CandidateProperty(name="connector_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="connector_type", type="ConnectorType"),
            CandidateProperty(name="platform_type", type="PlatformType"),
            CandidateProperty(name="api_base_url", type="str", is_optional=True),
            CandidateProperty(name="token_ref", type="str", is_optional=True),
            CandidateProperty(name="is_enabled", type="bool", default_value=True),
        ]),
        CandidateClass(name="CommunityOrganization", attributes=[
            CandidateProperty(name="org_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="platform_type", type="PlatformType"),
            CandidateProperty(name="external_id", type="str"),
        ]),
        CandidateClass(name="Repository", attributes=[
            CandidateProperty(name="repo_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="full_name", type="str"),
            CandidateProperty(name="default_branch", type="str", default_value="main"),
            CandidateProperty(name="visibility", type="Visibility"),
            CandidateProperty(name="repo_type", type="RepositoryType"),
            CandidateProperty(name="status", type="str", default_value="active"),
        ]),
        CandidateClass(name="BotTemplate", attributes=[
            CandidateProperty(name="template_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="category", type="str"),
            CandidateProperty(name="risk_level", type="RiskLevel"),
            CandidateProperty(name="description", type="str", is_optional=True),
        ], extensions={
            "configurableFieldSpecs": {"type": "object", "description": "Schema for template-specific config fields"},
            "defaultTriggerEvents": ["ISSUE_CREATED", "PR_CREATED"],
        }),
        CandidateClass(name="BotInstance", attributes=[
            CandidateProperty(name="instance_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="priority", type="int", default_value=10),
            CandidateProperty(name="is_enabled", type="bool", default_value=True),
        ]),
        CandidateClass(name="EventTrigger", attributes=[
            CandidateProperty(name="trigger_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="event_type", type="EventType"),
            CandidateProperty(name="filter_expression", type="str", is_optional=True),
            CandidateProperty(name="is_enabled", type="bool", default_value=True),
        ]),
        CandidateClass(name="Rule", attributes=[
            CandidateProperty(name="rule_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="condition_expression", type="str", is_optional=True),
            CandidateProperty(name="priority", type="int", default_value=10),
            CandidateProperty(name="is_enabled", type="bool", default_value=True),
        ]),
        CandidateClass(name="Action", attributes=[
            CandidateProperty(name="action_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="action_type", type="ActionType"),
            CandidateProperty(name="requires_approval", type="bool", default_value=False),
            CandidateProperty(name="execution_order", type="int", default_value=1),
        ], extensions={
            "parameterSchemaRef": {"type": "object"},
            "retryPolicy": {"max_retries": 3, "backoff": "exponential"},
            "rollbackHint": "Revert label changes if downstream fails",
        }),
        CandidateClass(name="MessageTemplate", attributes=[
            CandidateProperty(name="template_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="language", type="str", default_value="en"),
            CandidateProperty(name="title_template", type="str"),
            CandidateProperty(name="body_template", type="str"),
        ]),
        CandidateClass(name="NotificationTarget", attributes=[
            CandidateProperty(name="target_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="target_type", type="TargetType"),
            CandidateProperty(name="address", type="str"),
            CandidateProperty(name="is_enabled", type="bool", default_value=True),
        ]),
        CandidateClass(name="ApprovalPolicy", attributes=[
            CandidateProperty(name="policy_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="risk_level", type="RiskLevel"),
            CandidateProperty(name="approver_group", type="str"),
            CandidateProperty(name="timeout_hours", type="int", default_value=24),
        ]),
        CandidateClass(name="ScheduleTask", attributes=[
            CandidateProperty(name="task_id", type="str", is_id=True),
            CandidateProperty(name="name", type="str"),
            CandidateProperty(name="cron_expression", type="str"),
            CandidateProperty(name="timezone", type="str", default_value="UTC"),
            CandidateProperty(name="is_enabled", type="bool", default_value=True),
        ]),
    ]

    associations = [
        CandidateAssociation(name="Project_Environments",
            end1=CandidateAssociationEnd(role="project", type="AutomationProject", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="environments", type="Environment", multiplicity="1..*")),
        CandidateAssociation(name="Project_Connectors",
            end1=CandidateAssociationEnd(role="project", type="AutomationProject", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="connectors", type="PlatformConnector", multiplicity="0..*")),
        CandidateAssociation(name="Project_Organizations",
            end1=CandidateAssociationEnd(role="project", type="AutomationProject", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="organizations", type="CommunityOrganization", multiplicity="0..*")),
        CandidateAssociation(name="Organization_Repositories",
            end1=CandidateAssociationEnd(role="organization", type="CommunityOrganization", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="repositories", type="Repository", multiplicity="0..*")),
        CandidateAssociation(name="Project_BotTemplates",
            end1=CandidateAssociationEnd(role="project", type="AutomationProject", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="bot_templates", type="BotTemplate", multiplicity="0..*")),
        CandidateAssociation(name="Template_Instances",
            end1=CandidateAssociationEnd(role="template", type="BotTemplate", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="instances", type="BotInstance", multiplicity="0..*")),
        CandidateAssociation(name="Instance_Repositories",
            end1=CandidateAssociationEnd(role="bot_instance", type="BotInstance", multiplicity="0..*"),
            end2=CandidateAssociationEnd(role="repositories", type="Repository", multiplicity="1..*")),
        CandidateAssociation(name="Instance_Rules",
            end1=CandidateAssociationEnd(role="bot_instance", type="BotInstance", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="rules", type="Rule", multiplicity="1..*")),
        CandidateAssociation(name="Rule_Trigger",
            end1=CandidateAssociationEnd(role="rule", type="Rule", multiplicity="0..*"),
            end2=CandidateAssociationEnd(role="trigger", type="EventTrigger", multiplicity="1..1")),
        CandidateAssociation(name="Rule_Actions",
            end1=CandidateAssociationEnd(role="rule", type="Rule", multiplicity="1..1"),
            end2=CandidateAssociationEnd(role="actions", type="Action", multiplicity="1..*")),
        CandidateAssociation(name="Action_MessageTemplate",
            end1=CandidateAssociationEnd(role="action", type="Action", multiplicity="0..*"),
            end2=CandidateAssociationEnd(role="message_template", type="MessageTemplate", multiplicity="0..1")),
        CandidateAssociation(name="Action_NotificationTarget",
            end1=CandidateAssociationEnd(role="action", type="Action", multiplicity="0..*"),
            end2=CandidateAssociationEnd(role="notification_target", type="NotificationTarget", multiplicity="0..1")),
        CandidateAssociation(name="Action_ApprovalPolicy",
            end1=CandidateAssociationEnd(role="action", type="Action", multiplicity="0..*"),
            end2=CandidateAssociationEnd(role="approval_policy", type="ApprovalPolicy", multiplicity="0..1")),
        CandidateAssociation(name="Schedule_BotInstance",
            end1=CandidateAssociationEnd(role="schedule_tasks", type="ScheduleTask", multiplicity="0..*"),
            end2=CandidateAssociationEnd(role="bot_instance", type="BotInstance", multiplicity="1..1")),
    ]

    constraints = [
        CandidateConstraint(
            name="high_risk_needs_approval",
            context="Action",
            expression="self.requires_approval = true implies self.approval_policy->notEmpty()",
            language="OCL",
        ),
        CandidateConstraint(
            name="instance_needs_repo",
            context="BotInstance",
            expression="self.repositories->size() >= 1",
            language="OCL",
        ),
    ]

    return CandidateModel(
        domain_name="OssBotAutomation",
        classes=classes,
        enumerations=enums,
        associations=associations,
        constraints=constraints,
    )


# ===================================================================
# 1. Schema tests
# ===================================================================

class TestSchemas:

    def test_candidate_model_minimal(self):
        m = CandidateModel(domain_name="Test")
        assert m.domain_name == "Test"
        assert m.classes == []

    def test_candidate_model_full(self):
        m = _build_oss_bot_candidate()
        assert len(m.classes) == 14
        assert len(m.enumerations) == 9
        assert len(m.associations) == 14
        assert len(m.constraints) == 2

    def test_candidate_model_json_roundtrip(self):
        m = _build_oss_bot_candidate()
        json_str = m.model_dump_json()
        m2 = CandidateModel.model_validate_json(json_str)
        assert len(m2.classes) == 14

    def test_extensions_preserved(self):
        cls = CandidateClass(name="X", extensions={"foo": {"bar": 1}})
        assert cls.extensions["foo"]["bar"] == 1


# ===================================================================
# 2. Normalization tests
# ===================================================================

class TestNormalization:

    def test_pascal_case(self):
        assert _to_pascal_case("automation_project") == "AutomationProject"
        assert _to_pascal_case("AutomationProject") == "AutomationProject"
        assert _to_pascal_case("botInstance") == "BotInstance"

    def test_snake_case(self):
        assert _to_snake_case("projectId") == "project_id"
        assert _to_snake_case("project_id") == "project_id"
        assert _to_snake_case("APIBaseURL") == "api_base_url"  # consecutive caps handled well

    def test_upper_case(self):
        assert _to_upper_case("github") == "GITHUB"
        assert _to_upper_case("GITHUB") == "GITHUB"
        assert _to_upper_case("issueCreated") == "ISSUE_CREATED"

    def test_normalize_14_classes(self):
        candidate = _build_oss_bot_candidate()
        normalized = normalize_candidate(candidate)
        assert len(normalized.classes) == 14
        assert len(normalized.enumerations) == 9
        assert len(normalized.associations) == 14
        class_names = {c.name for c in normalized.classes}
        assert "AutomationProject" in class_names
        assert "BotTemplate" in class_names
        assert "ScheduleTask" in class_names

    def test_sidecar_extraction(self):
        candidate = _build_oss_bot_candidate()
        normalized = normalize_candidate(candidate)
        # BotTemplate and Action both have extensions that should go to sidecar
        assert len(normalized.sidecar_items) > 0
        sidecar_owners = {item["owner_class"] for item in normalized.sidecar_items}
        assert "BotTemplate" in sidecar_owners
        assert "Action" in sidecar_owners

    def test_type_alias_resolution(self):
        candidate = CandidateModel(
            domain_name="Test",
            classes=[CandidateClass(name="Foo", attributes=[
                CandidateProperty(name="count", type="integer"),
                CandidateProperty(name="label", type="string"),
                CandidateProperty(name="flag", type="boolean"),
            ])],
        )
        normalized = normalize_candidate(candidate)
        types = {a.type for a in normalized.classes[0].attributes}
        assert types == {"int", "str", "bool"}

    def test_multiplicity_normalization(self):
        candidate = CandidateModel(
            domain_name="Test",
            classes=[CandidateClass(name="Foo", attributes=[
                CandidateProperty(name="a", type="str", multiplicity="*"),
                CandidateProperty(name="b", type="str", multiplicity="1"),
                CandidateProperty(name="c", type="str", multiplicity=""),
            ])],
        )
        normalized = normalize_candidate(candidate)
        attrs = {a.name: a.multiplicity for a in normalized.classes[0].attributes}
        assert attrs["a"] == "0..*"
        assert attrs["b"] == "1..1"
        assert attrs["c"] == "1..1"


# ===================================================================
# 3. Compilation tests
# ===================================================================

class TestCompilation:

    def test_compile_single_class(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo", attributes=[
                NormalizedProperty(name="foo_id", type="str", is_id=True),
                NormalizedProperty(name="name", type="str"),
            ])],
        )
        dm = compile_to_domain_model(normalized)
        assert isinstance(dm, DomainModel)
        cls = dm.get_class_by_name("Foo")
        assert cls is not None
        attrs = {a.name: a for a in cls.attributes}
        assert attrs["foo_id"].is_id is True
        assert attrs["name"].is_id is False

    def test_compile_with_enum(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo", attributes=[
                NormalizedProperty(name="status", type="Status"),
            ])],
            enumerations=[NormalizedEnumeration(name="Status", literals=[
                NormalizedEnumerationLiteral(name="ACTIVE"),
                NormalizedEnumerationLiteral(name="INACTIVE"),
            ])],
        )
        dm = compile_to_domain_model(normalized)
        cls = dm.get_class_by_name("Foo")
        attr = next(a for a in cls.attributes if a.name == "status")
        assert isinstance(attr.type, Enumeration)
        assert attr.type.name == "Status"

    def test_compile_with_association(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[
                NormalizedClass(name="A"),
                NormalizedClass(name="B"),
            ],
            associations=[NormalizedAssociation(
                name="A_B",
                end1=NormalizedAssociationEnd(role="a", type="A", multiplicity="1..1"),
                end2=NormalizedAssociationEnd(role="bs", type="B", multiplicity="0..*"),
            )],
        )
        dm = compile_to_domain_model(normalized)
        assert len(dm.associations) == 1
        assoc = next(iter(dm.associations))
        ends = {e.name: e for e in assoc.ends}
        assert ends["bs"].multiplicity.max == UNLIMITED_MAX_MULTIPLICITY

    def test_compile_with_constraint(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo")],
            constraints=[NormalizedConstraint(
                name="c1", context="Foo",
                expression="self.x > 0", language="OCL",
            )],
        )
        dm = compile_to_domain_model(normalized)
        assert len(dm.constraints) == 1

    def test_compile_14_class_model(self):
        candidate = _build_oss_bot_candidate()
        normalized = normalize_candidate(candidate)
        dm = compile_to_domain_model(normalized)

        # Verify class count (14 domain classes + 9 enums + primitives)
        domain_classes = [t for t in dm.types if isinstance(t, Class)]
        domain_enums = [t for t in dm.types if isinstance(t, Enumeration)]
        assert len(domain_classes) == 14
        assert len(domain_enums) == 9
        assert len(dm.associations) == 14
        assert len(dm.constraints) == 2

    def test_compile_attribute_multiplicity(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo", attributes=[
                NormalizedProperty(name="tags", type="str", multiplicity="0..*"),
            ])],
        )
        dm = compile_to_domain_model(normalized)
        cls = dm.get_class_by_name("Foo")
        attr = next(a for a in cls.attributes if a.name == "tags")
        assert attr.multiplicity.min == 0
        assert attr.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY

    def test_compile_property_fields_preserved(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo", attributes=[
                NormalizedProperty(
                    name="pk", type="str",
                    is_id=True, is_read_only=True,
                    is_optional=False, default_value="auto",
                ),
            ])],
        )
        dm = compile_to_domain_model(normalized)
        attr = next(a for a in dm.get_class_by_name("Foo").attributes)
        assert attr.is_id is True
        assert attr.is_read_only is True
        assert attr.is_optional is False
        assert attr.default_value == "auto"

    def test_compile_skips_unknown_association_end(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="A")],
            associations=[NormalizedAssociation(
                name="A_Missing",
                end1=NormalizedAssociationEnd(role="a", type="A"),
                end2=NormalizedAssociationEnd(role="missing", type="DoesNotExist"),
            )],
        )
        dm = compile_to_domain_model(normalized)
        assert len(dm.associations) == 0  # skipped gracefully


# ===================================================================
# 4. Validation tests
# ===================================================================

class TestValidation:

    def test_valid_model(self):
        candidate = _build_oss_bot_candidate()
        normalized = normalize_candidate(candidate)
        report = validate_candidate(normalized)
        assert report.is_valid is True

    def test_duplicate_class_name(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[
                NormalizedClass(name="Foo"),
                NormalizedClass(name="Foo"),
            ],
        )
        report = validate_candidate(normalized)
        assert report.is_valid is False
        assert any("Duplicate" in i.message for i in report.issues)

    def test_unresolved_attribute_type(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo", attributes=[
                NormalizedProperty(name="bar", type="NoSuchType"),
            ])],
        )
        report = validate_candidate(normalized)
        assert report.is_valid is False
        assert any("NoSuchType" in i.message for i in report.issues)

    def test_broken_association_ref(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="A")],
            associations=[NormalizedAssociation(
                name="A_X",
                end1=NormalizedAssociationEnd(role="a", type="A"),
                end2=NormalizedAssociationEnd(role="x", type="X"),
            )],
        )
        report = validate_candidate(normalized)
        assert report.is_valid is False

    def test_multiple_is_id_error(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo", attributes=[
                NormalizedProperty(name="id1", type="str", is_id=True),
                NormalizedProperty(name="id2", type="str", is_id=True),
            ])],
        )
        report = validate_candidate(normalized)
        assert report.is_valid is False

    def test_class_enum_namespace_collision(self):
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="Foo")],
            enumerations=[NormalizedEnumeration(name="Foo", literals=[
                NormalizedEnumerationLiteral(name="A"),
            ])],
        )
        report = validate_candidate(normalized)
        assert report.is_valid is False


# ===================================================================
# 5. Review tests
# ===================================================================

class TestReview:

    def test_review_14_class(self):
        candidate = _build_oss_bot_candidate()
        normalized = normalize_candidate(candidate)
        dm = compile_to_domain_model(normalized)
        summary, sidecar = generate_review(normalized, dm)

        assert len(summary.class_names) == 14
        assert len(summary.enumeration_names) == 9
        assert len(summary.association_names) == 14
        assert summary.sidecar_item_count > 0
        assert len(summary.high_priority_checks) > 0
        assert len(summary.round_trip_risks) > 0

    def test_sidecar_entries(self):
        candidate = _build_oss_bot_candidate()
        normalized = normalize_candidate(candidate)
        dm = compile_to_domain_model(normalized)
        _, sidecar = generate_review(normalized, dm)

        assert len(sidecar.entries) > 0
        kinds = {e.kind for e in sidecar.entries}
        assert "configurable_field_specs" in kinds or "retry_policy" in kinds

    def test_missing_class_warning(self):
        """If BotTemplate is missing, review should warn."""
        normalized = NormalizedCandidateModel(
            domain_name="Test",
            classes=[NormalizedClass(name="BotInstance")],
        )
        dm = compile_to_domain_model(normalized)
        summary, _ = generate_review(normalized, dm)
        warning_msgs = [w.message for w in summary.warnings]
        assert any("BotTemplate" in m for m in warning_msgs)


# ===================================================================
# 6. End-to-end integration test (14-class OSS Bot)
# ===================================================================

class TestEndToEnd:

    def test_full_pipeline_14_class(self):
        """Full pipeline without LLM: candidate → normalize → validate →
        compile → review. Equivalent to the test_combined_14_class_roundtrip
        test from 02-besser_debug §4.1, but through the requirements_to_buml
        pipeline instead of the WME converter."""
        candidate = _build_oss_bot_candidate()

        # Normalize
        normalized = normalize_candidate(candidate)
        assert len(normalized.classes) == 14
        assert len(normalized.sidecar_items) > 0

        # Validate
        report = validate_candidate(normalized)
        assert report.is_valid is True, f"Validation failed: {report.issues}"

        # Compile
        dm = compile_to_domain_model(normalized)
        domain_classes = [t for t in dm.types if isinstance(t, Class)]
        domain_enums = [t for t in dm.types if isinstance(t, Enumeration)]
        assert len(domain_classes) == 14
        assert len(domain_enums) == 9
        assert len(dm.associations) == 14
        assert len(dm.constraints) == 2

        # Spot-check specific classes
        proj = dm.get_class_by_name("AutomationProject")
        assert proj is not None
        proj_id_attr = next((a for a in proj.attributes if a.name == "project_id"), None)
        assert proj_id_attr is not None
        assert proj_id_attr.is_id is True

        bot_inst = dm.get_class_by_name("BotInstance")
        assert bot_inst is not None

        # Review
        summary, sidecar = generate_review(normalized, dm)
        assert len(summary.class_names) == 14
        assert summary.sidecar_item_count == len(sidecar.entries)

    def test_candidate_json_replay(self):
        """Test the skip_llm=True path of the top-level convenience function."""
        from besser.utilities.requirements_to_buml import requirements_to_buml

        candidate = _build_oss_bot_candidate()
        result = requirements_to_buml(
            document_text="(not used)",
            skip_llm=True,
            candidate_json=candidate.model_dump(),
        )
        assert isinstance(result["domain_model"], DomainModel)
        assert len(result["review_summary"].class_names) == 14
        assert result["validation_report"].is_valid is True
