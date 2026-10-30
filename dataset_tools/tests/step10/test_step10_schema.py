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


def test_schema_freezes_summary_only_reasoning_v012():
    schema = sample_manifest_schema()
    assert schema["properties"]["builder_version"]["const"] == "0.2.0"
    reasoning = (
        schema["properties"]["optional_auxiliary"]
        ["properties"]["reasoning"]
        ["properties"]["record"]
        ["oneOf"][0]
    )
    assert reasoning["additionalProperties"] is False
    assert set(reasoning["required"]) == {
        "reasoning_format_version",
        "generator_version",
        "prompt_version",
        "reasoning_summary",
        "quality_status",
        "source_record_sha256",
    }
    assert reasoning["properties"]["reasoning_format_version"]["const"] == "0.2-draft"
    assert reasoning["properties"]["generator_version"]["const"] == "0.3.0"
    assert reasoning["properties"]["prompt_version"]["const"] == "step9_minimal_rewrite_prompt_v0.12"
    serialized = str(reasoning)
    assert "used_evidence_keys" not in serialized
    assert "limitations" not in serialized
