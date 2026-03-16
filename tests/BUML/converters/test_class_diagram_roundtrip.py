"""
Round-trip fidelity tests for DomainModel -> WME JSON -> DomainModel.

Verifies that Property-level fields (is_id, is_read_only, multiplicity,
is_optional, default_value) and other structural semantics survive the
class_buml_to_json -> process_class_diagram round-trip.

Test location: tests/BUML/converters/test_class_diagram_roundtrip.py

Run:
    pytest tests/BUML/converters/test_class_diagram_roundtrip.py -v
"""

import pytest

from besser.BUML.metamodel.structural import (
    Class, Property, DomainModel, PrimitiveDataType,
    Enumeration, EnumerationLiteral,
    BinaryAssociation, Generalization, Constraint,
    Multiplicity, UNLIMITED_MAX_MULTIPLICITY,
)
from besser.utilities.web_modeling_editor.backend.services.converters.buml_to_json.class_diagram_converter import (
    class_buml_to_json,
)
from besser.utilities.web_modeling_editor.backend.services.converters.json_to_buml.class_diagram_processor import (
    process_class_diagram,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _roundtrip(dm: DomainModel) -> DomainModel:
    """Export *dm* to WME JSON, then re-import it, returning the rebuilt model."""
    json_data = class_buml_to_json(dm)
    wrapped = {
        "title": dm.name,
        "model": {
            "elements": json_data.get("elements", {}),
            "relationships": json_data.get("relationships", {}),
        },
    }
    return process_class_diagram(wrapped)


def _get_attr(dm: DomainModel, class_name: str, attr_name: str) -> Property:
    """Retrieve a Property by class name + attribute name, or fail."""
    cls = dm.get_class_by_name(class_name)
    assert cls is not None, f"Class '{class_name}' not found after round-trip"
    prop = next((a for a in cls.attributes if a.name == attr_name), None)
    assert prop is not None, f"Attribute '{attr_name}' not found in class '{class_name}'"
    return prop


# ---------------------------------------------------------------------------
# 1. is_id round-trip  (fix 1.1)
# ---------------------------------------------------------------------------

class TestIsIdRoundtrip:

    def test_is_id_true_survives(self):
        cls = Class(name="AutomationProject")
        cls.add_attribute(Property(name="projectId", type=PrimitiveDataType("str"), is_id=True))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "AutomationProject", "projectId")
        assert prop.is_id is True

    def test_is_id_false_is_default(self):
        cls = Class(name="Environment")
        cls.add_attribute(Property(name="envName", type=PrimitiveDataType("str")))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Environment", "envName")
        assert prop.is_id is False


# ---------------------------------------------------------------------------
# 2. is_read_only round-trip  (fix 1.2)
# ---------------------------------------------------------------------------

class TestIsReadOnlyRoundtrip:

    def test_is_read_only_true_survives(self):
        cls = Class(name="Environment")
        cls.add_attribute(Property(name="envId", type=PrimitiveDataType("str"), is_read_only=True))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Environment", "envId")
        assert prop.is_read_only is True

    def test_is_read_only_false_is_default(self):
        cls = Class(name="Environment")
        cls.add_attribute(Property(name="envName", type=PrimitiveDataType("str")))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Environment", "envName")
        assert prop.is_read_only is False


# ---------------------------------------------------------------------------
# 3. Attribute-level multiplicity round-trip  (fix 1.3)
# ---------------------------------------------------------------------------

class TestAttributeMultiplicityRoundtrip:

    def test_zero_to_many(self):
        cls = Class(name="BotTemplate")
        cls.add_attribute(Property(
            name="defaultTriggerEvents",
            type=PrimitiveDataType("str"),
            multiplicity=Multiplicity(0, UNLIMITED_MAX_MULTIPLICITY),
        ))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "BotTemplate", "defaultTriggerEvents")
        assert prop.multiplicity.min == 0
        assert prop.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY

    def test_one_to_five(self):
        cls = Class(name="Rule")
        cls.add_attribute(Property(
            name="tags",
            type=PrimitiveDataType("str"),
            multiplicity=Multiplicity(1, 5),
        ))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Rule", "tags")
        assert prop.multiplicity.min == 1
        assert prop.multiplicity.max == 5

    def test_default_one_to_one_not_written(self):
        """Default 1..1 should survive (it won't be in JSON, import defaults to 1..1)."""
        cls = Class(name="Action")
        cls.add_attribute(Property(name="actionName", type=PrimitiveDataType("str")))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Action", "actionName")
        assert prop.multiplicity.min == 1
        assert prop.multiplicity.max == 1


