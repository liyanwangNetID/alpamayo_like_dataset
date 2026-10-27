from pathlib import Path

from step4.build_meta_actions_v02 import step4_feature_commands


def test_force_is_propagated_to_every_step4_feature_stage():
    commands = step4_feature_commands(force=True)
    assert len(commands) == 5
    assert all("--force" in command for command in commands)
    assert "--all" in commands[-1]


def test_lane_change_profiler_uses_step2_package_imports():
    path = Path(__file__).resolve().parents[2] / "step4" / "profile_lane_change_geometry_features.py"
    text = path.read_text(encoding="utf-8")
    assert "from step2.clip_reader import DrivingClipReader" in text
    assert "from step2.vector_map_reader import VectorMapReader" in text
    assert "from clip_reader import DrivingClipReader" not in text
    assert "from vector_map_reader import VectorMapReader" not in text
    assert "from step4.lane_matcher import" in text
    assert "from lane_matcher import" not in text
