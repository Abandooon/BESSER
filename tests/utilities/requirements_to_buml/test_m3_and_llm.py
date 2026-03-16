"""
Tests for M3 schema projection and LLM integration.

Covers:
1. M3 introspection correctness
2. Auto-generated Pydantic model behavior
3. JSON Schema structure
4. Prompt construction
5. LLM end-to-end (requires API key, auto-skipped otherwise)

Run:
    pytest tests/utilities/requirements_to_buml/test_m3_and_llm.py -v

LLM tests:
    OPENAI_API_KEY=sk-... pytest ... -k TestLLM -v
    ANTHROPIC_API_KEY=sk-... pytest ... -k TestLLM -v
"""

import json
import os
import pathlib

import pytest

from besser.BUML.metamodel.structural import Class, Enumeration, DomainModel

from besser.utilities.requirements_to_buml.m3_schema_projector import (
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
    ReviewSummary,
    ValidationReport,
    project_m3_to_json_schema,
    get_m3_property_fields,
    get_m3_introspection_report,
)

from besser.utilities.requirements_to_buml.prompting import (
    build_system_prompt,
    build_user_prompt,
)


# ===================================================================
# 1. M3 Introspection
# ===================================================================

class TestM3Introspection:

    def test_property_fields_contain_key_params(self):
        fields = get_m3_property_fields()
        expected = {"name", "type", "is_id", "is_read_only", "is_optional",
                    "multiplicity", "visibility", "default_value", "is_composite"}
        assert expected.issubset(set(fields.keys()))

    def test_property_name_is_required(self):
        assert get_m3_property_fields()["name"]["required"] is True

    def test_property_is_id_default_false(self):
        f = get_m3_property_fields()["is_id"]
        assert f["required"] is False
        assert f["default"] is False

    def test_report_covers_all_metaclasses(self):
        report = get_m3_introspection_report()
        expected = {"Property", "Class", "BinaryAssociation", "Enumeration",
                    "EnumerationLiteral", "Constraint", "Multiplicity", "DomainModel"}
        assert expected == set(report.keys())


# ===================================================================
# 2. Auto-generated Pydantic models
# ===================================================================

class TestDynamicModels:

    def test_candidate_property_instantiation(self):
        p = CandidateProperty(name="foo_id", type="str", is_id=True)
        assert p.is_id is True
        assert p.visibility == "public"
        assert p.multiplicity == "1..1"

    def test_candidate_class_with_attributes(self):
        c = CandidateClass(name="Foo", attributes=[
            CandidateProperty(name="x", type="str"),
        ])
        assert c.attributes[0].name == "x"

    def test_candidate_model_json_roundtrip(self):
        m = CandidateModel(
            domain_name="Test",
            classes=[CandidateClass(name="A", attributes=[
                CandidateProperty(name="a_id", type="str", is_id=True),
            ])],
            enumerations=[CandidateEnumeration(name="E", literals=[
                CandidateEnumerationLiteral(name="X"),
            ])],
            associations=[CandidateAssociation(name="A_B",
                end1=CandidateAssociationEnd(role="a", type="A"),
                end2=CandidateAssociationEnd(role="b", type="B", multiplicity="0..*"),
            )],
        )
        j = m.model_dump_json()
        m2 = CandidateModel.model_validate_json(j)
        assert m2.classes[0].attributes[0].is_id is True
        assert m2.associations[0].end2.multiplicity == "0..*"

    def test_extensions_preserved(self):
        c = CandidateClass(name="X", extensions={"foo": {"bar": 1}})
        assert c.extensions["foo"]["bar"] == 1

    def test_normalized_model_has_sidecar(self):
        nm = NormalizedCandidateModel(domain_name="T", sidecar_items=[{"k": "v"}])
        assert len(nm.sidecar_items) == 1

    def test_normalized_aliases_are_same_type(self):
        """NormalizedProperty IS CandidateProperty — same type, MDE-correct."""
        from besser.utilities.requirements_to_buml.m3_schema_projector import (
            NormalizedProperty,
        )
        assert NormalizedProperty is CandidateProperty


# ===================================================================
# 3. JSON Schema structure
# ===================================================================

class TestJsonSchema:

    def test_schema_is_valid_json(self):
        s = project_m3_to_json_schema()
        assert len(json.dumps(s)) > 100

    def test_schema_has_all_defs(self):
        defs = set(project_m3_to_json_schema().get("$defs", {}).keys())
        expected = {"CandidateProperty", "CandidateClass",
                    "CandidateAssociationEnd", "CandidateAssociation",
                    "CandidateEnumerationLiteral", "CandidateEnumeration",
                    "CandidateConstraint", "CandidateUnresolvedItem"}
        assert expected == defs

    def test_schema_top_level_properties(self):
        props = set(project_m3_to_json_schema()["properties"].keys())
        expected = {"domain_name", "classes", "enumerations", "associations",
                    "constraints", "unresolved_items", "metadata"}
        assert expected == props

    def test_property_def_has_is_id(self):
        assert "is_id" in project_m3_to_json_schema()["$defs"]["CandidateProperty"]["properties"]

    def test_property_def_has_multiplicity(self):
        assert "multiplicity" in project_m3_to_json_schema()["$defs"]["CandidateProperty"]["properties"]

    def test_property_def_has_is_read_only(self):
        assert "is_read_only" in project_m3_to_json_schema()["$defs"]["CandidateProperty"]["properties"]


