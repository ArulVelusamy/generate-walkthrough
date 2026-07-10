import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))
sys.path.insert(0, str(ROOT / "tests"))

from serialize import serialize
from test_schema import make_validator
from openapi_spec_validator import validate

AWS = ROOT / "tests" / "fixtures" / "valid" / "aws-api.model.json"


def load(p):
    with open(p) as fh:
        return json.load(fh)


def test_fixture_is_a_valid_sidecar():
    errors = list(make_validator().iter_errors(load(AWS)))
    assert errors == [], [e.message for e in errors]


def test_openapi_models_aws_native_features(tmp_path):
    serialize(load(AWS), str(tmp_path))
    doc = load(tmp_path / "PaymentsAPI-openapi.json")
    validate(doc)
    # array + object element + enum + format present somewhere in components
    dumped = json.dumps(doc)
    assert '"type": "array"' in dumped
    assert '"enum"' in dumped
    assert '"format": "date-time"' in dumped or '"format": "uuid"' in dumped
    # apiKey scheme emitted (NOT dropped to none) and cognito oauth2 with scopes
    schemes = doc["components"]["securitySchemes"]
    assert any(s["type"] == "apiKey" for s in schemes.values())
    assert any(s["type"] == "oauth2" for s in schemes.values())
    assert any("write" in scope for methods in doc["paths"].values() for op in methods.values()
               for req in op.get("security", []) for scopes in req.values() for scope in scopes)


def test_sigv4_is_a_documented_gap_not_a_scheme(tmp_path):
    serialize(load(AWS), str(tmp_path))
    doc = load(tmp_path / "PaymentsAPI-openapi.json")
    assert any("SigV4" in g for g in doc.get("x-coverage-gaps", []))


def test_aws_calls_rendered_and_absent_from_openapi(tmp_path):
    serialize(load(AWS), str(tmp_path))
    md = (tmp_path / "PaymentsAPI-aws-calls.md").read_text()
    assert "PutItem" in md and "GetObject" in md
    doc = json.dumps(load(tmp_path / "PaymentsAPI-openapi.json"))
    assert "PutItem" not in doc and "GetObject" not in doc   # AWS calls never leak into OpenAPI
