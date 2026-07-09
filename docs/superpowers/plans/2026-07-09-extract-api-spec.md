# extract-api-spec Extractor (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `extract-api-spec` skill whose committed, deterministic `serialize.py` transforms a walkthrough sidecar (`<Project>-walkthrough.model.json`) into an OpenAPI 3.0.3 spec (JSON), a Postman v2.1 collection + environment, and an AWS-calls markdown companion.

**Architecture:** The extractor is stdlib-only Python under `skills/extract-api-spec/` — small focused modules (`fieldschema.py`, `auth.py`, `openapi_render.py`, `postman_render.py`, `aws_render.py`) orchestrated by `serialize.py`. It consumes only the sidecar's structured subset (`endpoints`, `aws_calls`); it does NOT re-read source or re-validate against the JSON Schema at runtime (the sidecar is already verified when produced). Output is deterministic via `json.dumps(sort_keys=True, indent=2)`. Tests (pytest) validate the OpenAPI against 3.0.3 with `openapi-spec-validator` and assert structure/no-invention/gap-preservation, using the existing Flaskr golden sidecar (target A) plus a new hand-authored AWS/JSON sidecar (target B).

**Tech Stack:** Python 3 stdlib (runtime); pytest + jsonschema + openapi-spec-validator (dev/test only). OpenAPI 3.0.3, Postman Collection v2.1.

## Global Constraints

Every task's requirements implicitly include these:

- **`serialize.py` and its modules are stdlib-only at runtime** — no third-party imports. Validators/openapi-spec-validator are dev/test-only.
- **Ground-only / no invention:** never synthesize data absent from the sidecar. A `grounded:false` body → an OpenAPI schema of `{}` (any) carrying the sidecar's `gap` as a `description`, plus an entry in the top-level `x-coverage-gaps` list. Never emit a security scheme for an endpoint whose `auth` is `[]`. Never synthesize a response status.
- **OpenAPI is emitted as JSON** (`<Project>-openapi.json`), 3.0.3, deterministic (`json.dumps(sort_keys=True, indent=2)` + trailing newline). Byte-identical on re-run from the same sidecar.
- **No-invention self-check** in `serialize.py`: the number of OpenAPI operations equals the number of sidecar endpoints; every operation's `operationId` traces to exactly one sidecar endpoint.
- **AWS SDK calls never enter the OpenAPI** — they render only into `<Project>-aws-calls.md`.
- Output filenames, all in the output directory: `<Project>-openapi.json`, `<Project>.postman_collection.json`, `<Project>.postman_environment.json`, `<Project>-aws-calls.md`. `<Project>` is `project.name` from the sidecar.
- **Commit messages MUST NOT include any `Co-Authored-By: Claude` trailer.**
- Extractor code lives under `skills/extract-api-spec/`; tests import it by adding that dir to `sys.path` (mirroring how `tests/` already imports `test_schema`). Run tests with `.venv/bin/python -m pytest tests/ -v`.

---

### Task 1: Dev dep + FieldSchema → OpenAPI Schema Object

The pure renderer that turns a sidecar `FieldSchema` into an OpenAPI 3.0.3 Schema Object. Handles primitives, `format`, `enum`, `array`/`items`, `object`/`properties`+required, `additionalProperties`, `nullable`, `readOnly`/`writeOnly`, `oneOf`+`discriminator` (hoisted), and unknown type.

**Files:**
- Modify: `tests/requirements-dev.txt`
- Create: `skills/extract-api-spec/fieldschema.py`
- Create: `tests/test_extract_fieldschema.py`

**Interfaces:**
- Produces: `render_field(field: dict, hoisted: dict) -> dict`. `field` is a sidecar FieldSchema. `hoisted` is a mutable dict `{name: schema_object}` the function adds hoisted `oneOf` branch schemas to (so the caller can merge them into `components.schemas`). Returns an OpenAPI 3.0.3 Schema Object. Consumed by Tasks 3 and 4.

- [ ] **Step 1: Add the dev dependency**

Append to `tests/requirements-dev.txt`:
```
openapi-spec-validator>=0.7
```

- [ ] **Step 2: Install it**

Run: `.venv/bin/pip install -r tests/requirements-dev.txt`
Expected: installs `openapi-spec-validator` (and its deps) without error.

- [ ] **Step 3: Write the failing tests**