# ===================================================================
# 4. Prompt construction
# ===================================================================

class TestPrompts:

    def test_system_prompt_embeds_schema(self):
        prompt = build_system_prompt()
        assert '"$defs"' in prompt
        assert "CandidateProperty" in prompt
        assert "is_id" in prompt
        assert "multiplicity" in prompt

    def test_system_prompt_no_hand_written_fragments(self):
        """Prompt should NOT contain hand-written schema descriptions."""
        prompt = build_system_prompt()
        # Old hand-written markers that should be gone
        assert "### Class structure" not in prompt
        assert "### Association structure" not in prompt

    def test_user_prompt_oss_bot_hint(self):
        p = build_user_prompt("Some doc", domain_hint="oss_bot")
        assert "BotTemplate" in p

    def test_user_prompt_agnostic(self):
        p = build_user_prompt("Some doc", domain_hint=None)
        assert "General software engineering" in p
        assert "BotTemplate" not in p

    def test_user_prompt_custom(self):
        p = build_user_prompt("Doc", domain_hint="E-commerce domain.",
                              core_class_hints="Product, Order")
        assert "E-commerce" in p
        assert "Product" in p


# ===================================================================
# 5. LLM Integration (requires API key)
# ===================================================================

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")

_DOCS_DIR = pathlib.Path(__file__).resolve().parents[3] / "docs"
_OSS_BOT_DOC = _DOCS_DIR / "01_用户上传工程需求文档.md"

_LIBRARY_DOC = """\
# 图书馆管理系统需求
## 业务对象
- 图书 (Book): 书名、ISBN、出版日期、页数
- 借阅者 (Borrower): 姓名、证件号、联系方式
- 借阅记录 (BorrowRecord): 借出日期、应还日期、状态
- 图书分类 (Category): 分类名称
- 作者 (Author): 姓名
## 关系
- 一本图书可有多个作者；一个作者可写多本图书
- 一本图书属于一个分类
- 一个借阅者可有多条借阅记录
## 约束
- 同时借阅不超过5本
"""

_TASK_DOC = """\
# Task Tracker
## Entities
- Project: name, status (active/archived)
- Task: title, priority (low/medium/high), status (todo/done)
- User: username, email, role (admin/member)
## Relationships
- Project contains many Tasks; Task assigned to one User
"""


def _read_oss_doc() -> str:
    if not _OSS_BOT_DOC.exists():
        pytest.skip(f"Doc not found: {_OSS_BOT_DOC}")
    return _OSS_BOT_DOC.read_text(encoding="utf-8")


def _run_pipeline(candidate: CandidateModel) -> dict:
    from besser.utilities.requirements_to_buml.normalization import normalize_candidate
    from besser.utilities.requirements_to_buml.validation import validate_candidate
    from besser.utilities.requirements_to_buml.compilation import compile_to_domain_model
    from besser.utilities.requirements_to_buml.review import generate_review

    normalized = normalize_candidate(candidate)
    report = validate_candidate(normalized)
    dm = compile_to_domain_model(normalized)
    summary, sidecar = generate_review(normalized, dm)
    return {"normalized": normalized, "validation_report": report,
            "domain_model": dm, "review_summary": summary}


@pytest.mark.skipif(not OPENAI_KEY, reason="OPENAI_API_KEY not set")
class TestLLMOpenAI:

    def test_extract_oss_bot(self):
        from besser.utilities.requirements_to_buml.extraction import extract_candidate
        doc = _read_oss_doc()
        c = extract_candidate(doc, provider="openai", model="gpt-4o",
                              api_key=OPENAI_KEY, domain_hint="oss_bot")
        assert len(c.classes) >= 10
        names = {cls.name for cls in c.classes}
        assert len({"AutomationProject", "BotTemplate", "BotInstance", "Rule", "Action"} & names) >= 3

    def test_extract_library_agnostic(self):
        from besser.utilities.requirements_to_buml.extraction import extract_candidate
        c = extract_candidate(_LIBRARY_DOC, provider="openai", model="gpt-4o",
                              api_key=OPENAI_KEY, domain_hint=None)
        assert len(c.classes) >= 3
        assert any("book" in cls.name.lower() for cls in c.classes)

    def test_full_pipeline(self):
        from besser.utilities.requirements_to_buml.extraction import extract_candidate
        doc = _read_oss_doc()
        c = extract_candidate(doc, provider="openai", model="gpt-4o",
                              api_key=OPENAI_KEY, domain_hint="oss_bot")
        r = _run_pipeline(c)
        assert len([t for t in r["domain_model"].types if isinstance(t, Class)]) >= 8


@pytest.mark.skipif(not ANTHROPIC_KEY, reason="ANTHROPIC_API_KEY not set")
class TestLLMAnthropic:

    def test_extract_oss_bot(self):
        from besser.utilities.requirements_to_buml.extraction import extract_candidate
        doc = _read_oss_doc()
        c = extract_candidate(doc, provider="anthropic", model="claude-sonnet-4-20250514",
                              api_key=ANTHROPIC_KEY, domain_hint="oss_bot")
        assert len(c.classes) >= 10

    def test_extract_generic(self):
        from besser.utilities.requirements_to_buml.extraction import extract_candidate
        c = extract_candidate(_LIBRARY_DOC, provider="anthropic",
                              model="claude-sonnet-4-20250514",
                              api_key=ANTHROPIC_KEY)
        assert len(c.classes) >= 3
