from jsonschema import Draft202012Validator
from step11.schema import dataset_split_schema


def test_schema_is_valid_and_has_three_splits():
    schema = dataset_split_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["split"]["enum"] == ["train", "validation", "test"]
