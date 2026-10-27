from step7.build_scene_facts import build_visible_camera_index


def evidence(anchor_id, track_id, *, status="combined_evidence_available", cameras=()):
    return {
        "anchor_id": anchor_id,
        "track_id": track_id,
        "evidence_status": status,
        "total_winning_cell_count": 2 if cameras else 0,
        "maximum_visible_fraction": 0.5 if cameras else None,
        "static_occlusion_evaluated": False,
        "occlusion_winning_camera_names": list(cameras),
    }


def test_visible_camera_index_uses_frozen_policy_and_canonical_order():
    rows = [evidence("a", "1", cameras=("front_wide", "cross_left"))]
    assert build_visible_camera_index(rows) == {
        ("a", "1"): ("cross_left", "front_wide")
    }


def test_visible_camera_index_keeps_nonvisible_actor_with_empty_camera_tuple():
    rows = [evidence("a", "1", status="no_geometric_candidate")]
    assert build_visible_camera_index(rows) == {("a", "1"): ()}


def test_scene_fact_builder_has_no_obsolete_observability_artifact_dependency():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] / "step7" / "build_scene_facts.py").read_text(encoding="utf-8")
    assert "actor_observability_v0.1.jsonl" not in source
    assert "step7e_geometric_occlusion_evidence_v02.jsonl" in source