`tests/test_extract_fieldschema.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))

from fieldschema import render_field


def r(field):
    hoisted = {}
    return render_field(field, hoisted), hoisted


def test_primitive_with_format():
    out, _ = r({"name": "created", "type": "string", "format": "date-time"})
    assert out == {"type": "string", "format": "date-time"}


def test_integer():
    out, _ = r({"name": "n", "type": "integer"})
    assert out == {"type": "integer"}


def test_enum_infers_string_type():
    out, _ = r({"name": "status", "type": "enum", "enum": ["DRAFT", "PUBLISHED"]})
    assert out == {"type": "string", "enum": ["DRAFT", "PUBLISHED"]}


def test_array_of_objects():
    out, _ = r({"name": "items", "type": "array",
                "items": {"name": "item", "type": "object",
                          "properties": [{"name": "id", "type": "integer", "required": True}]}})
    assert out == {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}}


def test_object_required_derived_from_children():
    out, _ = r({"name": "root", "type": "object", "properties": [
        {"name": "title", "type": "string", "required": True},
        {"name": "body", "type": "string", "required": False},
    ]})
    assert out["type"] == "object"
    assert out["properties"] == {"title": {"type": "string"}, "body": {"type": "string"}}
    assert out["required"] == ["title"]  # only required children, sorted


def test_object_with_no_required_omits_required_key():
    out, _ = r({"name": "root", "type": "object", "properties": [{"name": "x", "type": "string"}]})
    assert "required" not in out


def test_nullable_and_readonly():
    out, _ = r({"name": "id", "type": "integer", "nullable": True, "readOnly": True})
    assert out == {"type": "integer", "nullable": True, "readOnly": True}


def test_additional_properties_bool():
    out, _ = r({"name": "meta", "type": "object", "additionalProperties": True})
    assert out == {"type": "object", "additionalProperties": True}


def test_unknown_type_is_empty_schema_no_bare_nullable():
    # no type, nullable set -> must NOT emit bare nullable on {} (invalid 3.0.3)
    out, _ = r({"name": "x", "nullable": True})
    assert out == {}


def test_oneof_hoists_branches_and_sets_discriminator():
    out, hoisted = r({"name": "payload", "type": "object", "discriminator": "kind", "oneOf": [
        {"name": "A", "type": "object", "properties": [{"name": "kind", "type": "string", "required": True}]},
        {"name": "B", "type": "object", "properties": [{"name": "kind", "type": "string", "required": True}]},
    ]})
    assert out["oneOf"] == [{"$ref": "#/components/schemas/A"}, {"$ref": "#/components/schemas/B"}]
    assert out["discriminator"] == {"propertyName": "kind"}
    assert set(hoisted.keys()) == {"A", "B"}
    assert hoisted["A"]["type"] == "object"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_extract_fieldschema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fieldschema'`.

- [ ] **Step 5: Implement `skills/extract-api-spec/fieldschema.py`**

```python
"""Render a sidecar FieldSchema into an OpenAPI 3.0.3 Schema Object. Stdlib only."""

_PRIMITIVES = {"string", "number", "integer", "boolean", "object", "array"}


def _infer_enum_type(values):
    if values and all(isinstance(v, bool) for v in values):
        return "boolean"
    if values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return "integer"
    if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "number"
    if values and all(isinstance(v, str) for v in values):
        return "string"
    return None


def render_field(field, hoisted):
    t = field.get("type")
    out = {}

    if field.get("oneOf"):
        refs = []
        for branch in field["oneOf"]:
            name = branch.get("name") or "OneOf%d" % (len(hoisted) + 1)
            hoisted[name] = render_field(branch, hoisted)
            refs.append({"$ref": "#/components/schemas/%s" % name})
        out["oneOf"] = refs
        if field.get("discriminator"):
            out["discriminator"] = {"propertyName": field["discriminator"]}
        return out

    if t == "enum":
        inferred = _infer_enum_type(field.get("enum") or [])
        if inferred:
            out["type"] = inferred
        out["enum"] = list(field.get("enum") or [])
    elif t == "array":
        out["type"] = "array"
        items = field.get("items")
        out["items"] = render_field(items, hoisted) if items else {}
    elif t == "object":
        out["type"] = "object"
        props = field.get("properties") or []
        if props:                       # omit an empty properties map (keeps output minimal/valid)
            out["properties"] = {p["name"]: render_field(p, hoisted) for p in props}
        required = sorted(p["name"] for p in props if p.get("required"))
        if required:
            out["required"] = required
        ap = field.get("additionalProperties")
        if isinstance(ap, bool):
            out["additionalProperties"] = ap
        elif isinstance(ap, dict):
            out["additionalProperties"] = render_field(ap, hoisted)
    elif t in _PRIMITIVES:
        out["type"] = t
    # else: unknown type -> {} (any); do NOT add a bare nullable

    if "format" in field and t not in (None, "object", "array", "enum"):
        out["format"] = field["format"]
    # nullable only when a concrete type is present (never bare nullable on {})
    if field.get("nullable") and "type" in out:
        out["nullable"] = True
    if field.get("readOnly"):
        out["readOnly"] = True
    if field.get("writeOnly"):
        out["writeOnly"] = True
    return out
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_extract_fieldschema.py -v`
Expected: PASS — all cases green.

- [ ] **Step 7: Commit**

```bash
git add tests/requirements-dev.txt skills/extract-api-spec/fieldschema.py tests/test_extract_fieldschema.py
git commit -m "Add FieldSchema -> OpenAPI Schema Object renderer + openapi-spec-validator dev dep"
```

---

### Task 2: AuthScheme → securitySchemes + security requirements

Pure renderer that turns a sidecar endpoint's `auth` array into OpenAPI `components.securitySchemes` entries and per-operation `security` requirements. SigV4/custom become documented gaps, never `none`.

**Files:**
- Create: `skills/extract-api-spec/auth.py`
- Create: `tests/test_extract_auth.py`

**Interfaces:**
- Produces:
  - `render_scheme(auth: dict) -> (scheme_object_or_None, gap_or_None)` — maps one AuthScheme to an OpenAPI Security Scheme Object (or `(None, gap_string)` when unmappable, e.g. SigV4/custom).
  - `render_endpoint_security(auth_list: list, schemes: dict, gaps: list) -> list` — returns the operation's `security` list; adds needed schemes to `schemes` (name→object) and any unmappable-auth notes to `gaps`. Empty `auth_list` → returns `[]` (no security, none invented). Consumed by Task 3.

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_auth.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))

from auth import render_scheme, render_endpoint_security


def test_apikey_cookie():
    obj, gap = render_scheme({"scheme_name": "session", "kind": "apiKey", "in": "cookie", "name": "session"})
    assert obj == {"type": "apiKey", "in": "cookie", "name": "session"}
    assert gap is None


def test_apikey_header():
    obj, gap = render_scheme({"scheme_name": "apikey", "kind": "apiKey", "in": "header", "name": "x-api-key"})
    assert obj == {"type": "apiKey", "in": "header", "name": "x-api-key"}
    assert gap is None


