"""Deterministic structured chain-of-causality rules for Step 8."""

from __future__ import annotations

from typing import Any, Mapping

from .contract import (
    GENERATOR_VERSION,
    RULE_VERSION,
    STRUCTURED_CAUSALITY_FORMAT_VERSION,
    JoinedAnchor,
)

_RELATION_ORDER = {
    "aligns_with": 0,
    "stage_consistent": 1,
    "supports": 2,
    "insufficient_evidence": 3,
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _actor_ref(actor: Mapping[str, Any], role: str) -> dict[str, Any]:
    return {
        "scene_role": role,
        "role_rank": actor.get("role_rank"),
        "track_id": actor.get("track_id"),
    }


def _quality(value: Any) -> str:
    return value if value in {"usable", "unknown"} else "unknown"


def _node(node_id: str, node_type: str, value: Mapping[str, Any], source: str) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "value": dict(value),
        "source_ref": source,
    }


def _link(
    link_id: str,
    source: str,
    target: str,
    relation: str,
    confidence: str,
    rule_id: str,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "link_id": link_id,
        "source_node_id": source,
        "target_node_id": target,
        "relation": relation,
        "confidence": confidence,
        "rule_id": rule_id,
        "reasons": reasons,
    }


def _navigation_link(
    navigation: Mapping[str, Any],
    lateral_data: Mapping[str, Any],
    road_context: Mapping[str, Any],
) -> tuple[str, str, str, list[str]]:
    """Relate route intent to current lateral execution without overclaiming.

    Navigation denotes route intent, while the lateral label denotes execution
    within the frozen future-action horizon. Strong links are emitted only for
    direct same-stage agreement or for an explicitly evidenced pre-turn stage.
    """
    action = str(navigation.get("action", "unknown"))
    navigation_quality = _quality(navigation.get("quality_status"))
    lateral = str(lateral_data.get("action", "unknown"))
    lateral_quality = _quality(lateral_data.get("quality_status"))

    if (
        navigation_quality != "usable"
        or lateral_quality != "usable"
        or action == "unknown"
        or lateral == "unknown"
    ):
        return (
            "insufficient_evidence",
            "unknown",
            "navigation_lateral_evidence_insufficient_v02",
            ["navigation_or_lateral_decision_not_usable"],
        )

    direct_alignment = {
        ("straight", "keep_direction"),
        ("left", "turn_left"),
        ("right", "turn_right"),
    }
    if (action, lateral) in direct_alignment:
        return (
            "aligns_with",
            "supported",
            "navigation_lateral_direct_alignment_v02",
            ["navigation_intent_directly_matches_current_lateral_execution"],
        )

    road_type = str(road_context.get("type", "unknown"))
    road_quality = _quality(road_context.get("quality_status"))
    if (
        action == "straight"
        and lateral in {"change_lane_left", "change_lane_right"}
        and road_type == "lane_following"
        and road_quality == "usable"
    ):
        return (
            "stage_consistent",
            "supported",
            "straight_navigation_allows_lane_change_v01",
            ["route_level_straight_intent_is_compatible_with_lane_level_change"],
        )

    navigation_reasons = {
        str(value) for value in navigation.get("reasons", ())
    }
    upcoming_turn = (
        action in {"left", "right"}
        and lateral == "keep_direction"
        and road_type == "intersection_approach"
        and road_quality == "usable"
        and "upcoming_intersection_detected" in navigation_reasons
    )
    if upcoming_turn:
        return (
            "stage_consistent",
            "supported",
            "upcoming_navigation_precedes_lateral_execution_v01",
            [
                f"navigation_describes_upcoming_{action}_turn",
                "current_lateral_action_is_pre_turn_keep_direction",
                "turn_execution_not_observed_in_current_action_window",
            ],
        )

    return (
        "insufficient_evidence",
        "unknown",
        "navigation_lateral_stage_or_semantics_insufficient_v02",
        ["navigation_intent_does_not_directly_support_current_lateral_action"],
    )


