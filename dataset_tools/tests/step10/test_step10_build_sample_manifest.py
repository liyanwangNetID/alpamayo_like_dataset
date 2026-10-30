from pathlib import Path
from types import SimpleNamespace

from step10.build_sample_manifest import build_history, build_visual


def test_builder_uses_three_frames_and_relative_paths(tmp_path):
    data_root = tmp_path / "data"
    image = data_root / "test_clip_001" / "cameras" / "front_wide" / "000001.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"x")
    names = ("front_wide", "front_tele", "cross_left", "cross_right")
    groups = []
    for offset in (-400000000, -200000000, 0):
        matches = {}
        for name in names:
            value = SimpleNamespace(camera_name=name, frame_index=1, stamp_ns=1000 + offset, frame_id=name, width=10, height=10, encoding="jpeg", image_path=(data_root / "test_clip_001" / "cameras" / name / "000001.jpg"))
            value.image_path.parent.mkdir(parents=True, exist_ok=True)
            value.image_path.write_bytes(b"x")
            matches[name] = SimpleNamespace(timestamp_ns=1000 + offset, error_ns=0, value=value)
        groups.append(SimpleNamespace(target_ns=1000 + offset, mode="exact", matches=matches, maximum_skew_ns=0, maximum_target_error_ns=0))
    reader = SimpleNamespace(get_multicamera_frames=lambda *args, **kwargs: SimpleNamespace(groups=tuple(groups)))
    candidate = {"anchor_id": "a", "anchor_ns": 1000, "frame_offsets_ns": [-400000000, -200000000, 0], "visual_group_modes": ["exact", "exact", "exact"], "visual_sequence_mode": "all_exact", "maximum_camera_skew_ns": 0, "maximum_camera_target_error_ns": 0, "visual_profile": "four_camera_three_frame_v0.1"}
    visual = build_visual(reader, candidate, data_root)
    assert all(len(visual["frames"][name]) == 3 for name in names)
    assert all(not Path(item["image_path"]).is_absolute() for values in visual["frames"].values() for item in values)


def test_history_is_complete():
    points = tuple(SimpleNamespace(target_stamp_ns=i, relative_x=0.0, relative_y=0.0, sin_relative_yaw=0.0, cos_relative_yaw=1.0, speed=0.0, longitudinal_acceleration=0.0, yaw_rate=0.0, relative_time=float(i)) for i in range(16))
    reader = SimpleNamespace(get_ego_history=lambda *args, **kwargs: points, ego_history_to_dicts=lambda values: [vars(value) for value in values])
    value = build_history(reader, {"anchor_id": "a", "anchor_ns": 15, "ego_history_profile": "ego_history_16x10hz_v0.1"})
    assert value["point_count"] == 16
    assert len(value["points"]) == 16


def test_builder_version_is_v020():
    from step10.schema import BUILDER_VERSION

    assert BUILDER_VERSION == "0.2.0"