def test_apikey_gap_preserved():
    obj, gap = render_scheme({"scheme_name": "session", "kind": "apiKey", "in": "cookie",
                              "name": "session", "gap": "cookie name assumed"})
    assert obj["type"] == "apiKey"
    assert gap == "cookie name assumed"   # disclosed gap flows to x-coverage-gaps


def test_http_bearer_jwt():
    obj, gap = render_scheme({"scheme_name": "cognito", "kind": "http", "scheme": "bearer", "bearerFormat": "JWT"})
    assert obj == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


def test_oauth2_scheme_shape():
    obj, gap = render_scheme({"scheme_name": "cognito", "kind": "oauth2", "scopes": ["posts.write"]})
    assert obj["type"] == "oauth2"
    assert obj["flows"]["clientCredentials"]["tokenUrl"]   # 3.0.3 requires a flow with a URL
    assert gap and "not recoverable" in gap                # placeholder URL is a documented gap


def test_custom_sigv4_is_gap_not_none():
    obj, gap = render_scheme({"scheme_name": "sigv4", "kind": "custom", "gap": "IAM SigV4 — not expressible in OpenAPI"})
    assert obj is None
    assert "SigV4" in gap


def test_endpoint_security_empty_auth_invents_nothing():
    schemes, gaps = {}, []
    assert render_endpoint_security([], schemes, gaps) == []
    assert schemes == {}
    assert gaps == []


def test_endpoint_security_collects_scheme_and_scopes():
    schemes, gaps = {}, []
    sec = render_endpoint_security(
        [{"scheme_name": "cognito", "kind": "oauth2", "scopes": ["posts.write"]}], schemes, gaps)
    assert sec == [{"cognito": ["posts.write"]}]
    assert "cognito" in schemes and schemes["cognito"]["type"] == "oauth2"


def test_endpoint_security_custom_adds_gap_no_requirement():
    schemes, gaps = {}, []
    sec = render_endpoint_security(
        [{"scheme_name": "sigv4", "kind": "custom", "gap": "IAM SigV4 — not expressible in OpenAPI"}], schemes, gaps)
    assert sec == []          # no invented requirement
    assert schemes == {}
    assert any("SigV4" in g for g in gaps)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'auth'`.

- [ ] **Step 3: Implement `skills/extract-api-spec/auth.py`**

```python
"""Render sidecar AuthScheme entries into OpenAPI securitySchemes + security. Stdlib only."""


def render_scheme(auth):
    """Return (openapi_security_scheme | None, gap | None) for one AuthScheme."""
    kind = auth.get("kind")
    if kind == "apiKey":
        obj = {"type": "apiKey", "in": auth["in"], "name": auth.get("name", "")}
        return obj, auth.get("gap")     # preserve any disclosed gap (e.g. assumed cookie name)
    if kind == "http":
        obj = {"type": "http", "scheme": auth.get("scheme", "bearer")}
        if auth.get("bearerFormat"):
            obj["bearerFormat"] = auth["bearerFormat"]
        return obj, auth.get("gap")
    if kind == "oauth2":
        # 3.0.3 requires a flows object with a URL; the URL is not recoverable from source,
        # so a REPLACE_ME placeholder is used and recorded as a gap. Scopes survive on the
        # per-operation security requirement.
        obj = {"type": "oauth2", "flows": {"clientCredentials": {
            "tokenUrl": "https://REPLACE_ME/oauth2/token", "scopes": {}}}}
        return obj, "oauth2 token URL for scheme not recoverable from source — placeholder used"
    if kind == "openIdConnect":
        obj = {"type": "openIdConnect",
               "openIdConnectUrl": "https://REPLACE_ME/.well-known/openid-configuration"}
        return obj, "openIdConnect URL not recoverable from source — placeholder used"
    if kind == "mutualTLS":
        # mutualTLS is an OpenAPI 3.1 scheme type; not expressible in 3.0.3 -> gap.
        return None, "mutualTLS security is not expressible in OpenAPI 3.0.3"
    if kind == "none":
        return None, None
    # custom / SigV4 / anything unmappable -> documented gap, never a scheme
    return None, auth.get("gap") or "auth kind '%s' not expressible in OpenAPI" % kind


def render_endpoint_security(auth_list, schemes, gaps):
    """Return the operation `security` list; register schemes; append gaps for unmappable auth."""
    security = []
    for auth in auth_list:
        obj, gap = render_scheme(auth)
        if gap:                        # record gap even when the scheme DOES map (e.g. oauth2 placeholder URL)
            gaps.append(gap)
        if obj is None:
            continue
        name = auth["scheme_name"]
        schemes[name] = obj
        security.append({name: list(auth.get("scopes") or [])})
    return security
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_extract_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/extract-api-spec/auth.py tests/test_extract_auth.py
git commit -m "Add AuthScheme -> OpenAPI securitySchemes + security renderer"
```

---

### Task 3: OpenAPI assembler

Assembles a full OpenAPI 3.0.3 document from a sidecar, using Tasks 1–2. Body schemas are keyed by `operationId` and always `$ref`-ed; responses are status-keyed with a `content` map; gaps collect into `x-coverage-gaps`.

**Files:**
- Create: `skills/extract-api-spec/openapi_render.py`
- Create: `tests/test_extract_openapi.py`

**Interfaces:**
- Consumes: `render_field` (Task 1), `render_endpoint_security` (Task 2).
- Produces: `render_openapi(sidecar: dict) -> dict` — a complete OpenAPI 3.0.3 document. Consumed by Task 5 (serialize.py) and Task 6 (golden B).

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_openapi.py`:
```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_openapi.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'openapi_render'`.