# ---------------------------------------------------------------------------
# 4. is_optional round-trip  (regression guard)
# ---------------------------------------------------------------------------

class TestIsOptionalRoundtrip:

    def test_is_optional_true(self):
        cls = Class(name="Action")
        cls.add_attribute(Property(name="rollbackHint", type=PrimitiveDataType("str"), is_optional=True))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Action", "rollbackHint")
        assert prop.is_optional is True

    def test_is_optional_false(self):
        cls = Class(name="Action")
        cls.add_attribute(Property(name="actionName", type=PrimitiveDataType("str")))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Action", "actionName")
        assert prop.is_optional is False


# ---------------------------------------------------------------------------
# 5. default_value round-trip  (regression guard)
# ---------------------------------------------------------------------------

class TestDefaultValueRoundtrip:

    def test_int_default(self):
        cls = Class(name="Rule")
        cls.add_attribute(Property(name="priority", type=PrimitiveDataType("int"), default_value=10))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Rule", "priority")
        assert prop.default_value == 10

    def test_str_default(self):
        cls = Class(name="Rule")
        cls.add_attribute(Property(name="status", type=PrimitiveDataType("str"), default_value="active"))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Rule", "status")
        assert prop.default_value == "active"

    def test_no_default(self):
        cls = Class(name="Rule")
        cls.add_attribute(Property(name="ruleName", type=PrimitiveDataType("str")))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "Rule", "ruleName")
        assert prop.default_value is None


# ---------------------------------------------------------------------------
# 6. Association multiplicity round-trip  (regression guard)
# ---------------------------------------------------------------------------

class TestAssociationMultiplicityRoundtrip:

    def test_one_to_many(self):
        cls_proj = Class(name="AutomationProject")
        cls_env = Class(name="Environment")

        end_proj = Property(
            name="project", type=cls_proj,
            multiplicity=Multiplicity(1, 1),
            is_navigable=False,
        )
        end_env = Property(
            name="environments", type=cls_env,
            multiplicity=Multiplicity(1, UNLIMITED_MAX_MULTIPLICITY),
            is_navigable=True,
        )
        assoc = BinaryAssociation(
            name="Project_Environment",
            ends={end_proj, end_env},
        )
        dm = DomainModel("test", types={cls_proj, cls_env}, associations={assoc})

        dm2 = _roundtrip(dm)
        assert len(dm2.associations) >= 1
        assoc2 = next(iter(dm2.associations))
        ends2 = {e.name: e for e in assoc2.ends}
        assert ends2["environments"].multiplicity.min == 1
        assert ends2["environments"].multiplicity.max == UNLIMITED_MAX_MULTIPLICITY


# ---------------------------------------------------------------------------
# 7. Abstract class round-trip  (regression guard)
# ---------------------------------------------------------------------------

class TestAbstractClassRoundtrip:

    def test_is_abstract_true(self):
        cls = Class(name="BaseConnector", is_abstract=True)
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        cls2 = dm2.get_class_by_name("BaseConnector")
        assert cls2 is not None
        assert cls2.is_abstract is True

    def test_is_abstract_false(self):
        cls = Class(name="ConcreteClass")
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)
        cls2 = dm2.get_class_by_name("ConcreteClass")
        assert cls2 is not None
        assert cls2.is_abstract is False


# ---------------------------------------------------------------------------
# 8. Enumeration round-trip  (regression guard)
# ---------------------------------------------------------------------------

class TestEnumerationRoundtrip:

    def test_literals_preserved(self):
        literals = {
            EnumerationLiteral(name="GITHUB"),
            EnumerationLiteral(name="GITLAB"),
            EnumerationLiteral(name="WEBHOOK"),
        }
        enum = Enumeration(name="PlatformType", literals=literals)
        dm = DomainModel("test", types={enum})

        dm2 = _roundtrip(dm)
        enum2 = next(
            (t for t in dm2.types if isinstance(t, Enumeration) and t.name == "PlatformType"),
            None,
        )
        assert enum2 is not None
        literal_names = {lit.name for lit in enum2.literals}
        assert literal_names == {"GITHUB", "GITLAB", "WEBHOOK"}


