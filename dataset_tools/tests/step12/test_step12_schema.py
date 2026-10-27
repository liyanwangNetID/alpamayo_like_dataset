from jsonschema import Draft202012Validator
from step12.schema import final_audit_schema

def test_final_audit_schema_is_valid(): Draft202012Validator.check_schema(final_audit_schema())
