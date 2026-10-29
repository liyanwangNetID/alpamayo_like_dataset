from __future__ import annotations

import json
from typing import Any, Mapping

SYSTEM_PROMPT = (
    "Turn the supplied confirmed driving-situation facts into a concise description for "
    "a human reviewer. Every supplied sentence is already a complete confirmed fact. "
    "Preserve the meaning of every supplied fact. Prefer minimal rewriting and keep the "
    "original factual order. Combining facts is optional and should be done only when the "
    "combined sentence cannot introduce a new relationship. Use only the supplied facts. "
    "Do not add explanations, causes, intentions, preparation, compliance, alignment, "
    "deviation, future behavior, absence statements, or conclusions. Do not infer that one "
    "fact explains another. Do not connect facts with because, therefore, since, so, as, "
    "in response to, due to, or similar causal wording unless that relationship is explicitly "
    "written in the supplied facts. Do not add sentences about anything missing, unknown, "
    "unavailable, unclear, not mentioned, not provided, or not confirmed. Do not add a "
    "sentence merely to make the description longer. When only a few facts are supplied, "
    "return an equally short description. Use ordinary driving language. Return only a JSON "
    "object with one field named reasoning_summary. The summary must be no more than five "
    "sentences."
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def build_evidence_package(row: Mapping[str, Any]) -> dict[str, Any]:
    nodes = {node["node_id"]: node for node in row["structured_coc"]["nodes"]}
    decisions: dict[str, dict[str, Any]] = {}
    for name, node_type in (
        ("lateral", "lateral_decision"),
        ("longitudinal", "longitudinal_decision"),
        ("navigation", "navigation_intent"),
    ):
        node = next((item for item in nodes.values() if item["node_type"] == node_type), None)
        if node is not None:
            decisions[name] = dict(node["value"])

    links = []
    for link in row["structured_coc"]["links"]:
        source = nodes[link["source_node_id"]]
        target = nodes[link["target_node_id"]]
        links.append({
            "relation": link["relation"],
            "rule_id": link["rule_id"],
            "source_type": source["node_type"],
            "source": dict(source["value"]),
            "target_type": target["node_type"],
            "target": dict(target["value"]),
        })
    return {
        "record_id": row["anchor_id"],
        "quality_status": row["quality"]["status"],
        "decisions": decisions,
        "links": links,
    }


def llm_situation_payload(package: Mapping[str, Any]) -> dict[str, list[str]]:
    decisions = _mapping(package.get("decisions"))
    facts: list[str] = []

    lateral = _mapping(decisions.get("lateral")).get("action")
    lateral_facts = {
        "keep_direction": "The vehicle is keeping its current direction.",
        "turn_left": "The vehicle is turning left.",
        "turn_right": "The vehicle is turning right.",
        "change_lane_left": "The vehicle is changing lanes to the left.",
        "change_lane_right": "The vehicle is changing lanes to the right.",
    }
    if lateral in lateral_facts:
        facts.append(lateral_facts[str(lateral)])

    longitudinal = _mapping(decisions.get("longitudinal")).get("action")
    longitudinal_facts = {
        "accelerate": "The vehicle is accelerating.",
        "maintain_speed": "The vehicle is maintaining speed.",
        "decelerate": "The vehicle is slowing down.",
        "stop": "The vehicle is stopped.",
    }
    if longitudinal in longitudinal_facts:
        facts.append(longitudinal_facts[str(longitudinal)])

    navigation = _mapping(decisions.get("navigation")).get("action")
    navigation_facts = {
        "straight": "The route continues straight.",
        "left": "The route calls for a left turn ahead.",
        "right": "The route calls for a right turn ahead.",
    }
    if navigation in navigation_facts:
        facts.append(navigation_facts[str(navigation)])

    for link in package.get("links", ()):
        relation = link.get("relation")
        source_type = link.get("source_type")
        source = _mapping(link.get("source"))
        if relation == "stage_consistent" and navigation in {"left", "right"}:
            facts.append("The upcoming turn has not started yet.")
        if relation != "supports" or source_type != "actor_state":
            continue

        actor_name = {
            "automobile": "vehicle",
            "person": "person",
            "rider": "rider",
        }.get(str(source.get("actor_class")), "road user")
        actor_ref = _mapping(source.get("actor_ref"))
        if actor_ref.get("scene_role") == "lead":
            subject = f"A {actor_name} is ahead"
        else:
            position = source.get("relative_position")
            subject = (
                f"A {actor_name} is in the {str(position).replace('_', '-')} relative position"
                if position not in (None, "", "unknown")
                else f"A {actor_name} is nearby"
            )

        details: list[str] = []
        distance = source.get("relative_distance")
        if distance not in (None, "", "unknown"):
            details.append(f"at a {distance} distance")
        motion = {
            "stationary": "stationary",
            "slower_than_ego": "moving slower than the vehicle",
            "faster_than_ego": "moving faster than the vehicle",
            "similar_speed": "moving at a similar speed",
        }.get(str(source.get("relative_speed_category")))
        if motion:
            details.append(motion)
        lane_direction = source.get("lane_direction_relation")
        if lane_direction == "same_direction":
            details.append("traveling in the same direction")
        elif lane_direction == "opposing":
            details.append("traveling in the opposite direction")
        trend = {
            "stable_distance": "with a stable separation",
            "approaching": "with the separation decreasing",
            "receding": "with the separation increasing",
        }.get(str(source.get("distance_trend")))
        if trend:
            details.append(trend)
        facts.append(subject + (", " + ", ".join(details) if details else "") + ".")

    return {"confirmed_facts": facts}


def user_prompt(package: Mapping[str, Any]) -> str:
    instruction = (
        "Combine or lightly rephrase only these confirmed facts. Do not add any sentence "
        "about missing information or anything not listed. Return only JSON with the single "
        "field reasoning_summary."
    )
    payload = json.dumps(
        llm_situation_payload(package),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return chr(10).join((instruction, payload))