- [ ] **Step 3: Implement `skills/extract-api-spec/openapi_render.py`**

```python
"""Assemble an OpenAPI 3.0.3 document from a walkthrough sidecar. Stdlib only."""

from fieldschema import render_field
from auth import render_endpoint_security

_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _param(field, location):
    p = {"name": field["name"], "in": location,
         "required": bool(field.get("required")) or location == "path",
         "schema": render_field(field, {})}
    return p


def _body_schema(body, comp_name, components, gaps):
    """Return an OpenAPI schema object for a request/response body, registering a named component when grounded."""
    if body.get("grounded") and body.get("schema"):
        hoisted = {}
        rendered = render_field(body["schema"], hoisted)
        components.update(hoisted)
        components[comp_name] = rendered
        return {"$ref": "#/components/schemas/%s" % comp_name}
    gap = body.get("gap") or "not recoverable from source"
    gaps.append(gap)
    return {"description": gap}   # {} (any) + gap marker; nothing invented


def render_openapi(sidecar):
    project = sidecar["project"]
    components_schemas = {}
    security_schemes = {}
    gaps = []
    paths = {}

    for ep in sidecar["endpoints"]:
        op = {"operationId": ep["operationId"], "tags": [ep["group"]], "summary": ep.get("summary", "")}

        params = [_param(f, "path") for f in ep["request"].get("path_params", [])]
        params += [_param(f, "query") for f in ep["request"].get("query_params", [])]
        params += [_param(f, "header") for f in ep["request"].get("headers", [])]
        if params:
            op["parameters"] = params

        body = ep["request"].get("body") or {}
        grounded_body = body.get("grounded") and body.get("schema")
        gap_body = (not body.get("grounded")) and body.get("gap")   # ungrounded body still surfaces its gap
        if grounded_body or gap_body:
            mt = ep["request"].get("media_type") or "application/json"
            schema = _body_schema(body, ep["operationId"] + "Request", components_schemas, gaps)
            op["requestBody"] = {"content": {mt: {"schema": schema}}}

        responses = {}
        for resp in ep["responses"]:
            status = str(resp["status"])
            entry = {"description": resp["description"]}
            headers = {h["name"]: {"schema": render_field(h, {})} for h in resp.get("headers", [])}
            if headers:
                entry["headers"] = headers
            content = {}
            for c in resp.get("content", []):
                schema = _body_schema(c["body"], ep["operationId"] + "Response" + status, components_schemas, gaps)
                content[c["media_type"]] = {"schema": schema}
            if content:
                entry["content"] = content
            responses[status] = entry
        op["responses"] = responses

        security = render_endpoint_security(ep.get("auth", []), security_schemes, gaps)
        if security:
            op["security"] = security

        paths.setdefault(ep["path"], {})[ep["method"].lower()] = op

    doc = {
        "openapi": "3.0.3",
        "info": {"title": project["name"], "version": project["version"]},
        "servers": [{"url": "{baseUrl}", "variables": {"baseUrl": {
            "default": "https://REPLACE_ME",
            "description": "not recoverable from source — set before use"}}}],
        "paths": paths,
    }
    components = {}
    if components_schemas:
        components["schemas"] = components_schemas
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    if gaps:
        doc["x-coverage-gaps"] = gaps
    return doc
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_extract_openapi.py -v`
Expected: PASS — including `test_openapi_is_valid_303` (openapi-spec-validator accepts the document).

- [ ] **Step 5: Commit**

```bash
git add skills/extract-api-spec/openapi_render.py tests/test_extract_openapi.py
git commit -m "Add OpenAPI 3.0.3 assembler (paths, components, security, coverage gaps)"
```

---

### Task 4: Postman collection + environment renderer

Renders a Postman Collection v2.1 (folders by `group`, body mode by media type, `url.variable` for path params, auth mapped correctly) plus an environment file. Built from the sidecar directly so anchors/gaps survive.

**Files:**
- Create: `skills/extract-api-spec/postman_render.py`
- Create: `tests/test_extract_postman.py`

**Interfaces:**
- Produces: `render_postman(sidecar: dict) -> (collection: dict, environment: dict)`. Consumed by Task 5.

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_postman.py`:
```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_postman.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'postman_render'`.

- [ ] **Step 3: Implement `skills/extract-api-spec/postman_render.py`**

```python
"""Render a Postman Collection v2.1 + environment from a walkthrough sidecar. Stdlib only."""

_SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


def _url(path):
    segments = [s for s in path.split("/") if s != ""]
    postman_segments = []
    variables = []
    for s in segments:
        if s.startswith("{") and s.endswith("}"):
            key = s[1:-1]
            postman_segments.append(":" + key)
            variables.append({"key": key})
        else:
            postman_segments.append(s)
    url = {"raw": "{{baseUrl}}/" + "/".join(postman_segments), "host": ["{{baseUrl}}"], "path": postman_segments}
    if variables:
        url["variable"] = variables
    return url


def _body(request):
    body = request.get("body") or {}
    if not (body.get("grounded") and body.get("schema")):
        return None
    fields = body["schema"].get("properties") or []
    mt = request.get("media_type") or "application/json"
    if mt == "application/x-www-form-urlencoded":
        return {"mode": "urlencoded", "urlencoded": [{"key": f["name"], "value": "", "type": "text"} for f in fields]}
    if mt.startswith("multipart/"):
        return {"mode": "formdata", "formdata": [{"key": f["name"], "value": "", "type": "text"} for f in fields]}
    # default JSON
    example = {f["name"]: "" for f in fields}
    import json
    return {"mode": "raw", "raw": json.dumps(example, indent=2),
            "options": {"raw": {"language": "json"}}}


