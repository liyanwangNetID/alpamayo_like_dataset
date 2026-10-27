from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

FORMAT_VERSION = "0.1-draft"
BUILDER_VERSION = "0.1.0"
CAMERA_NAMES = ("front_wide", "front_tele", "cross_left", "cross_right")
FRAME_OFFSETS_NS = (-400_000_000, -200_000_000, 0)


def sample_manifest_schema() -> dict[str, Any]:
    text = {"type": "string", "minLength": 1}
    quality = {"type": "string", "enum": ["usable", "partial", "unknown", "unavailable"]}
    frame = {
        "type": "object",
        "additionalProperties": False,
        "required": ["camera_name", "relative_time_ns", "target_stamp_ns", "frame_stamp_ns", "time_error_ns", "frame_index", "image_path", "width", "height", "encoding", "frame_id"],
        "properties": {
            "camera_name": {"type": "string", "enum": list(CAMERA_NAMES)},
            "relative_time_ns": {"type": "integer", "enum": list(FRAME_OFFSETS_NS)},
            "target_stamp_ns": {"type": "integer", "minimum": 0},
            "frame_stamp_ns": {"type": "integer", "minimum": 0},
            "time_error_ns": {"type": "integer"},
            "frame_index": {"type": "integer", "minimum": 0},
            "image_path": {"type": "string", "minLength": 1, "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$)).+"},
            "width": {"type": "integer", "minimum": 1},
            "height": {"type": "integer", "minimum": 1},
            "encoding": text,
            "frame_id": {"type": "string"},
        },
    }
    history_point = {
        "type": "object",
        "additionalProperties": False,
        "required": ["target_stamp_ns", "relative_x", "relative_y", "sin_relative_yaw", "cos_relative_yaw", "speed", "longitudinal_acceleration", "yaw_rate", "relative_time"],
        "properties": {
            "target_stamp_ns": {"type": "integer", "minimum": 0},
            "relative_x": {"type": "number"}, "relative_y": {"type": "number"},
            "sin_relative_yaw": {"type": "number"}, "cos_relative_yaw": {"type": "number"},
            "speed": {"type": "number"}, "longitudinal_acceleration": {"type": "number"},
            "yaw_rate": {"type": "number"}, "relative_time": {"type": "number"},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "sample_manifest_schema_v0.1-draft.json",
        "title": "AlpaSim self-contained Sample Manifest v0.1-draft",
        "type": "object",
        "additionalProperties": False,
        "required": ["sample_manifest_format_version", "builder_version", "anchor_id", "clip_id", "anchor_ns", "selection", "model_input", "supervision", "optional_auxiliary", "quality", "provenance"],
        "properties": {
            "sample_manifest_format_version": {"const": FORMAT_VERSION},
            "builder_version": {"const": BUILDER_VERSION},
            "anchor_id": text,
            "clip_id": {"type": "string", "pattern": "^test_clip_[0-9]+$"},
            "anchor_ns": {"type": "integer", "minimum": 0},
            "selection": {"type": "object"},
            "model_input": {
                "type": "object", "additionalProperties": False,
                "required": ["visual", "ego_history", "navigation"],
                "properties": {
                    "visual": {
                        "type": "object", "additionalProperties": False,
                        "required": ["visual_profile", "camera_names", "frame_offsets_ns", "visual_sequence_mode", "visual_group_modes", "maximum_camera_skew_ns", "maximum_camera_target_error_ns", "frames"],
                        "properties": {
                            "visual_profile": {"const": "four_camera_three_frame_v0.1"},
                            "camera_names": {"const": list(CAMERA_NAMES)},
                            "frame_offsets_ns": {"const": list(FRAME_OFFSETS_NS)},
                            "visual_sequence_mode": {"const": "all_exact"},
                            "visual_group_modes": {"const": ["exact", "exact", "exact"]},
                            "maximum_camera_skew_ns": {"const": 0},
                            "maximum_camera_target_error_ns": {"const": 0},
                            "frames": {
                                "type": "object", "additionalProperties": False,
                                "required": list(CAMERA_NAMES),
                                "properties": {name: {"type": "array", "minItems": 3, "maxItems": 3, "items": frame} for name in CAMERA_NAMES},
                            },
                        },
                    },
                    "ego_history": {
                        "type": "object", "additionalProperties": False,
                        "required": ["profile", "frame", "point_count", "interval_ns", "span_ns", "points"],
                        "properties": {
                            "profile": {"const": "ego_history_16x10hz_v0.1"},
                            "frame": {"const": "anchor_ego"},
                            "point_count": {"const": 16},
                            "interval_ns": {"const": 100000000},
                            "span_ns": {"const": 1500000000},
                            "points": {"type": "array", "minItems": 16, "maxItems": 16, "items": history_point},
                        },
                    },
                    "navigation": {"type": "object"},
                },
            },
            "supervision": {
                "type": "object", "additionalProperties": False,
                "required": ["driving_decision", "scene_facts", "structured_causality"],
                "properties": {
                    "driving_decision": {"type": "object"},
                    "scene_facts": {"type": "object"},
                    "structured_causality": {"type": "object"},
                },
            },
            "optional_auxiliary": {
                "type": "object", "additionalProperties": False,
                "required": ["reasoning"],
                "properties": {
                    "reasoning": {
                        "type": "object", "additionalProperties": False,
                        "required": ["available", "record", "usage_policy"],
                        "properties": {
                            "available": {"type": "boolean"},
                            "record": {"type": ["object", "null"]},
                            "usage_policy": {
                                "const": {
                                    "authoritative": False,
                                    "default_training_usage": "excluded",
                                    "optional_experimental_usage": "auxiliary_only",
                                    "sample_membership_dependency": False,
                                    "action_target_dependency": False,
                                    "dataset_split_dependency": False,
                                }
                            },
                        },
                    }
                },
            },
            "quality": {
                "type": "object", "additionalProperties": False,
                "required": ["meta_action", "navigation", "scene_facts", "structured_causality", "reasoning"],
                "properties": {key: quality for key in ("meta_action", "navigation", "scene_facts", "structured_causality", "reasoning")},
            },
            "provenance": {
                "type": "object", "additionalProperties": False,
                "required": ["candidate_anchor_record_sha256", "keyframe_record_sha256", "meta_action_record_sha256", "navigation_record_sha256", "scene_fact_record_sha256", "structured_causality_record_sha256", "reasoning_record_sha256"],
                "properties": {key: {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"} for key in ("candidate_anchor_record_sha256", "keyframe_record_sha256", "meta_action_record_sha256", "navigation_record_sha256", "scene_fact_record_sha256", "structured_causality_record_sha256", "reasoning_record_sha256")},
            },
        },
    }


def write_schema(path: Path) -> None:
    schema = sample_manifest_schema()
    Draft202012Validator.check_schema(schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    temporary.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