# ---------------------------------------------------------------------------
# 9. Constraint round-trip  (regression guard)
# ---------------------------------------------------------------------------

class TestConstraintRoundtrip:
    class TestConstraintRoundtrip:

        def test_constraint_element_exported(self):
            """Verify that constraints are at least serialized into the JSON output.

            Full OCL round-trip depends on process_ocl_constraints() which has its
            own parsing requirements.  This test only checks that the export
            direction produces the expected ClassOCLConstraint element and
            ClassOCLLink relationship — it does NOT assert that the constraint
            survives the full import back, which is a known upstream limitation
            outside the scope of the Property-field round-trip fixes.
            """
            cls = Class(name="BotInstance")
            constraint = Constraint(
                name="must_have_repo",
                context=cls,
                expression="context.repositories->size() >= 1",
                language="OCL",
            )
            dm = DomainModel("test", types={cls}, constraints={constraint})

            json_data = class_buml_to_json(dm)
            elements = json_data.get("elements", {})
            relationships = json_data.get("relationships", {})

            # The constraint should appear as a ClassOCLConstraint element
            ocl_elements = [
                e for e in elements.values()
                if e.get("type") == "ClassOCLConstraint"
            ]
            assert len(ocl_elements) >= 1, "Constraint not exported as ClassOCLConstraint element"
            assert ocl_elements[0].get("constraint") == "context.repositories->size() >= 1"

            # A ClassOCLLink should connect it to BotInstance
            ocl_links = [
                r for r in relationships.values()
                if r.get("type") == "ClassOCLLink"
            ]
            assert len(ocl_links) >= 1, "ClassOCLLink relationship not created for constraint"


# ---------------------------------------------------------------------------
# 10. Combined multi-field round-trip
# ---------------------------------------------------------------------------

class TestCombinedRoundtrip:

    def test_single_class_all_property_fields(self):
        """One class with attributes exercising every Property field at once."""
        cls = Class(name="FullTest")
        cls.add_attribute(Property(
            name="pk",
            type=PrimitiveDataType("str"),
            is_id=True,
            is_read_only=True,
            is_optional=False,
            default_value="auto",
            multiplicity=Multiplicity(1, 1),
        ))
        cls.add_attribute(Property(
            name="tags",
            type=PrimitiveDataType("str"),
            is_id=False,
            is_read_only=False,
            is_optional=True,
            multiplicity=Multiplicity(0, UNLIMITED_MAX_MULTIPLICITY),
        ))
        dm = DomainModel("test", types={cls})

        dm2 = _roundtrip(dm)

        pk = _get_attr(dm2, "FullTest", "pk")
        assert pk.is_id is True
        assert pk.is_read_only is True
        assert pk.is_optional is False
        assert pk.default_value == "auto"
        assert pk.multiplicity.min == 1
        assert pk.multiplicity.max == 1

        tags = _get_attr(dm2, "FullTest", "tags")
        assert tags.is_id is False
        assert tags.is_read_only is False
        assert tags.is_optional is True
        assert tags.default_value is None
        assert tags.multiplicity.min == 0
        assert tags.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY

    def test_enum_typed_attribute_with_multiplicity(self):
        """Attribute whose type is an Enumeration + non-default multiplicity."""
        enum = Enumeration(name="EventType", literals={
            EnumerationLiteral(name="ISSUE_CREATED"),
            EnumerationLiteral(name="PR_CREATED"),
        })
        cls = Class(name="BotTemplate")
        cls.add_attribute(Property(
            name="defaultEvents",
            type=enum,
            multiplicity=Multiplicity(0, UNLIMITED_MAX_MULTIPLICITY),
            is_optional=True,
        ))
        dm = DomainModel("test", types={cls, enum})

        dm2 = _roundtrip(dm)
        prop = _get_attr(dm2, "BotTemplate", "defaultEvents")
        assert prop.multiplicity.min == 0
        assert prop.multiplicity.max == UNLIMITED_MAX_MULTIPLICITY
        assert prop.is_optional is True
        assert isinstance(prop.type, Enumeration)
        assert prop.type.name == "EventType"
