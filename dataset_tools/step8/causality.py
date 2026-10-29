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

    navigation_reasons = {
        str(value) for value in navigation.get("reasons", ())
    }
    road_type = str(road_context.get("type", "unknown"))
    road_quality = _quality(road_context.get("quality_status"))
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

    list_specs = (
        ("lead_actors", "lead"),
        ("left_nearby_actors", "left"),
        ("right_nearby_actors", "right"),
    )
    for list_name, role in list_specs:
        actors = actor_context.get(list_name, [])
        if not isinstance(actors, list):
            continue
        for actor in actors:
            if not isinstance(actor, Mapping):
                continue
            rank = actor.get("role_rank")
            node_id = f"actor_{role}_{rank}"
            relation_data = (
                _lead_relation(actor, longitudinal)
                if role == "lead"
                else _side_relation(actor, lateral, role)
            )
            if relation_data is None:
                continue
            nodes.append(
                _node(
                    node_id,
                    "actor_state",
                    {
                        "actor_ref": _actor_ref(actor, role),
                        "actor_class": actor.get("actor_class"),
                        "relative_position": actor.get("relative_position"),
                        "relative_distance": actor.get("relative_distance"),
                        "distance_trend": actor.get("distance_trend"),
                        "relative_speed_category": actor.get("relative_speed_category"),
                        "lane_direction_relation": actor.get("lane_direction_relation", "unknown"),
                        "quality_status": _quality(actor.get("quality_status")),
                    },
                    "scene_facts.jsonl",
                )
            )
            rel, conf, rule, why = relation_data
            target = "decision_longitudinal" if role == "lead" else "decision_lateral"
            links.append(_link(f"link_{node_id}_{target}", node_id, target, rel, conf, rule, why))

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
    unknown_sources = []
    if meta_quality != "usable":
        unknown_sources.append("meta_action")
    if navigation_quality != "usable":
        unknown_sources.append("navigation")
    if scene_quality != "usable":
        unknown_sources.append("scene_facts")
    if meta_quality != "usable":
        status = "unknown"
    elif unknown_sources or not supported:
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
            + ([] if supported else ["no_supported_causal_link"]),
        },
        "source_versions": {
            "navigation_format_version": joined.navigation.get("navigation_format_version"),
            "scene_fact_format_version": joined.scene_fact.get("scene_fact_format_version"),
            "meta_action_format_version": joined.meta_action.get("label_format_version"),
        },
    }