def _road_relation(
    road_context: Mapping[str, Any],
    longitudinal: str,
) -> tuple[str, str, str, list[str]] | None:
    if longitudinal not in {"decelerate", "stop"}:
        return None
    if _quality(road_context.get("quality_status")) != "usable":
        return None
    road_type = str(road_context.get("type", "unknown"))
    proximity = str(road_context.get("intersection_proximity", "unknown"))
    if road_type not in {"intersection_approach", "intersection"}:
        return None
    if proximity not in {"approaching", "near", "at"}:
        return None
    reasons = {str(value) for value in road_context.get("reasons", ())}
    if "wait_line" in reasons:
        return (
            "supports",
            "supported",
            "wait_line_intersection_supports_longitudinal_response_v01",
            ["usable_wait_line_context_is_consistent_with_longitudinal_response"],
        )
    return (
        "supports",
        "weak",
        "intersection_context_supports_longitudinal_response_v01",
        ["usable_intersection_context_is_consistent_with_longitudinal_response"],
    )


def _lead_relation(actor: Mapping[str, Any], longitudinal: str) -> tuple[str, str, str, list[str]] | None:
    if _quality(actor.get("quality_status")) != "usable":
        return None
    if actor.get("relative_distance") not in {"near", "medium"}:
        return None
    if longitudinal not in {"decelerate", "stop"}:
        return None
    actor_class = str(actor.get("actor_class", ""))
    direction = str(actor.get("lane_direction_relation", "unknown"))
    restrictive = (
        actor.get("distance_trend") == "approaching"
        or actor.get("relative_speed_category") in {"slower_than_ego", "stationary"}
    )
    if not restrictive:
        return None
    if actor_class in {"person", "rider"}:
        return (
            "supports",
            "supported",
            "front_vulnerable_actor_supports_longitudinal_response_v01",
            ["front_vulnerable_actor_presents_path_relevant_safety_constraint"],
        )
    if direction != "same_direction":
        return None
    return (
        "supports",
        "supported",
        "same_direction_lead_vehicle_supports_longitudinal_response_v01",
        ["same_direction_lead_vehicle_presents_longitudinal_constraint"],
    )


def _side_relation(actor: Mapping[str, Any], lateral: str, side: str) -> tuple[str, str, str, list[str]] | None:
    # Side-of-Ego role and lane direction do not prove target-lane membership or
    # that an Actor constrained the executed lane change. Keep the Actor in
    # Scene Facts, but emit no Step 8 causal link until target-lane gap evidence
    # exists.
    return None


