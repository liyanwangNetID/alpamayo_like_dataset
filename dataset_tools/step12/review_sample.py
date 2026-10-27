#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any
import cv2

from project_paths import ALPASIM_DATA_ROOT, MANIFEST_ROOT, REPORT_ROOT
from step7.review_scene_fact import create_review_video, letterbox

SAMPLE = MANIFEST_ROOT / "sample_manifest_v0.1.jsonl"
SPLIT = MANIFEST_ROOT / "dataset_split_v0.1.jsonl"
OUTPUT_ROOT = REPORT_ROOT / "step12_review"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle: return [json.loads(line) for line in handle if line.strip()]


def matches(row, args, split):
    if args.split and split != args.split: return False
    decision = row["supervision"]["driving_decision"]["joint_action"]
    if args.lateral_action and decision["lateral"] != args.lateral_action: return False
    if args.longitudinal_action and decision["longitudinal"] != args.longitudinal_action: return False
    if args.navigation_action and row["model_input"]["navigation"]["navigation"]["action"] != args.navigation_action: return False
    if args.road_context and row["supervision"]["scene_facts"]["road_context"]["type"] != args.road_context: return False
    if args.coc_quality and row["quality"]["structured_causality"] != args.coc_quality: return False
    return True


def print_section(title, value):
    print("\n" + "=" * 88); print(title); print("=" * 88)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False))


def overview(row, output: Path):
    visual = row["model_input"]["visual"]
    panel_w, panel_h = 480, 270
    time_rows = []
    for index, offset in enumerate(visual["frame_offsets_ns"]):
        panels = []
        for camera in visual["camera_names"]:
            path = ALPASIM_DATA_ROOT / visual["frames"][camera][index]["image_path"]
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None: raise RuntimeError(f"unable to read image: {path}")
            image = letterbox(image, panel_w, panel_h)
            cv2.rectangle(image, (0, 0), (panel_w, 34), (0, 0, 0), -1)
            cv2.putText(image, f"{camera}  t={offset/1e9:+.1f}s", (8, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1, cv2.LINE_AA)
            panels.append(image)
        time_rows.append(cv2.hconcat(panels))
    grid = cv2.vconcat(time_rows)
    info_h = 280
    canvas = cv2.copyMakeBorder(grid, 0, info_h, 0, 0, cv2.BORDER_CONSTANT, value=(250,250,250))
    nav = row["model_input"]["navigation"]["navigation"]
    action = row["supervision"]["driving_decision"]["joint_action"]
    scene = row["supervision"]["scene_facts"]
    coc = row["supervision"]["structured_causality"]
    lines = [
        f"Anchor: {row['anchor_id']}   Clip: {row['clip_id']}",
        f"Navigation: {nav['action']} | {nav.get('text')}",
        f"Decision: lateral={action['lateral']}  longitudinal={action['longitudinal']}",
        f"Road context: {scene['road_context']['type']} | Scene quality: {scene['quality']['status']} | CoC quality: {coc['quality']['status']}",
    ]
    for link in coc["structured_coc"]["links"][:4]:
        lines.append(f"CoC: {link['source_node_id']} --{link['relation']}/{link['confidence']}--> {link['target_node_id']}")
    y = grid.shape[0] + 40
    for line in lines:
        cv2.putText(canvas, line[:150], (16, y), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0,0,0), 1, cv2.LINE_AA); y += 35
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), canvas): raise RuntimeError(f"unable to write overview: {output}")


def main() -> int:
    p = argparse.ArgumentParser(description="Generate a complete visual human-review bundle for one Step 10 sample.")
    p.add_argument("--anchor-id"); p.add_argument("--split", choices=("train","validation","test")); p.add_argument("--seed", type=int, default=12)
    p.add_argument("--lateral-action"); p.add_argument("--longitudinal-action"); p.add_argument("--navigation-action"); p.add_argument("--road-context"); p.add_argument("--coc-quality", choices=("usable","partial","unknown"))
    p.add_argument("--pre-sec", type=float, default=3.0); p.add_argument("--post-sec", type=float, default=3.0); p.add_argument("--fps", type=float, default=10.0); p.add_argument("--force", action="store_true"); p.add_argument("--no-video", action="store_true")
    args = p.parse_args()
    samples = read_jsonl(SAMPLE); split_by_id = {row["anchor_id"]: row["split"] for row in read_jsonl(SPLIT)}
    if args.anchor_id:
        selected = next((row for row in samples if row["anchor_id"] == args.anchor_id), None)
        if selected is None: raise KeyError(f"anchor not found: {args.anchor_id}")
    else:
        candidates = [row for row in samples if matches(row, args, split_by_id[row["anchor_id"]])]
        if not candidates: raise ValueError("no sample matches the requested filters")
        selected = random.Random(args.seed).choice(candidates)
    split = split_by_id[selected["anchor_id"]]
    out = OUTPUT_ROOT / selected["anchor_id"]
    out.mkdir(parents=True, exist_ok=True)
    bundle_path = out / "review_bundle.json"; decision_path = out / "review_decision.json"; overview_path = out / "sample_overview.png"; video_path = out / "synchronized_context.mp4"
    print_section("IDENTITY AND SPLIT", {"anchor_id": selected["anchor_id"], "clip_id": selected["clip_id"], "anchor_ns": selected["anchor_ns"], "split": split, "selection": selected["selection"]})
    print_section("VISUAL INPUT", selected["model_input"]["visual"])
    print_section("EGO HISTORY", selected["model_input"]["ego_history"])
    print_section("NAVIGATION INPUT", selected["model_input"]["navigation"])
    print_section("DRIVING DECISION TARGET", selected["supervision"]["driving_decision"])
    print_section("SCENE FACTS", selected["supervision"]["scene_facts"])
    print_section("STRUCTURED COC", selected["supervision"]["structured_causality"])
    print_section("OPTIONAL REASONING - NON-AUTHORITATIVE, DEFAULT TRAINING EXCLUDED", selected["optional_auxiliary"]["reasoning"])
    print_section("QUALITY AND PROVENANCE", {"quality": selected["quality"], "provenance": selected["provenance"]})
    overview(selected, overview_path)
    if not args.no_video:
        scene = {"anchor_id": selected["anchor_id"], "clip_id": selected["clip_id"], "anchor_ns": selected["anchor_ns"], **selected["supervision"]["scene_facts"]}
        create_review_video(scene, dataset_root=ALPASIM_DATA_ROOT, output_path=video_path, pre_seconds=args.pre_sec, post_seconds=args.post_sec, fps=args.fps, panel_width=640, panel_height=360, force=args.force)
    bundle = {"anchor_id": selected["anchor_id"], "split": split, "sample": selected, "generated_outputs": {"video": str(video_path) if not args.no_video else None, "overview_image": str(overview_path)}, "review_selection": {"seed": args.seed, "filters": {key: value for key, value in vars(args).items() if value not in (None, False)}}}
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not decision_path.exists() or args.force:
        decision = {"anchor_id": selected["anchor_id"], "review_status": "pending", "visual_alignment": None, "navigation_consistency": None, "action_consistency": None, "scene_fact_consistency": None, "structured_coc_consistency": None, "reasoning_consistency": None, "issues": [], "reviewer_notes": ""}
        decision_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print_section("GENERATED REVIEW ARTIFACTS", {"overview": str(overview_path), "video": str(video_path) if not args.no_video else None, "bundle": str(bundle_path), "review_decision": str(decision_path)})
    print("PASS: Step 12 visual human-review bundle generated.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