def _auth(auth_list, env_keys):
    for a in auth_list:
        if a.get("kind") == "http" and a.get("scheme") == "bearer":
            env_keys.add("token")
            return {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]}
        if a.get("kind") == "apiKey" and a.get("in") == "header":
            env_keys.add("apiKey")
            return {"type": "apikey", "apikey": [
                {"key": "key", "value": a.get("name", "x-api-key"), "type": "string"},
                {"key": "value", "value": "{{apiKey}}", "type": "string"},
                {"key": "in", "value": "header", "type": "string"}]}
        # session/cookie auth lives in the cookie jar, not the request auth object; skip
    return None


def render_postman(sidecar):
    env_keys = {"baseUrl"}
    folders = {}
    for ep in sidecar["endpoints"]:
        request = {"method": ep["method"], "header": [], "url": _url(ep["path"])}
        body = _body(ep["request"])
        if body:
            request["body"] = body
        auth = _auth(ep.get("auth", []), env_keys)
        if auth:
            request["auth"] = auth
        item = {"name": ep["operationId"], "request": request}
        folders.setdefault(ep["group"], []).append(item)

    collection = {
        "info": {"name": sidecar["project"]["name"], "schema": _SCHEMA},
        "item": [{"name": group, "item": items} for group, items in sorted(folders.items())],
    }
    environment = {
        "name": sidecar["project"]["name"] + " environment",
        "values": [{"key": k, "value": "", "enabled": True} for k in sorted(env_keys)],
    }
    return collection, environment
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_extract_postman.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add skills/extract-api-spec/postman_render.py tests/test_extract_postman.py
git commit -m "Add Postman v2.1 collection + environment renderer"
```

---

### Task 5: AWS companion + serialize.py CLI (orchestration, determinism, no-invention)

`aws_render.py` renders the AWS-calls markdown; `serialize.py` ties everything together, writes the four files deterministically, and runs the no-invention self-check. Includes an end-to-end test against the Flaskr golden (target A) plus a determinism test.

**Files:**
- Create: `skills/extract-api-spec/aws_render.py`
- Create: `skills/extract-api-spec/serialize.py`
- Create: `tests/test_extract_serialize.py`

**Interfaces:**
- Consumes: `render_openapi` (Task 3), `render_postman` (Task 4).
- Produces:
  - `render_aws_calls(sidecar: dict) -> str` (markdown).
  - `serialize(sidecar: dict, outdir: str) -> list[str]` (writes files, returns written paths).
  - CLI: `python serialize.py <sidecar.json> <outdir>`.

- [ ] **Step 1: Write the failing tests**

`tests/test_extract_serialize.py`:
```python
import json
import sys
from pathlib import Path

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