def build_structured_causality(joined: JoinedAnchor) -> dict[str, Any]:
    navigation = _mapping(joined.navigation.get("navigation"))
    scene = joined.scene_fact
    actor_context = _mapping(scene.get("actor_context"))
    meta = joined.meta_action
    lateral_data = _mapping(meta.get("lateral"))
    longitudinal_data = _mapping(meta.get("longitudinal"))

    navigation_action = str(navigation.get("action", "unknown"))
    navigation_quality = _quality(navigation.get("quality_status"))
    lateral = str(lateral_data.get("action", "unknown"))
    longitudinal = str(longitudinal_data.get("action", "unknown"))
    meta_quality = _quality(meta.get("overall_quality_status"))
    scene_quality = _quality(_mapping(scene.get("quality")).get("status"))

    nodes = [
        _node(
            "navigation_intent",
            "navigation_intent",
            {"action": navigation_action, "quality_status": navigation_quality},
            "navigation.jsonl",
        ),
        _node(
            "decision_longitudinal",
            "longitudinal_decision",
            {"action": longitudinal, "quality_status": _quality(longitudinal_data.get("quality_status"))},
            "meta_actions_v0.2.jsonl",
        ),
        _node(
            "decision_lateral",
            "lateral_decision",
            {"action": lateral, "quality_status": _quality(lateral_data.get("quality_status"))},
            "meta_actions_v0.2.jsonl",
        ),
    ]
    links: list[dict[str, Any]] = []

    relation, confidence, rule_id, reasons = _navigation_link(
        navigation,
        lateral_data,
        _mapping(scene.get("road_context")),
    )
    links.append(_link("link_navigation_lateral", "navigation_intent", "decision_lateral", relation, confidence, rule_id, reasons))

    road_context = _mapping(scene.get("road_context"))
    road_relation = _road_relation(road_context, longitudinal)
    if road_relation is not None:
        nodes.append(_node(
            "road_context",
            "road_context",
            {
                "type": road_context.get("type", "unknown"),
                "intersection_proximity": road_context.get("intersection_proximity", "unknown"),
                "stop_line_proximity": road_context.get("stop_line_proximity", "unknown"),
                "yield_line_proximity": road_context.get("yield_line_proximity", "unknown"),
                "reasons": list(road_context.get("reasons", ())),
                "quality_status": _quality(road_context.get("quality_status")),
            },
            "scene_facts.jsonl",
        ))
        rel, conf, rule, why = road_relation
        links.append(_link(
            "link_road_context_decision_longitudinal",
            "road_context",
            "decision_longitudinal",
            rel, conf, rule, why,
        ))

    lead_actors = actor_context.get("lead_actors", [])
    primary_lead = None
    if isinstance(lead_actors, list):
        primary_lead = next(
            (
                actor for actor in lead_actors
                if isinstance(actor, Mapping) and actor.get("role_rank") == 1
            ),
            None,
        )
    if primary_lead is not None:
        relation_data = _lead_relation(primary_lead, longitudinal)
        if relation_data is not None:
            node_id = "actor_lead_1"
            nodes.append(_node(
                node_id,
                "actor_state",
                {
                    "actor_ref": _actor_ref(primary_lead, "lead"),
                    "actor_class": primary_lead.get("actor_class"),
                    "relative_position": primary_lead.get("relative_position"),
                    "relative_distance": primary_lead.get("relative_distance"),
                    "distance_trend": primary_lead.get("distance_trend"),
                    "relative_speed_category": primary_lead.get("relative_speed_category"),
                    "lane_direction_relation": primary_lead.get("lane_direction_relation", "unknown"),
                    "quality_status": _quality(primary_lead.get("quality_status")),
                },
                "scene_facts.jsonl",
            ))
            rel, conf, rule, why = relation_data
            links.append(_link(
                f"link_{node_id}_decision_longitudinal",
                node_id,
                "decision_longitudinal",
                rel, conf, rule, why,
            ))

    nodes.sort(key=lambda item: item["node_id"])
    links.sort(
        key=lambda item: (
            _RELATION_ORDER.get(item["relation"], 99),
            item["source_node_id"],
            item["target_node_id"],
            item["rule_id"],
        )
    )
    for index, link in enumerate(links, 1):
        link["link_id"] = f"link_{index:03d}"

    supported = any(link["confidence"] == "supported" for link in links)
    lateral_covered = any(
        link["target_node_id"] == "decision_lateral"
        and link["confidence"] in {"supported", "weak"}
        for link in links
    )
    longitudinal_covered = any(
        link["target_node_id"] == "decision_longitudinal"
        and link["confidence"] in {"supported", "weak"}
        for link in links
    )
    coverage_reasons = []
    if (
        _quality(lateral_data.get("quality_status")) == "usable"
        and lateral not in {"unknown", "keep_direction"}
        and not lateral_covered
    ):
        coverage_reasons.append("lateral_decision_without_supported_context")
    if (
        _quality(longitudinal_data.get("quality_status")) == "usable"
        and longitudinal in {"decelerate", "stop"}
        and not longitudinal_covered
    ):
        coverage_reasons.append("longitudinal_decision_without_supported_context")
    unknown_sources = []
    if meta_quality != "usable":
        unknown_sources.append("meta_action")
    if navigation_quality != "usable":
        unknown_sources.append("navigation")
    if scene_quality != "usable":
        unknown_sources.append("scene_facts")
    if meta_quality != "usable":
        status = "unknown"
    elif unknown_sources or not supported or coverage_reasons:
        status = "partial"
    else:
        status = "usable"

    return {
        "structured_causality_format_version": STRUCTURED_CAUSALITY_FORMAT_VERSION,
        "generator_version": GENERATOR_VERSION,
        "rule_version": RULE_VERSION,
        "anchor_id": joined.anchor_id,
        "clip_id": joined.clip_id,
        "anchor_ns": joined.anchor_ns,
        "structured_coc": {"nodes": nodes, "links": links},
        "evidence_refs": {
            "navigation_anchor_id": joined.anchor_id,
            "scene_fact_anchor_id": joined.anchor_id,
            "meta_action_anchor_id": joined.anchor_id,
        },
        "quality": {
            "status": status,
            "source_quality": {
                "navigation": navigation_quality,
                "scene_facts": scene_quality,
                "meta_action": meta_quality,
            },
            "reasons": [f"{name}_quality_unknown" for name in unknown_sources]
            + ([] if supported else ["no_supported_causal_link"])
            + coverage_reasons,
        },
        "source_versions": {
            "navigation_format_version": joined.navigation.get("navigation_format_version"),
            "scene_fact_format_version": joined.scene_fact.get("scene_fact_format_version"),
            "meta_action_format_version": joined.meta_action.get("label_format_version"),
        },
    }
