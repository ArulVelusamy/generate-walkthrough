import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))

from postman_render import render_postman


def sidecar():
    return {
        "schema_version": "1.0",
        "project": {"name": "Demo", "version": "1.2.3"},
        "endpoints": [
            {"id": "post_update", "operationId": "updateThing", "group": "Things", "in_journey": True,
             "method": "POST", "path": "/things/{id}/update", "source_path": "/things/<int:id>/update",
             "summary": "Update", "handler": {"file": "a.py", "symbol": "u"},
             "auth": [{"scheme_name": "bearer", "kind": "http", "scheme": "bearer"}],
             "request": {"media_type": "application/x-www-form-urlencoded",
                         "path_params": [{"name": "id", "type": "integer", "required": True}],
                         "query_params": [], "headers": [],
                         "body": {"grounded": True, "schema": {"name": "root", "type": "object",
                                  "properties": [{"name": "title", "type": "string", "required": True}]}, "gap": None}},
             "responses": [{"status": 302, "description": "redirect", "content": [],
                            "anchor": {"file": "a.py", "symbol": "u"}}]},
        ],
    }


def test_collection_schema_and_info():
    coll, env = render_postman(sidecar())
    assert coll["info"]["schema"] == "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    assert coll["info"]["name"] == "Demo"


def test_folder_by_group_with_request():
    coll, _ = render_postman(sidecar())
    folders = {it["name"]: it for it in coll["item"]}
    assert "Things" in folders
    req = folders["Things"]["item"][0]
    assert req["request"]["method"] == "POST"


def test_path_variable_and_url():
    coll, _ = render_postman(sidecar())
    url = coll["item"][0]["item"][0]["request"]["url"]
    assert url["path"] == ["things", ":id", "update"]
    assert {"key": "id"} in [{"key": v["key"]} for v in url["variable"]]
    assert url["host"] == ["{{baseUrl}}"]


def test_urlencoded_body_mode():
    coll, _ = render_postman(sidecar())
    body = coll["item"][0]["item"][0]["request"]["body"]
    assert body["mode"] == "urlencoded"
    assert any(kv["key"] == "title" for kv in body["urlencoded"])


def test_bearer_auth_uses_token_var_and_environment_has_baseurl():
    coll, env = render_postman(sidecar())
    req = coll["item"][0]["item"][0]["request"]
    assert req["auth"]["type"] == "bearer"
    keys = {v["key"] for v in env["values"]}
    assert "baseUrl" in keys and "token" in keys
