from step9.contract import PROMPT_VERSION
from step9.prompt import SYSTEM_PROMPT, build_evidence_package, llm_situation_payload


def source():
    return {
        "anchor_id": "clip_1",
        "quality": {"status": "usable", "reasons": []},
        "structured_coc": {
            "nodes": [
                {"node_id": "lat", "node_type": "lateral_decision", "value": {"action": "keep_direction"}},
                {"node_id": "lon", "node_type": "longitudinal_decision", "value": {"action": "maintain_speed"}},
                {"node_id": "nav", "node_type": "navigation_intent", "value": {"action": "right"}},
            ],
            "links": [
                {"source_node_id": "nav", "target_node_id": "lat", "relation": "stage_consistent", "rule_id": "upcoming_navigation_precedes_lateral_execution_v01"}
            ],
        },
    }


def test_current_prompt_version_and_policy():
    assert PROMPT_VERSION == "step9_minimal_rewrite_prompt_v0.12"
    assert "Prefer minimal rewriting" in SYSTEM_PROMPT
    assert "Do not add a sentence merely to make the description longer" in SYSTEM_PROMPT


def test_confirmed_facts_are_complete_and_ordered():
    package = build_evidence_package(source())
    assert llm_situation_payload(package) == {
        "confirmed_facts": [
            "The vehicle is keeping its current direction.",
            "The vehicle is maintaining speed.",
            "The route calls for a right turn ahead.",
            "The upcoming turn has not started yet.",
        ]
    }
