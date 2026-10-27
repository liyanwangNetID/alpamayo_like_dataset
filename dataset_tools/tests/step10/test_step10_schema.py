from jsonschema import Draft202012Validator
from step10.schema import FRAME_OFFSETS_NS, sample_manifest_schema


def test_schema_is_valid_and_freezes_three_frames():
    schema = sample_manifest_schema()
    Draft202012Validator.check_schema(schema)
    visual = schema["properties"]["model_input"]["properties"]["visual"]
    assert visual["properties"]["frame_offsets_ns"]["const"] == list(FRAME_OFFSETS_NS)
    frames = visual["properties"]["frames"]["properties"]
    assert set(frames) == {"front_wide", "front_tele", "cross_left", "cross_right"}
    assert all(value["minItems"] == value["maxItems"] == 3 for value in frames.values())


def test_schema_has_no_sample_id_or_static_occupancy():
    text = str(sample_manifest_schema())
    assert "sample_id" not in text
    assert "static_occupancy" not in text
