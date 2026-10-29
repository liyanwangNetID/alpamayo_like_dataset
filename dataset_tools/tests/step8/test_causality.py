from __future__ import annotations

from step8.causality import build_structured_causality
from step8.contract import JoinedAnchor


def joined(
    *,
    navigation="straight",
    navigation_quality="usable",
    longitudinal="decelerate",
    lateral="keep_direction",
    meta_quality="usable",
    scene_quality="usable",
    lead=None,
    left=None,
    right=None,
    road_type="lane_following",
    road_quality="usable",
    navigation_reasons=None,
):
    anchor = "clip_10"
    return JoinedAnchor(
        anchor_id=anchor,
        clip_id="clip",
        anchor_ns=10,
        keyframe={"anchor_id": anchor, "clip_id": "clip", "anchor_ns": 10},
        navigation={
            "anchor_id": anchor,
            "clip_id": "clip",
            "anchor_ns": 10,
            "navigation_format_version": "0.1-draft",
            "navigation": {
                "action": navigation,
                "quality_status": navigation_quality,
                "reasons": list(navigation_reasons or []),
            },
        },
        scene_fact={
            "anchor_id": anchor,
            "clip_id": "clip",
            "anchor_ns": 10,
            "scene_fact_format_version": "0.1-draft",
            "road_context": {
                "type": road_type,
                "intersection_proximity": "none",
                "stop_line_proximity": "none",
                "yield_line_proximity": "none",
                "quality_status": road_quality,
            },
            "actor_context": {
                "lead_actors": lead or [],
                "left_nearby_actors": left or [],
                "right_nearby_actors": right or [],
            },
            "quality": {"status": scene_quality},
        },
        meta_action={
            "anchor_id": anchor,
            "clip_id": "clip",
            "anchor_ns": 10,
            "label_format_version": "0.2-draft",
            "overall_quality_status": meta_quality,
            "longitudinal": {"action": longitudinal, "quality_status": meta_quality},
            "lateral": {"action": lateral, "quality_status": meta_quality},
        },
    )


def actor(rank=1, distance="near", trend="approaching", speed="slower_than_ego", actor_class="automobile", direction="same_direction"):
    return {
        "role_rank": rank,
        "track_id": rank + 100,
        "actor_class": actor_class,
        "relative_position": "front",
        "relative_distance": distance,
        "distance_trend": trend,
        "relative_speed_category": speed,
        "quality_status": "usable",
        "lane_direction_relation": direction,
    }


def test_navigation_alignment_is_not_called_absolute_causation():
    record = build_structured_causality(joined())
    links = record["structured_coc"]["links"]
    assert any(link["relation"] == "aligns_with" for link in links)
    assert all(link["relation"] != "causes" for link in links)


def test_lead_actor_supports_deceleration():
    record = build_structured_causality(joined(lead=[actor()]))
    links = record["structured_coc"]["links"]
    support = [link for link in links if link["relation"] == "supports"]
    assert len(support) == 1
    assert support[0]["target_node_id"] == "decision_longitudinal"
    assert record["quality"]["status"] == "usable"


def test_far_lead_actor_is_not_forced_into_coc():
    record = build_structured_causality(joined(lead=[actor(distance="far")]))
    node_ids = {node["node_id"] for node in record["structured_coc"]["nodes"]}
    assert "actor_lead_1" not in node_ids


def test_side_actor_does_not_create_target_lane_causality():
    record = build_structured_causality(
        joined(lateral="change_lane_left", left=[actor(direction="same_direction")])
    )
    assert all(
        not link["rule_id"].endswith("actor_constrains_lane_change_v01")
        for link in record["structured_coc"]["links"]
    )
    assert all(
        node["node_id"] != "actor_left_1"
        for node in record["structured_coc"]["nodes"]
    )


def test_opposing_vehicle_is_not_used_as_following_constraint():
    record = build_structured_causality(
        joined(lead=[actor(direction="opposing")])
    )
    assert all(
        link["source_node_id"] != "actor_lead_1"
        for link in record["structured_coc"]["links"]
    )


