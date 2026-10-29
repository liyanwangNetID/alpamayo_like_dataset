from step8.build_step8 import structured_causality_schema
from step8.contract import GENERATOR_VERSION, RULE_VERSION


def test_stage_consistent_is_in_schema():
    enum = structured_causality_schema()["$defs"]["link"]["properties"]["relation"]["enum"]
    assert "stage_consistent" in enum


def test_step8_semantic_versions_are_upgraded():
    assert GENERATOR_VERSION == "0.2.0"
    assert RULE_VERSION == "structured_causality_rules_v0.3"
