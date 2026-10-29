from step9.prompt import build_evidence_package
from step9.trial import select_trial_rows, trial_tags


def row(anchor_id, quality, relation, source_type="navigation_intent"):
    return {
        "anchor_id": anchor_id,
        "clip_id": "clip",
        "anchor_ns": 1,
        "quality": {"status": quality, "reasons": []},
        "structured_coc": {
            "nodes": [
                {"node_id": "lat", "node_type": "lateral_decision", "value": {"action": "keep_direction"}},
                {"node_id": "lon", "node_type": "longitudinal_decision", "value": {"action": "maintain_speed"}},
                {"node_id": "nav", "node_type": "navigation_intent", "value": {"action": "straight"}},
                {"node_id": "actor", "node_type": "actor_state", "value": {"actor_class": "automobile"}},
            ],
            "links": [
                {"source_node_id": "actor" if source_type == "actor_state" else "nav", "target_node_id": "lon" if source_type == "actor_state" else "lat", "relation": relation, "rule_id": "test_rule"}
            ],
        },
    }


def test_trial_tags_use_relations_and_actor_count():
    package = build_evidence_package(row("a", "usable", "supports", "actor_state"))
    tags = trial_tags(package)
    assert "quality:usable" in tags
    assert "relation:supports" in tags
    assert "actors:single" in tags


def test_trial_selection_respects_limit():
    rows = [
        row("a", "usable", "aligns_with"),
        row("b", "partial", "stage_consistent"),
        row("c", "unknown", "insufficient_evidence"),
    ]
    assert len(select_trial_rows(rows, limit=2)) == 2