def test_determinism_byte_identical(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"
    a.mkdir(); b.mkdir()
    serialize(load(FLASKR), str(a))
    serialize(load(FLASKR), str(b))
    for name in ["Flaskr-openapi.json", "Flaskr.postman_collection.json",
                 "Flaskr.postman_environment.json", "Flaskr-aws-calls.md"]:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_serialize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'serialize'`.

- [ ] **Step 3: Implement `skills/extract-api-spec/aws_render.py`**

```python
"""Render the AWS SDK-calls markdown companion from a sidecar. Stdlib only."""


def render_aws_calls(sidecar):
    calls = sidecar.get("aws_calls") or []
    lines = ["# AWS SDK calls", ""]
    if not calls:
        lines.append("_No AWS SDK calls were found in this codebase._")
        return "\n".join(lines) + "\n"
    lines += ["These are AWS service side-effects the code performs. They are not HTTP endpoints, "
              "so they are documented here rather than in the OpenAPI spec.", "",
              "| Service | Operation | Resource | Purpose | Source |",
              "|---------|-----------|----------|---------|--------|"]
    for c in sorted(calls, key=lambda c: (c["service"], c["operation"])):
        res = c.get("resource") or {}
        res_str = ", ".join("%s=%s" % (k, v) for k, v in sorted(res.items()))
        anc = c.get("anchor") or {}
        src = "%s:%s" % (anc.get("file", ""), anc.get("symbol", ""))
        lines.append("| %s | %s | %s | %s | %s |" % (
            c["service"], c["operation"], res_str, c.get("purpose", ""), src))
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Implement `skills/extract-api-spec/serialize.py`**

```python
"""Deterministically transform a walkthrough sidecar into OpenAPI + Postman + AWS companion.

Usage: python serialize.py <sidecar.json> <outdir>
Stdlib only. Output is byte-identical across runs on the same sidecar.
"""

import json
import sys
from pathlib import Path

from openapi_render import render_openapi
from postman_render import render_postman
from aws_render import render_aws_calls


def _dump(obj):
    return json.dumps(obj, sort_keys=True, indent=2) + "\n"


def _assert_no_invention(sidecar, openapi):
    op_ids = [op["operationId"]
              for methods in openapi["paths"].values() for op in methods.values()]
    ep_ids = [ep["operationId"] for ep in sidecar["endpoints"]]
    if sorted(op_ids) != sorted(ep_ids):
        raise ValueError("no-invention check failed: OpenAPI operations do not match sidecar endpoints "
                         "(%d vs %d)" % (len(op_ids), len(ep_ids)))


def serialize(sidecar, outdir):
    name = sidecar["project"]["name"]
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)

    openapi = render_openapi(sidecar)
    _assert_no_invention(sidecar, openapi)
    collection, environment = render_postman(sidecar)
    aws_md = render_aws_calls(sidecar)

    written = []
    targets = [
        ("%s-openapi.json" % name, _dump(openapi)),
        ("%s.postman_collection.json" % name, _dump(collection)),
        ("%s.postman_environment.json" % name, _dump(environment)),
        ("%s-aws-calls.md" % name, aws_md),
    ]
    for filename, content in targets:
        path = out / filename
        path.write_text(content)
        written.append(str(path))
    return written


def main(argv):
    if len(argv) != 3:
        print("usage: python serialize.py <sidecar.json> <outdir>", file=sys.stderr)
        return 2
    with open(argv[1]) as fh:
        sidecar = json.load(fh)
    written = serialize(sidecar, argv[2])
    for p in written:
        print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_extract_serialize.py -v`
Expected: PASS — Flaskr end-to-end, valid OpenAPI, 1:1 operation count, no 401, byte-identical reruns.

- [ ] **Step 6: Commit**

```bash
git add skills/extract-api-spec/aws_render.py skills/extract-api-spec/serialize.py tests/test_extract_serialize.py
git commit -m "Add AWS companion renderer + serialize.py CLI (deterministic, no-invention check)"
```

---

### Task 6: AWS/JSON golden fixture (target B)

A hand-authored sidecar exercising what Flaskr can't: JSON bodies with arrays/enums/formats/readOnly, a paginated list response with a cursor header, `apiKey`-in-header + Cognito `oauth2` scopes, an IAM SigV4 `custom` gap, and `aws_calls`. Proves AWS-native coverage.

**Files:**
- Create: `tests/fixtures/valid/aws-api.model.json`
- Create: `tests/test_extract_aws_golden.py`

**Interfaces:**
- Consumes: the schema (validates as a sidecar), `serialize` (Task 5).

- [ ] **Step 1: Write the fact-assertion test**

`tests/test_extract_aws_golden.py`:
```python
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
    schemas = doc["components"]["schemas"]
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_aws_golden.py -v`
Expected: FAIL — `aws-api.model.json` does not exist.

- [ ] **Step 3: Author `tests/fixtures/valid/aws-api.model.json`**

A schema-valid sidecar named `PaymentsAPI`. It must contain (at minimum) these endpoints and sections; author it to satisfy both the walkthrough schema and the Step-1 assertions:

```json
{
  "schema_version": "1.0",
  "project": {"name": "PaymentsAPI", "version": "0.0.0-from-walkthrough", "source_ref": "main"},
  "endpoints": [
    {
      "id": "post_payments_create", "operationId": "createPayment", "group": "Payments", "in_journey": true,
      "method": "POST", "path": "/payments", "source_path": "/payments", "summary": "Create a payment",
      "handler": {"file": "handlers/payments.py", "symbol": "create"},
      "auth": [{"scheme_name": "cognito", "kind": "oauth2", "scopes": ["payments.write"],
                "sources": [{"file": "template.yaml", "symbol": "CognitoAuthorizer"}]}],
      "request": {"media_type": "application/json", "path_params": [], "query_params": [], "headers": [],
        "body": {"grounded": true, "schema": {"name": "root", "type": "object", "properties": [
          {"name": "amount", "type": "number", "required": true, "anchor": {"file": "handlers/payments.py", "symbol": "create"}},
          {"name": "currency", "type": "enum", "enum": ["USD", "EUR", "GBP"], "required": true, "anchor": {"file": "handlers/payments.py", "symbol": "create"}}
        ]}, "gap": null}},
      "responses": [
        {"status": 201, "description": "Payment created", "headers": [], "content": [
          {"media_type": "application/json", "body": {"grounded": true, "schema": {"name": "root", "type": "object", "properties": [
            {"name": "id", "type": "string", "format": "uuid", "readOnly": true, "required": true, "anchor": {"file": "handlers/payments.py", "symbol": "create"}},
            {"name": "createdAt", "type": "string", "format": "date-time", "readOnly": true, "required": true, "anchor": {"file": "handlers/payments.py", "symbol": "create"}}
          ]}, "gap": null}}], "anchor": {"file": "handlers/payments.py", "symbol": "create"}}
      ]
    },
    {
      "id": "get_payments_list", "operationId": "listPayments", "group": "Payments", "in_journey": true,
      "method": "GET", "path": "/payments", "source_path": "/payments", "summary": "List payments (paginated)",
      "handler": {"file": "handlers/payments.py", "symbol": "list_payments"},
      "auth": [{"scheme_name": "apikey", "kind": "apiKey", "in": "header", "name": "x-api-key",
                "sources": [{"file": "template.yaml", "symbol": "ApiKey"}]}],
      "request": {"media_type": null,
        "path_params": [],
        "query_params": [{"name": "nextToken", "type": "string", "required": false, "anchor": {"file": "handlers/payments.py", "symbol": "list_payments"}}],
        "headers": [], "body": {"grounded": true, "schema": null, "gap": null}},
      "responses": [
        {"status": 200, "description": "A page of payments", "headers": [
          {"name": "x-next-token", "type": "string", "anchor": {"file": "handlers/payments.py", "symbol": "list_payments"}}],
         "content": [{"media_type": "application/json", "body": {"grounded": true, "schema": {"name": "root", "type": "object", "properties": [
            {"name": "items", "type": "array", "required": true, "items": {"name": "item", "type": "object", "properties": [
               {"name": "id", "type": "string", "format": "uuid", "required": true}]}, "anchor": {"file": "handlers/payments.py", "symbol": "list_payments"}},
            {"name": "nextToken", "type": "string", "required": false, "anchor": {"file": "handlers/payments.py", "symbol": "list_payments"}}
          ]}, "gap": null}}], "anchor": {"file": "handlers/payments.py", "symbol": "list_payments"}}
      ]
    },
    {
      "id": "get_payments_export", "operationId": "exportPayments", "group": "Payments", "in_journey": true,
      "method": "GET", "path": "/payments/export", "source_path": "/payments/export", "summary": "Export (IAM-signed)",
      "handler": {"file": "handlers/export.py", "symbol": "export"},
      "auth": [{"scheme_name": "sigv4", "kind": "custom", "gap": "IAM SigV4 (AWS_IAM authorizer) — not expressible in OpenAPI 3.0.3",
                "sources": [{"file": "template.yaml", "symbol": "AwsIamAuth"}]}],
      "request": {"media_type": null, "path_params": [], "query_params": [], "headers": [],
        "body": {"grounded": true, "schema": null, "gap": null}},
      "responses": [
        {"status": 200, "description": "Export stream", "headers": [], "content": [
          {"media_type": "application/json", "body": {"grounded": false, "schema": null, "gap": "streamed export; shape not modeled"}}],
         "anchor": {"file": "handlers/export.py", "symbol": "export"}}
      ]
    }
  ],
  "aws_calls": [
    {"service": "DynamoDB", "operation": "PutItem", "resource": {"table": "Payments", "keys": ["pk", "sk"]},
     "purpose": "persist a new payment", "anchor": {"file": "handlers/payments.py", "symbol": "create"}},
    {"service": "S3", "operation": "GetObject", "resource": {"bucket": "payment-exports"},
     "purpose": "read an export file", "anchor": {"file": "handlers/export.py", "symbol": "export"}}
  ]
}
```

- [ ] **Step 4: Run the AWS-golden tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_extract_aws_golden.py -v` then `.venv/bin/python -m pytest tests/ -v`
Expected: PASS — fixture validates as a sidecar; OpenAPI models arrays/enums/formats/oauth2-scopes/apiKey; SigV4 is a gap; AWS calls in the md, absent from OpenAPI. Full suite green.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/valid/aws-api.model.json tests/test_extract_aws_golden.py
git commit -m "Add AWS/JSON golden sidecar (target B) exercising arrays, scopes, SigV4 gap"
```

---

### Task 7: Skill docs + packaging (1.2.0)

The `extract-api-spec` SKILL.md + mapping reference, version bump, plugin/marketplace metadata, CHANGELOG release, and README.

**Files:**
- Create: `skills/extract-api-spec/SKILL.md`
- Create: `skills/extract-api-spec/mapping-spec.md`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Create: `tests/test_extract_packaging.py`

**Interfaces:**
- Consumes: the finished extractor (Tasks 1–6).

- [ ] **Step 1: Write the failing packaging test**

`tests/test_extract_packaging.py`:
```python
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_version_bumped():
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert data["version"] == "1.2.0"


def test_skill_md_present_and_shaped():
    text = (ROOT / "skills" / "extract-api-spec" / "SKILL.md").read_text()
    assert text.startswith("---")                     # YAML frontmatter
    assert "name: extract-api-spec" in text
    assert "serialize.py" in text
    for out in ["openapi.json", "postman_collection.json", "aws-calls.md"]:
        assert out in text


def test_changelog_has_120_release():
    text = (ROOT / "CHANGELOG.md").read_text()
    assert "## [1.2.0]" in text
    assert "extract-api-spec" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_extract_packaging.py -v`
Expected: FAIL — version still 1.1.0, SKILL.md absent.

- [ ] **Step 3: Write `skills/extract-api-spec/SKILL.md`**

```markdown
---
name: extract-api-spec
description: Use when the user wants to derive an OpenAPI (Swagger) spec and a Postman collection from an existing walkthrough sidecar (`<Project>-walkthrough.model.json`). Produces vanilla OpenAPI 3.0.3 (JSON), a Postman v2.1 collection + environment, and an AWS-calls markdown companion. Triggers on "extract OpenAPI", "generate swagger", "postman collection from the walkthrough", "API spec from the doc".
---

# Extract API Spec

## Overview

Turns a walkthrough **sidecar** into API artifacts by running a committed, deterministic script — not by hand. The sidecar (`<Project>-walkthrough.model.json`, produced by `generate-walkthrough`) is the trusted, already-verified input; extraction is a faithful transform that invents nothing.

Outputs, written next to the sidecar:
- `<Project>-openapi.json` — OpenAPI 3.0.3 (JSON; canonical artifact).
- `<Project>.postman_collection.json` — Postman Collection v2.1.
- `<Project>.postman_environment.json` — `baseUrl` + auth variables.
- `<Project>-aws-calls.md` — AWS SDK-call companion (not expressible in OpenAPI).

## When to use

- The user has a walkthrough sidecar and wants an OpenAPI spec and/or Postman collection from it.
- Not for: producing the walkthrough itself (use `generate-walkthrough` first — this skill needs the sidecar), or for AWS API Gateway `x-amazon-apigateway-*` extensions (vanilla 3.0.3 only).

## How to run

1. Ensure a sidecar exists. If not, tell the user to run `generate-walkthrough` first — do NOT re-derive from source.
2. Run the extractor:
   ```
   python skills/extract-api-spec/serialize.py <path/to/Project-walkthrough.model.json> <output-dir>
   ```
   It is stdlib-only and deterministic (byte-identical on re-run). It writes the four files above and runs a no-invention self-check (OpenAPI operations map 1:1 to sidecar endpoints).
3. Validate (best-effort, if the tools are installed): validate the OpenAPI with `openapi-spec-validator`; import the Postman collection to confirm it loads. If validators are absent, do a structural spot-check.

## Grounding rules

- Ground-only: a `grounded:false` body becomes an empty (`{}`, "any") schema carrying the sidecar's `gap` as a description, plus an entry in the OpenAPI top-level `x-coverage-gaps` list. Never fill it in.
- Auth that cannot map to an OpenAPI security scheme (IAM SigV4, custom Lambda authorizers) is recorded as a coverage gap — never silently dropped to "no auth".
- AWS SDK calls render only into the `-aws-calls.md` companion; they never enter the OpenAPI.
- The base URL is not recoverable from source: the OpenAPI `servers` entry uses a `{baseUrl}` placeholder and Postman uses `{{baseUrl}}` — set before use.

See `mapping-spec.md` for the exact sidecar → OpenAPI/Postman field mapping.
```

- [ ] **Step 4: Write `skills/extract-api-spec/mapping-spec.md`**

```markdown
# Sidecar → OpenAPI / Postman mapping

The exact transform `serialize.py` performs. The sidecar's structured subset
(`endpoints`, `aws_calls`) is consumed; `data_model`/`parameters`/`boundaries`/
narrative sections are ignored (they are HTML-only).

## OpenAPI 3.0.3

| Sidecar | OpenAPI |
|---------|---------|
| `project.name` / `project.version` | `info.title` / `info.version` |
| `endpoints[]` (incl. GET/POST twins) | `paths.{path}.{method}` |
| `operationId` / `group` / `summary` | `operationId` / `tags` / `summary` |
| `request.path_params/query_params/headers` | `parameters[]` (`in`, `required`, `schema`) |
| `request.body` (grounded) + `media_type` | `requestBody.content[media_type].schema` → `$ref components.schemas.{operationId}Request` |
| `responses[]` | `responses.{status}` (required `description`, `headers`, `content` map) → response bodies `$ref …Response{status}` |
| `auth[]` | `components.securitySchemes` + per-op `security` (with `scopes`); SigV4/custom → `x-coverage-gaps`, never `none` |
| `grounded:false` body | `{}` + `description: <gap>` and an entry in top-level `x-coverage-gaps` |
| — (not in source) | `servers: [{url: "{baseUrl}", ...}]` |
| `aws_calls[]` | NOT emitted (companion markdown only) |

FieldSchema → Schema Object: `type/format/enum/items/properties/additionalProperties/
nullable/readOnly/writeOnly` map directly; `oneOf` branches are hoisted into
`components.schemas` with a synthesized `discriminator.propertyName`; unknown type →
`{}` with no bare `nullable`.

## Postman v2.1

- Folders by `group`; each request = method + `{{baseUrl}}` + path (`:id`) + `url.variable` + headers + body.
- Body mode by media type: JSON → `raw`/json; `x-www-form-urlencoded` → `urlencoded`; `multipart/*` → `formdata`.
- Auth: `http`/`bearer` → `{{token}}`; `apiKey`-in-header → `{{apiKey}}`; session/cookie → cookie jar (not the request `auth`).
- Environment ships `baseUrl` + the auth variables used.

## Determinism

`serialize.py` emits JSON with `json.dumps(sort_keys=True, indent=2)` + trailing
newline, so re-running on the same sidecar yields byte-identical output.
```

- [ ] **Step 5: Bump the version and metadata**

In `.claude-plugin/plugin.json`, change `"version": "1.1.0"` to `"version": "1.2.0"`, and add `"openapi"`, `"postman"`, `"api"` to the `keywords` array.

In `.claude-plugin/marketplace.json`, extend the single plugin's `description` to note it now also extracts OpenAPI/Postman from the walkthrough (append a sentence), and add `"openapi"`, `"postman"` to its `keywords`.

- [ ] **Step 6: Release the changelog**

In `CHANGELOG.md`, rename the current `## [Unreleased]` heading to `## [1.2.0] — 2026-07-09` and add under its `### Added`:
```markdown
- **`extract-api-spec` skill** — derives a vanilla OpenAPI 3.0.3 spec (`<Project>-openapi.json`), a Postman v2.1 collection + environment, and an AWS-calls markdown companion from a walkthrough sidecar, via a committed stdlib-only deterministic `serialize.py`. Ground-only: unrecoverable detail is marked in `x-coverage-gaps`, never invented; AWS SDK calls render to the companion, never into the OpenAPI.
```
Add a fresh empty `## [Unreleased]` above it with `_Nothing yet._`.

- [ ] **Step 7: Update the README**

In `README.md`, add a row to the Files table for the new skill (e.g. `| skills/extract-api-spec/SKILL.md | Derives OpenAPI 3.0.3 + Postman from a walkthrough sidecar |`) and a short "Also: extract an API spec" note under the Use-it section pointing at `/extract-api-spec`.

- [ ] **Step 8: Run the packaging test + full suite**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS — packaging assertions green; the whole suite (schema + walkthrough docs + all extractor tests + goldens) green.

- [ ] **Step 9: Commit**

```bash
git add skills/extract-api-spec/SKILL.md skills/extract-api-spec/mapping-spec.md .claude-plugin/ CHANGELOG.md README.md tests/test_extract_packaging.py
git commit -m "Add extract-api-spec skill docs + mapping spec; release 1.2.0"
```

---

## Notes for the executor

- Run the whole suite between tasks: `.venv/bin/python -m pytest tests/ -v`.
- All extractor modules are stdlib-only at runtime; only the tests import `openapi_spec_validator`/`jsonschema`.
- The sidecar schema (`schema/walkthrough-model.schema.json`) is the frozen contract from Plan A — do not modify it here.
- Tasks 1–5 build the transform bottom-up (field → auth → openapi → postman → orchestrate); Task 6 proves AWS-native coverage; Task 7 ships it.
```
