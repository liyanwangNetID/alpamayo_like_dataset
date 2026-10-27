from step11.splitter import build_clip_groups, deterministic_grouped_split


def row(anchor, clip, lateral="keep_direction", longitudinal="maintain_speed", navigation="straight", road="lane_following", coc="usable"):
    return {
        "anchor_id": anchor,
        "clip_id": clip,
        "selection": {"selection_sources": ["event_candidate"]},
        "model_input": {"navigation": {"navigation": {"action": navigation}}},
        "supervision": {
            "driving_decision": {"joint_action": {"lateral": lateral, "longitudinal": longitudinal}},
            "scene_facts": {"road_context": {"type": road}},
        },
        "quality": {"meta_action": "usable", "structured_causality": coc},
    }


def test_split_is_deterministic_and_clip_exclusive():
    rows = [row(f"a{i}", f"test_clip_{i // 2:03d}") for i in range(30)]
    first = deterministic_grouped_split(rows)
    second = deterministic_grouped_split(list(reversed(rows)))
    assert first == second
    assert set(first.values()) == {"train", "validation", "test"}


def test_clip_groups_keep_all_anchors_together():
    rows = [row("a", "test_clip_001"), row("b", "test_clip_001"), row("c", "test_clip_002")]
    groups = build_clip_groups(rows)
    assert {group.clip_id: group.anchor_ids for group in groups}["test_clip_001"] == ("a", "b")
