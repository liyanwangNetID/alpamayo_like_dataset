#!/usr/bin/env python3
"""Read-only semantic-gap audit for frozen Step 8 Structured CoC."""
from __future__ import annotations
import argparse, json, random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping
from step8.contract import Step8Paths, load_and_validate_inputs

def mapping(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}

def read_formal(path: Path):
    rows = {}
    with path.open("r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip(): continue
            row = json.loads(line); aid = row.get("anchor_id")
            if not isinstance(aid, str) or not aid: raise ValueError(f"{path}:{n}: invalid anchor_id")
            if aid in rows: raise ValueError(f"{path}:{n}: duplicate anchor_id {aid}")
            rows[aid] = row
    return rows

def actor_links(record, target=None):
    nodes = record["structured_coc"]["nodes"]
    actor_ids = {n["node_id"] for n in nodes if n["node_type"] == "actor_state"}
    return [l for l in record["structured_coc"]["links"] if l["source_node_id"] in actor_ids and (target is None or l["target_node_id"] == target)]

def classify(joined, record):
    flags = set(); scene = joined.scene_fact
    ctx = mapping(scene.get("actor_context")); road = mapping(scene.get("road_context"))
    lon = str(mapping(joined.meta_action.get("longitudinal")).get("action", "unknown"))
    lat = str(mapping(joined.meta_action.get("lateral")).get("action", "unknown"))
    leads = [a for a in ctx.get("lead_actors", []) if isinstance(a, Mapping)]
    left = [a for a in ctx.get("left_nearby_actors", []) if isinstance(a, Mapping)]
    right = [a for a in ctx.get("right_nearby_actors", []) if isinstance(a, Mapping)]
    lon_links = actor_links(record, "decision_longitudinal")
    restrictive = [a for a in leads if a.get("quality_status") == "usable" and a.get("lane_direction_relation") == "same_direction" and a.get("relative_speed_category") in {"slower_than_ego", "stationary"}]
    far = [a for a in restrictive if a.get("relative_distance") == "far"]
    near_med = [a for a in restrictive if a.get("relative_distance") in {"near", "medium"}]
    if lon in {"decelerate", "stop"} and far and not lon_links: flags.add("far_slower_lead_without_longitudinal_link")
    if lon in {"decelerate", "stop"} and near_med and not lon_links: flags.add("near_medium_slower_lead_without_longitudinal_link")
    if lon in {"decelerate", "stop"} and len(lon_links) >= 2: flags.add("multiple_lead_actors_linked_to_one_longitudinal_decision")
    if lon in {"decelerate", "stop"} and leads and not lon_links: flags.add("longitudinal_response_with_leads_but_no_actor_link")
    if lon in {"decelerate", "stop"} and not leads: flags.add("longitudinal_response_without_lead_actor")
    relevant_road = str(road.get("type", "unknown")) == "intersection_approach" or any(str(road.get(k, "none")) not in {"none", "unknown"} for k in ("intersection_proximity", "stop_line_proximity", "yield_line_proximity"))
    if lon in {"decelerate", "stop"} and relevant_road: flags.add("longitudinal_response_with_relevant_road_context")
    if lat in {"turn_left", "change_lane_left"} and left: flags.add("left_action_with_left_side_actors")
    if lat in {"turn_left", "change_lane_left"} and right: flags.add("left_action_with_right_side_actors")
    if lat in {"turn_right", "change_lane_right"} and left: flags.add("right_action_with_left_side_actors")
    if lat in {"turn_right", "change_lane_right"} and right: flags.add("right_action_with_right_side_actors")
    if lat == "keep_direction" and any(a.get("relative_distance") == "near" for a in left + right): flags.add("keep_direction_with_near_side_actor")
    if not any(l.get("confidence") == "supported" for l in record["structured_coc"]["links"]): flags.add("no_supported_link")
    return flags

def summary_row(joined, record, flags):
    ctx = mapping(joined.scene_fact.get("actor_context"))
    return {"anchor_id": joined.anchor_id, "clip_id": joined.clip_id, "anchor_ns": joined.anchor_ns, "flags": sorted(flags), "navigation": mapping(joined.navigation.get("navigation")), "longitudinal": mapping(joined.meta_action.get("longitudinal")), "lateral": mapping(joined.meta_action.get("lateral")), "road_context": mapping(joined.scene_fact.get("road_context")), "lead_actors": ctx.get("lead_actors", []), "left_nearby_actors": ctx.get("left_nearby_actors", []), "right_nearby_actors": ctx.get("right_nearby_actors", []), "structured_coc": record["structured_coc"], "step8_quality": record["quality"]}

def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--data-root", type=Path); p.add_argument("--formal-output", type=Path); p.add_argument("--output", type=Path); p.add_argument("--examples-per-flag", type=int, default=12); p.add_argument("--seed", type=int, default=20261102); a = p.parse_args()
    if a.examples_per_flag < 1: raise SystemExit("--examples-per-flag must be >= 1")
    paths = Step8Paths.from_data_root(a.data_root); formal_path = a.formal_output or paths.data_root / "annotations/v0.1-draft/structured_causality.jsonl"; output = a.output or paths.data_root / "reports/step8_semantic_gap_audit_v01.json"
    joined, provenance = load_and_validate_inputs(paths); formal = read_formal(formal_path)
    if set(formal) != {r.anchor_id for r in joined}: raise ValueError("formal Step 8 Anchors do not close to frozen joined inputs")
    counts = Counter(); candidates = defaultdict(list)
    for row in joined:
        flags = classify(row, formal[row.anchor_id]); item = summary_row(row, formal[row.anchor_id], flags)
        for flag in flags: counts[flag] += 1; candidates[flag].append(item)
    rng = random.Random(a.seed); examples = {}
    for flag, rows in sorted(candidates.items()):
        rows = sorted(rows, key=lambda x: x["anchor_id"])
        if len(rows) > a.examples_per_flag: rows = sorted(rng.sample(rows, a.examples_per_flag), key=lambda x: x["anchor_id"])
        examples[flag] = rows
    report = {"report_format_version": "0.1-draft", "read_only": True, "record_count": len(joined), "seed": a.seed, "examples_per_flag": a.examples_per_flag, "input_provenance": provenance, "formal_step8_path": str(formal_path), "flag_counts": dict(sorted(counts.items())), "examples": examples}
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[Step 8 gap audit] records: {len(joined)}"); print(f"[Step 8 gap audit] flag_counts: {dict(sorted(counts.items()))}"); print(f"[Step 8 gap audit] report: {output}"); return 0
if __name__ == "__main__": raise SystemExit(main())
