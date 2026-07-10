import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))

from openapi_render import render_openapi
from openapi_spec_validator import validate  # raises on invalid


def minimal_sidecar():
    return {
        "schema_version": "1.0",
        "project": {"name": "Demo", "version": "1.2.3"},
        "endpoints": [{
            "id": "post_create", "operationId": "createThing", "group": "Things", "in_journey": True,
            "method": "POST", "path": "/things", "source_path": "/things", "summary": "Create a thing",
            "handler": {"file": "a.py", "symbol": "create"},
            "auth": [{"scheme_name": "apikey", "kind": "apiKey", "in": "header", "name": "x-api-key"}],
            "request": {"media_type": "application/json", "path_params": [], "query_params": [], "headers": [],
                        "body": {"grounded": True, "schema": {"name": "root", "type": "object",
                                 "properties": [{"name": "title", "type": "string", "required": True}]}, "gap": None}},
            "responses": [{"status": 201, "description": "Created", "headers": [
                            {"name": "Location", "type": "string"}], "content": [
                            {"media_type": "application/json", "body": {"grounded": True, "schema": {
                                "name": "root", "type": "object", "properties": [{"name": "id", "type": "integer"}]},
                                "gap": None}}], "anchor": {"file": "a.py", "symbol": "create"}}]
        }]
    }


def test_openapi_is_valid_303():
    doc = render_openapi(minimal_sidecar())
    validate(doc)  # raises if not valid OpenAPI 3.0.3
    assert doc["openapi"] == "3.0.3"
    assert doc["info"] == {"title": "Demo", "version": "1.2.3"}


def test_operation_shape_and_refs():
    doc = render_openapi(minimal_sidecar())
    op = doc["paths"]["/things"]["post"]
    assert op["operationId"] == "createThing"
    assert op["tags"] == ["Things"]
    assert op["requestBody"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/createThingRequest"}
    resp = op["responses"]["201"]
    assert resp["description"] == "Created"
    assert resp["headers"]["Location"]["schema"] == {"type": "string"}
    assert resp["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/createThingResponse201"}
    assert op["security"] == [{"apikey": []}]
    assert doc["components"]["securitySchemes"]["apikey"]["type"] == "apiKey"
    assert "createThingRequest" in doc["components"]["schemas"]


def test_servers_placeholder():
    doc = render_openapi(minimal_sidecar())
    assert doc["servers"][0]["url"] == "{baseUrl}"
    assert doc["servers"][0]["variables"]["baseUrl"]["default"]


def test_gap_becomes_empty_schema_and_coverage_list():
    s = minimal_sidecar()
    s["endpoints"][0]["responses"][0]["content"][0]["body"] = {"grounded": False, "schema": None, "gap": "not modeled"}
    doc = render_openapi(s)
    schema = doc["paths"]["/things"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]
    assert schema == {"description": "not modeled"}   # {} + description marker, no invented fields
    assert any("not modeled" in g for g in doc["x-coverage-gaps"])


def test_empty_auth_has_no_security_key():
    s = minimal_sidecar()
    s["endpoints"][0]["auth"] = []
    doc = render_openapi(s)
    assert "security" not in doc["paths"]["/things"]["post"]


def test_grounded_false_request_body_records_gap():
    s = minimal_sidecar()
    s["endpoints"][0]["request"]["body"] = {"grounded": False, "schema": None, "gap": "form fields not modeled"}
    doc = render_openapi(s)
    op = doc["paths"]["/things"]["post"]
    assert op["requestBody"]["content"]["application/json"]["schema"] == {"description": "form fields not modeled"}
    assert any("form fields not modeled" in g for g in doc["x-coverage-gaps"])
