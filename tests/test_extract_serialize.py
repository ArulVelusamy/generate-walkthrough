import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))

from serialize import serialize, render_aws_calls
from openapi_spec_validator import validate

FLASKR = ROOT / "tests" / "fixtures" / "valid" / "flaskr.model.json"


def load(p):
    with open(p) as fh:
        return json.load(fh)


def test_aws_calls_empty_note():
    md = render_aws_calls({"aws_calls": []})
    assert "No AWS" in md or "no AWS" in md


def test_aws_calls_table():
    md = render_aws_calls({"aws_calls": [
        {"service": "DynamoDB", "operation": "PutItem", "resource": {"table": "Ledger", "keys": ["pk", "sk"]},
         "purpose": "persist", "anchor": {"file": "db.py", "symbol": "put"}}]})
    assert "DynamoDB" in md and "PutItem" in md and "Ledger" in md


def test_aws_calls_escapes_pipe_in_cell():
    # a value containing '|' must be escaped so it can't break the Markdown table row
    md = render_aws_calls({"aws_calls": [
        {"service": "S3", "operation": "GetObject", "resource": {"key": "a|b"},
         "purpose": "read a|b", "anchor": {"file": "x.py", "symbol": "f"}}]})
    assert "a\\|b" in md and "read a\\|b" in md         # inner pipes escaped
    row = next(ln for ln in md.splitlines() if ln.startswith("| S3"))
    assert row.replace("\\|", "").count("|") == 6      # once escaped pipes removed: 5 cells -> 6 delimiters


def test_serialize_flaskr_writes_four_files(tmp_path):
    written = serialize(load(FLASKR), str(tmp_path))
    names = {Path(p).name for p in written}
    assert names == {"Flaskr-openapi.json", "Flaskr.postman_collection.json",
                     "Flaskr.postman_environment.json", "Flaskr-aws-calls.md"}


def test_flaskr_openapi_valid_and_no_invention(tmp_path):
    serialize(load(FLASKR), str(tmp_path))
    doc = load(tmp_path / "Flaskr-openapi.json")
    validate(doc)
    op_count = sum(len([m for m in methods]) for methods in doc["paths"].values())
    assert op_count == len(load(FLASKR)["endpoints"])   # no invention: 1:1 operations<->endpoints
    # no synthesized 401 anywhere
    statuses = [code for methods in doc["paths"].values() for op in methods.values() for code in op["responses"]]
    assert "401" not in statuses


def test_duplicate_operation_id_is_rejected(tmp_path):
    # two endpoints sharing an operationId would silently overwrite a component schema;
    # the no-invention self-check must reject it rather than emit a cross-wired spec.
    s = load(FLASKR)
    s["endpoints"][1]["operationId"] = s["endpoints"][0]["operationId"]
    with pytest.raises(ValueError):
        serialize(s, str(tmp_path))


def test_determinism_byte_identical(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    serialize(load(FLASKR), str(a))
    serialize(load(FLASKR), str(b))
    for name in ["Flaskr-openapi.json", "Flaskr.postman_collection.json",
                 "Flaskr.postman_environment.json", "Flaskr-aws-calls.md"]:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name