def test_front_person_can_support_response_despite_opposing_lane_region():
    record = build_structured_causality(
        joined(lead=[actor(actor_class="person", direction="opposing")])
    )
    links = record["structured_coc"]["links"]
    assert any(
        link["rule_id"] == "front_vulnerable_actor_supports_longitudinal_response_v01"
        for link in links
    )


def test_unlinked_road_context_node_is_omitted():
    record = build_structured_causality(joined())
    assert all(
        node["node_id"] != "road_context"
        for node in record["structured_coc"]["nodes"]
    )


def test_unknown_meta_action_makes_record_unknown():
    record = build_structured_causality(
        joined(longitudinal="unknown", lateral="unknown", meta_quality="unknown")
    )
    assert record["quality"]["status"] == "unknown"
    assert "meta_action_quality_unknown" in record["quality"]["reasons"]


def test_road_context_does_not_create_stop_line_causality():
    record = build_structured_causality(joined(longitudinal="stop"))
    assert all(
        "stop_line" not in link["rule_id"]
        for link in record["structured_coc"]["links"]
    )


def test_output_is_deterministic_for_actor_input_order():
    first = build_structured_causality(joined(lead=[actor(rank=2), actor(rank=1)]))
    second = build_structured_causality(joined(lead=[actor(rank=1), actor(rank=2)]))
    assert first == second


def navigation_link(record):
    return next(
        link
        for link in record["structured_coc"]["links"]
        if link["source_node_id"] == "navigation_intent"
        and link["target_node_id"] == "decision_lateral"
    )


def test_upcoming_left_turn_and_keep_direction_are_stage_consistent():
    record = build_structured_causality(joined(
        navigation="left",
        lateral="keep_direction",
        road_type="intersection_approach",
        navigation_reasons=["upcoming_intersection_detected"],
    ))
    link = navigation_link(record)
    assert link["relation"] == "stage_consistent"
    assert link["confidence"] == "supported"
    assert link["rule_id"] == "upcoming_navigation_precedes_lateral_execution_v01"


def test_upcoming_right_turn_and_keep_direction_are_stage_consistent():
    record = build_structured_causality(joined(
        navigation="right",
        lateral="keep_direction",
        road_type="intersection_approach",
        navigation_reasons=["upcoming_intersection_detected"],
    ))
    assert navigation_link(record)["relation"] == "stage_consistent"


def test_turn_intent_and_keep_direction_without_approach_evidence_are_insufficient():
    record = build_structured_causality(joined(
        navigation="left",
        lateral="keep_direction",
        road_type="lane_following",
        navigation_reasons=["upcoming_intersection_detected"],
    ))
    assert navigation_link(record)["relation"] == "insufficient_evidence"


def test_straight_navigation_does_not_claim_support_for_lane_change():
    record = build_structured_causality(joined(
        navigation="straight",
        lateral="change_lane_left",
    ))
    assert navigation_link(record)["relation"] == "insufficient_evidence"


def test_right_turn_intent_does_not_claim_support_for_right_lane_change():
    record = build_structured_causality(joined(
        navigation="right",
        lateral="change_lane_right",
        road_type="intersection_approach",
        navigation_reasons=["upcoming_intersection_detected"],
    ))
    assert navigation_link(record)["relation"] == "insufficient_evidence"


def test_only_direct_same_stage_pairs_align():
    for navigation, lateral in (
        ("straight", "keep_direction"),
        ("left", "turn_left"),
        ("right", "turn_right"),
    ):
        record = build_structured_causality(joined(
            navigation=navigation,
            lateral=lateral,
        ))
        link = navigation_link(record)
        assert link["relation"] == "aligns_with"
        assert link["rule_id"] == "navigation_lateral_direct_alignment_v02"


def test_unknown_navigation_remains_insufficient():
    record = build_structured_causality(joined(
        navigation="unknown",
        navigation_quality="unknown",
    ))
    link = navigation_link(record)
    assert link["relation"] == "insufficient_evidence"
    assert link["confidence"] == "unknown"
