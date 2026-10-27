from step12.audit_dataset import dimensions

def test_dimensions_ignore_reasoning_for_split_statistics():
    row = {"supervision": {"driving_decision": {"joint_action": {"lateral": "keep_direction", "longitudinal": "stop"}}, "scene_facts": {"road_context": {"type": "intersection"}}}, "model_input": {"navigation": {"navigation": {"action": "straight"}}}, "quality": {"meta_action": "usable", "navigation": "usable", "scene_facts": "usable", "structured_causality": "partial", "reasoning": "unknown"}}
    result = dimensions(row)
    assert result["lateral"] == "keep_direction"
    assert result["structured_coc_quality"] == "partial"
