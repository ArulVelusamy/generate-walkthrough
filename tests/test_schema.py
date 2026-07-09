import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schema" / "walkthrough-model.schema.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(path):
    with open(path) as fh:
        return json.load(fh)


def make_validator():
    schema = load(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)  # raises SchemaError if the schema itself is invalid
    return Draft202012Validator(schema)


def iter_fixtures(subdir):
    d = FIXTURES / subdir
    return sorted(d.glob("*.model.json"))


def test_schema_is_itself_valid():
    make_validator()  # must not raise SchemaError


@pytest.mark.parametrize("path", iter_fixtures("valid"), ids=lambda p: p.name)
def test_valid_fixtures_pass(path):
    errors = list(make_validator().iter_errors(load(path)))
    assert errors == [], f"{path.name} should be valid: {[e.message for e in errors]}"


@pytest.mark.parametrize("path", iter_fixtures("invalid"), ids=lambda p: p.name)
def test_invalid_fixtures_fail(path):
    errors = list(make_validator().iter_errors(load(path)))
    assert errors, f"{path.name} should be rejected but validated clean"
