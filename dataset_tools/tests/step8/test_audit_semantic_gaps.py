from step8.audit_semantic_gaps import classify
class Joined:
    anchor_id="test_clip_001_10"; clip_id="test_clip_001"; anchor_ns=10
    navigation={"navigation":{"action":"straight","quality_status":"usable"}}
    meta_action={"longitudinal":{"action":"decelerate","quality_status":"usable"},"lateral":{"action":"keep_direction","quality_status":"usable"}}
    scene_fact={"road_context":{"type":"lane_following","intersection_proximity":"none","stop_line_proximity":"none","yield_line_proximity":"none"},"actor_context":{"lead_actors":[{"quality_status":"usable","lane_direction_relation":"same_direction","relative_speed_category":"slower_than_ego","relative_distance":"far","role_rank":1,"track_id":"18"}],"left_nearby_actors":[],"right_nearby_actors":[]}}
def record(actor=False):
    nodes=[{"node_id":"navigation_intent","node_type":"navigation_intent"},{"node_id":"decision_longitudinal","node_type":"longitudinal_decision"},{"node_id":"decision_lateral","node_type":"lateral_decision"}]
    links=[{"source_node_id":"navigation_intent","target_node_id":"decision_lateral","confidence":"supported"}]
    if actor:
        nodes.append({"node_id":"actor_lead_1","node_type":"actor_state"}); links.append({"source_node_id":"actor_lead_1","target_node_id":"decision_longitudinal","confidence":"supported"})
    return {"structured_coc":{"nodes":nodes,"links":links}}
def test_far_slower_lead_gap_is_detected():
    flags=classify(Joined(),record(False)); assert "far_slower_lead_without_longitudinal_link" in flags; assert "longitudinal_response_with_leads_but_no_actor_link" in flags
def test_existing_actor_link_removes_far_lead_gap():
    flags=classify(Joined(),record(True)); assert "far_slower_lead_without_longitudinal_link" not in flags; assert "longitudinal_response_with_leads_but_no_actor_link" not in flags
