# Walkthrough Sidecar + generate-walkthrough Inversion (Plan A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `generate-walkthrough` emit a verified, machine-readable sidecar (`<Project>-walkthrough.model.json`) as its primary artifact and render the HTML from it, with the sidecar's shape pinned by a committed JSON Schema.

**Architecture:** The deliverable splits into (1) a formal JSON Schema (`schema/walkthrough-model.schema.json`, Draft 2020-12) that is the frozen contract for this plan, Plan B (extractor), and the future PR feature, validated by a Python/pytest harness against valid + invalid fixtures and a hand-authored Flaskr golden; and (2) prose edits to the skill (`SKILL.md` phase-2 inversion + three-way phase-3 verification; `walkthrough-spec.md` schema section + field→HTML-region mapping), gated by structural checks and review.

**Tech Stack:** JSON Schema Draft 2020-12; Python 3 with `pytest` + `jsonschema` (dev-only, for the contract tests); Markdown (the skills themselves).

## Global Constraints

Every task's requirements implicitly include these (copied from the spec):

- Sidecar `schema_version` is exactly `"1.0"`.
- Anchors are **symbol-primary**: `{ "file", "symbol", "line"? }` — `file` and `symbol` required, `line` an optional hint. Multi-site facts use `sources: [anchor]`.
- **Ground-only / no invention:** unrecoverable data is `grounded:false` + a `gap` string; never fabricated. Responses list **only source-observed statuses** (an auth gate that redirects is a `302`, never a synthesized `401`).
- **`auth` is always an array** of AuthScheme; an empty array means unauthenticated.
- Every response has a **non-empty `description`**.
- **Deterministic ordering:** every array is sorted by a stable id/name on emit.
- Extraction consumes only `endpoints` (+ `aws_calls`); `data_model`, `parameters`, `boundaries`, and narrative sections are reference/HTML-only.
- **Commit messages MUST NOT include any `Co-Authored-By: Claude` trailer** (repo convention).
- Contract tests are Python 3 + `pytest` + `jsonschema` only; no other runtime dependencies.

---

### Task 1: Frozen API-subset schema + test harness

This delivers the part of the contract Plan B depends on: `anchor`, `fieldSchema`, `authScheme`, and `endpoint`/`request`/`response`, plus the top-level object requiring `endpoints`. Reference/narrative sections come in Task 2.

**Files:**
- Create: `schema/walkthrough-model.schema.json`
- Create: `tests/requirements-dev.txt`
- Create: `tests/test_schema.py`
- Create: `tests/fixtures/valid/minimal.model.json`
- Create: `tests/fixtures/invalid/response-missing-description.model.json`
- Create: `tests/fixtures/invalid/auth-not-array.model.json`
- Create: `tests/fixtures/invalid/enum-without-values.model.json`
- Create: `tests/fixtures/invalid/apikey-without-in.model.json`

**Interfaces:**
- Produces: `schema/walkthrough-model.schema.json` with `$defs`: `anchor`, `fieldSchema`, `authScheme`, `bodyRef`, `responseContent`, `response`, `endpoint`. Top-level requires `["schema_version","project","endpoints"]`. Consumed by Tasks 2–6 and by Plan B.
- Produces: `tests/test_schema.py` exposing `validator_for(path)` and `iter_fixtures(subdir)` helpers reused by later tasks.

- [ ] **Step 1: Create the dev-dependency file**

`tests/requirements-dev.txt`:
```
pytest>=8
jsonschema>=4.20
```

- [ ] **Step 2: Set up the environment**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements-dev.txt
```
Expected: installs `pytest` and `jsonschema` without error.

- [ ] **Step 3: Write the failing tests**

`tests/test_schema.py`:
```python
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
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py -v`
Expected: FAIL — collection/`test_schema_is_itself_valid` errors because `schema/walkthrough-model.schema.json` does not exist yet.

- [ ] **Step 5: Write the schema (core API subset)**

`schema/walkthrough-model.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/ArulVelusamy/generate-walkthrough/schema/walkthrough-model.schema.json",
  "title": "Walkthrough sidecar knowledge model",
  "type": "object",
  "required": ["schema_version", "project", "endpoints"],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "const": "1.0" },
    "project": {
      "type": "object",
      "required": ["name", "version"],
      "additionalProperties": false,
      "properties": {
        "name": { "type": "string", "minLength": 1 },
        "version": { "type": "string", "minLength": 1 },
        "source_ref": { "type": "string" }
      }
    },
    "endpoints": { "type": "array", "items": { "$ref": "#/$defs/endpoint" } }
  },
  "$defs": {
    "anchor": {
      "type": "object",
      "required": ["file", "symbol"],
      "additionalProperties": false,
      "properties": {
        "file": { "type": "string", "minLength": 1 },
        "symbol": { "type": "string", "minLength": 1 },
        "line": { "type": "integer", "minimum": 1 }
      }
    },
    "fieldSchema": {
      "type": "object",
      "required": ["name", "type"],
      "additionalProperties": false,
      "properties": {
        "name": { "type": "string" },
        "type": { "enum": ["string", "number", "integer", "boolean", "object", "array", "enum"] },
        "format": { "type": "string" },
        "required": { "type": "boolean" },
        "nullable": { "type": "boolean" },
        "readOnly": { "type": "boolean" },
        "writeOnly": { "type": "boolean" },
        "enum": { "type": "array" },
        "items": { "$ref": "#/$defs/fieldSchema" },
        "properties": { "type": "array", "items": { "$ref": "#/$defs/fieldSchema" } },
        "additionalProperties": { "type": ["boolean", "object"] },
        "oneOf": { "type": "array", "items": { "$ref": "#/$defs/fieldSchema" } },
        "discriminator": { "type": "string" },
        "constraints": { "type": "array", "items": { "type": "string" } },
        "anchor": { "$ref": "#/$defs/anchor" }
      },
      "allOf": [
        { "if": { "properties": { "type": { "const": "enum" } }, "required": ["type"] },
          "then": { "required": ["enum"] } },
        { "if": { "properties": { "type": { "const": "array" } }, "required": ["type"] },
          "then": { "required": ["items"] } }
      ]
    },
    "authScheme": {
      "type": "object",
      "required": ["scheme_name", "kind"],
      "additionalProperties": false,
      "properties": {
        "scheme_name": { "type": "string" },
        "kind": { "enum": ["apiKey", "http", "oauth2", "openIdConnect", "mutualTLS", "none", "custom"] },
        "in": { "enum": ["header", "cookie", "query"] },
        "name": { "type": "string" },
        "scheme": { "enum": ["bearer", "basic"] },
        "bearerFormat": { "type": "string" },
        "scopes": { "type": "array", "items": { "type": "string" } },
        "sources": { "type": "array", "items": { "$ref": "#/$defs/anchor" } },
        "gap": { "type": ["string", "null"] }
      },
      "allOf": [
        { "if": { "properties": { "kind": { "const": "apiKey" } }, "required": ["kind"] },
          "then": { "required": ["in"] } }
      ]
    },
    "bodyRef": {
      "type": "object",
      "required": ["grounded"],
      "additionalProperties": false,
      "properties": {
        "grounded": { "type": "boolean" },
        "schema": { "anyOf": [ { "$ref": "#/$defs/fieldSchema" }, { "type": "null" } ] },
        "gap": { "type": ["string", "null"] }
      }
    },
    "responseContent": {
      "type": "object",
      "required": ["media_type", "body"],
      "additionalProperties": false,
      "properties": {
        "media_type": { "type": "string" },
        "body": { "$ref": "#/$defs/bodyRef" }
      }
    },
    "response": {
      "type": "object",
      "required": ["status", "description", "content", "anchor"],
      "additionalProperties": false,
      "properties": {
        "status": { "type": "integer", "minimum": 100, "maximum": 599 },
        "description": { "type": "string", "minLength": 1 },
        "headers": { "type": "array", "items": { "$ref": "#/$defs/fieldSchema" } },
        "content": { "type": "array", "items": { "$ref": "#/$defs/responseContent" } },
        "anchor": { "$ref": "#/$defs/anchor" }
      }
    },
    "endpoint": {
      "type": "object",
      "required": ["id", "operationId", "group", "in_journey", "method", "path", "source_path", "summary", "handler", "auth", "request", "responses"],
      "additionalProperties": false,
      "properties": {
        "id": { "type": "string" },
        "operationId": { "type": "string" },
        "group": { "type": "string" },
        "in_journey": { "type": "boolean" },
        "method": { "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] },
        "path": { "type": "string" },
        "source_path": { "type": "string" },
        "summary": { "type": "string" },
        "handler": { "$ref": "#/$defs/anchor" },
        "auth": { "type": "array", "items": { "$ref": "#/$defs/authScheme" } },
        "request": {
          "type": "object",
          "required": ["media_type", "path_params", "query_params", "headers", "body"],
          "additionalProperties": false,
          "properties": {
            "media_type": { "type": ["string", "null"] },
            "path_params": { "type": "array", "items": { "$ref": "#/$defs/fieldSchema" } },
            "query_params": { "type": "array", "items": { "$ref": "#/$defs/fieldSchema" } },
            "headers": { "type": "array", "items": { "$ref": "#/$defs/fieldSchema" } },
            "body": { "$ref": "#/$defs/bodyRef" }
          }
        },
        "responses": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/response" } },
        "callers": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["screen", "anchor"],
            "additionalProperties": false,
            "properties": { "screen": { "type": "string" }, "anchor": { "$ref": "#/$defs/anchor" } }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 6: Write the valid minimal fixture**

`tests/fixtures/valid/minimal.model.json`:
```json
{
  "schema_version": "1.0",
  "project": { "name": "Demo", "version": "0.0.0-from-walkthrough" },
  "endpoints": [
    {
      "id": "get_root",
      "operationId": "getRoot",
      "group": "Root",
      "in_journey": true,
      "method": "GET",
      "path": "/",
      "source_path": "/",
      "summary": "Index",
      "handler": { "file": "app.py", "symbol": "index", "line": 10 },
      "auth": [],
      "request": { "media_type": null, "path_params": [], "query_params": [], "headers": [], "body": { "grounded": true, "schema": null, "gap": null } },
      "responses": [
        { "status": 200, "description": "OK", "content": [ { "media_type": "text/html", "body": { "grounded": false, "schema": null, "gap": "rendered template" } } ], "anchor": { "file": "app.py", "symbol": "index", "line": 12 } }
      ]
    }
  ]
}
```

- [ ] **Step 7: Write the invalid fixtures**

`tests/fixtures/invalid/response-missing-description.model.json` — same as minimal but the response object omits `description`:
```json
{
  "schema_version": "1.0",
  "project": { "name": "Demo", "version": "0.0.0" },
  "endpoints": [
    { "id": "get_root", "operationId": "getRoot", "group": "Root", "in_journey": true, "method": "GET", "path": "/", "source_path": "/", "summary": "Index",
      "handler": { "file": "app.py", "symbol": "index" }, "auth": [],
      "request": { "media_type": null, "path_params": [], "query_params": [], "headers": [], "body": { "grounded": true, "schema": null, "gap": null } },
      "responses": [ { "status": 200, "content": [], "anchor": { "file": "app.py", "symbol": "index" } } ] }
  ]
}
```

`tests/fixtures/invalid/auth-not-array.model.json` — `auth` is an object, not an array:
```json
{
  "schema_version": "1.0",
  "project": { "name": "Demo", "version": "0.0.0" },
  "endpoints": [
    { "id": "get_root", "operationId": "getRoot", "group": "Root", "in_journey": true, "method": "GET", "path": "/", "source_path": "/", "summary": "Index",
      "handler": { "file": "app.py", "symbol": "index" }, "auth": { "scheme_name": "s", "kind": "none" },
      "request": { "media_type": null, "path_params": [], "query_params": [], "headers": [], "body": { "grounded": true, "schema": null, "gap": null } },
      "responses": [ { "status": 200, "description": "OK", "content": [], "anchor": { "file": "app.py", "symbol": "index" } } ] }
  ]
}
```

`tests/fixtures/invalid/enum-without-values.model.json` — a field of `type: enum` with no `enum` array:
```json
{
  "schema_version": "1.0",
  "project": { "name": "Demo", "version": "0.0.0" },
  "endpoints": [
    { "id": "post_x", "operationId": "postX", "group": "X", "in_journey": true, "method": "POST", "path": "/x", "source_path": "/x", "summary": "X",
      "handler": { "file": "app.py", "symbol": "x" }, "auth": [],
      "request": { "media_type": "application/json", "path_params": [], "query_params": [], "headers": [],
        "body": { "grounded": true, "schema": { "name": "root", "type": "object", "properties": [ { "name": "status", "type": "enum" } ] }, "gap": null } },
      "responses": [ { "status": 200, "description": "OK", "content": [], "anchor": { "file": "app.py", "symbol": "x" } } ] }
  ]
}
```

`tests/fixtures/invalid/apikey-without-in.model.json` — an `apiKey` auth scheme missing `in`:
```json
{
  "schema_version": "1.0",
  "project": { "name": "Demo", "version": "0.0.0" },
  "endpoints": [
    { "id": "get_root", "operationId": "getRoot", "group": "Root", "in_journey": true, "method": "GET", "path": "/", "source_path": "/", "summary": "Index",
      "handler": { "file": "app.py", "symbol": "index" }, "auth": [ { "scheme_name": "apikey", "kind": "apiKey", "name": "x-api-key" } ],
      "request": { "media_type": null, "path_params": [], "query_params": [], "headers": [], "body": { "grounded": true, "schema": null, "gap": null } },
      "responses": [ { "status": 200, "description": "OK", "content": [], "anchor": { "file": "app.py", "symbol": "index" } } ] }
  ]
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schema.py -v`
Expected: PASS — `test_schema_is_itself_valid`, one `valid` case, and four `invalid` cases all green.

- [ ] **Step 9: Add a .gitignore entry and commit**

Run:
```bash
grep -qxF '.venv/' .gitignore || printf '.venv/\n' >> .gitignore
git add schema/ tests/ .gitignore
git commit -m "Add frozen sidecar JSON Schema (API subset) + contract test harness"
```

---

### Task 2: Reference + narrative sections in the schema

Extends the frozen schema with the HTML/reference-only sections so a full sidecar validates.

**Files:**
- Modify: `schema/walkthrough-model.schema.json` (add top-level properties + `$defs`)
- Create: `tests/fixtures/valid/full-sections.model.json`
- Create: `tests/fixtures/invalid/boundary-missing-sources.model.json`

**Interfaces:**
- Consumes: the schema and `test_schema.py` harness from Task 1 (fixtures auto-discovered).
- Produces: top-level optional arrays `architecture`, `sequence`, `state`, `aws_calls`, `data_model`, `parameters`, `boundaries` with `$defs` `narrativeBlock`, `sequenceStep`, `stateEntry`, `awsCall`, `model`, `parameter`, `boundary`.

- [ ] **Step 1: Write the failing fixtures**

`tests/fixtures/valid/full-sections.model.json` — the minimal endpoint from Task 1 plus every reference/narrative section populated:
```json
{
  "schema_version": "1.0",
  "project": { "name": "Demo", "version": "0.0.0-from-walkthrough", "source_ref": "abc123" },
  "architecture": [ { "title": "App factory", "text": "create_app builds the app.", "sources": [ { "file": "app.py", "symbol": "create_app" } ] } ],
  "sequence": [ { "step": 1, "text": "Every request runs load_user.", "anchor": { "file": "app.py", "symbol": "load_user" } } ],
  "state": [ { "name": "session['uid']", "scope": "session", "lifecycle": "set on login; cleared on logout", "anchor": { "file": "auth.py", "symbol": "login" } } ],
  "endpoints": [
    { "id": "get_root", "operationId": "getRoot", "group": "Root", "in_journey": true, "method": "GET", "path": "/", "source_path": "/", "summary": "Index",
      "handler": { "file": "app.py", "symbol": "index", "line": 10 }, "auth": [],
      "request": { "media_type": null, "path_params": [], "query_params": [], "headers": [], "body": { "grounded": true, "schema": null, "gap": null } },
      "responses": [ { "status": 200, "description": "OK", "content": [ { "media_type": "text/html", "body": { "grounded": false, "schema": null, "gap": "template" } } ], "anchor": { "file": "app.py", "symbol": "index" } } ] }
  ],
  "aws_calls": [ { "service": "DynamoDB", "operation": "PutItem", "resource": { "table": "Ledger", "keys": ["pk", "sk"] }, "purpose": "persist", "anchor": { "file": "db.py", "symbol": "put" } } ],
  "data_model": [ { "name": "Post", "fields": [ { "name": "id", "type": "integer", "required": true, "nullable": false, "constraints": ["PRIMARY KEY"] } ], "indexes": [], "anchor": { "file": "schema.sql", "symbol": "post" } } ],
  "parameters": [ { "name": "SECRET_KEY", "kind": "config", "where_set": { "file": "app.py", "symbol": "create_app" }, "who_reads": [ { "file": "auth.py", "symbol": "login" } ] } ],
  "boundaries": [ { "severity": "crit", "title": "CSRF", "scenario": "no token on POST", "sources": [ { "file": "blog.py", "symbol": "create" } ] } ]
}
```

`tests/fixtures/invalid/boundary-missing-sources.model.json` — a boundary object without the required `sources` array (copy `full-sections` and drop `sources` from the boundary; keep everything else). The boundary becomes:
```json
"boundaries": [ { "severity": "crit", "title": "CSRF", "scenario": "no token on POST" } ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_schema.py -v`
Expected: FAIL — `full-sections` errors (top-level `additionalProperties:false` rejects the new sections) and `boundary-missing-sources` wrongly validates (no `boundaries` def yet).

- [ ] **Step 3: Add the top-level properties**

In `schema/walkthrough-model.schema.json`, add these keys to the top-level `properties` object (alongside `endpoints`):
```json
    "architecture": { "type": "array", "items": { "$ref": "#/$defs/narrativeBlock" } },
    "sequence": { "type": "array", "items": { "$ref": "#/$defs/sequenceStep" } },
    "state": { "type": "array", "items": { "$ref": "#/$defs/stateEntry" } },
    "aws_calls": { "type": "array", "items": { "$ref": "#/$defs/awsCall" } },
    "data_model": { "type": "array", "items": { "$ref": "#/$defs/model" } },
    "parameters": { "type": "array", "items": { "$ref": "#/$defs/parameter" } },
    "boundaries": { "type": "array", "items": { "$ref": "#/$defs/boundary" } }
```

- [ ] **Step 4: Add the `$defs`**

Add these members to the `$defs` object:
```json
    "narrativeBlock": {
      "type": "object", "required": ["title", "text", "sources"], "additionalProperties": false,
      "properties": { "title": { "type": "string" }, "text": { "type": "string" }, "sources": { "type": "array", "items": { "$ref": "#/$defs/anchor" } } }
    },
    "sequenceStep": {
      "type": "object", "required": ["step", "text", "anchor"], "additionalProperties": false,
      "properties": { "step": { "type": "integer", "minimum": 1 }, "text": { "type": "string" }, "anchor": { "$ref": "#/$defs/anchor" } }
    },
    "stateEntry": {
      "type": "object", "required": ["name", "scope", "lifecycle", "anchor"], "additionalProperties": false,
      "properties": { "name": { "type": "string" }, "scope": { "type": "string" }, "lifecycle": { "type": "string" }, "anchor": { "$ref": "#/$defs/anchor" } }
    },
    "awsCall": {
      "type": "object", "required": ["service", "operation", "purpose", "anchor"], "additionalProperties": false,
      "properties": { "service": { "type": "string" }, "operation": { "type": "string" }, "resource": { "type": "object" }, "purpose": { "type": "string" }, "anchor": { "$ref": "#/$defs/anchor" } }
    },
    "model": {
      "type": "object", "required": ["name", "fields", "anchor"], "additionalProperties": false,
      "properties": { "name": { "type": "string" }, "fields": { "type": "array", "items": { "$ref": "#/$defs/fieldSchema" } }, "indexes": { "type": "array", "items": { "type": "string" } }, "anchor": { "$ref": "#/$defs/anchor" } }
    },
    "parameter": {
      "type": "object", "required": ["name", "kind", "where_set", "who_reads"], "additionalProperties": false,
      "properties": { "name": { "type": "string" }, "kind": { "type": "string" }, "where_set": { "$ref": "#/$defs/anchor" }, "who_reads": { "type": "array", "items": { "$ref": "#/$defs/anchor" } } }
    },
    "boundary": {
      "type": "object", "required": ["severity", "title", "scenario", "sources"], "additionalProperties": false,
      "properties": { "severity": { "enum": ["info", "warn", "crit"] }, "title": { "type": "string" }, "scenario": { "type": "string" }, "sources": { "type": "array", "items": { "$ref": "#/$defs/anchor" } } }
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_schema.py -v`
Expected: PASS — two valid fixtures, five invalid fixtures.

- [ ] **Step 6: Commit**

Run:
```bash
git add schema/ tests/
git commit -m "Add reference + narrative sections to sidecar schema"
```

---

### Task 3: Flaskr golden sidecar fixture

A hand-authored, schema-valid sidecar for the Flaskr example (derived from `examples/Flaskr-Walkthrough.html`), pinned by a fact-assertion test. This is Plan A's acceptance anchor for "the sidecar captures a real app correctly."

**Files:**
- Create: `tests/fixtures/valid/flaskr.model.json`
- Create: `tests/test_flaskr_golden.py`

**Interfaces:**
- Consumes: the full schema (Tasks 1–2) and `test_schema.py` helpers (`load`, `make_validator`).
- Produces: `tests/fixtures/valid/flaskr.model.json` — a complete Flaskr sidecar used as a reference example in later docs.

- [ ] **Step 1: Write the fact-assertion test (the completeness contract)**

`tests/test_flaskr_golden.py`:
```python
from pathlib import Path
from test_schema import load, make_validator

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "valid" / "flaskr.model.json"


def _endpoints():
    return { (e["method"], e["path"]): e for e in load(GOLDEN)["endpoints"] }


def test_golden_validates_against_schema():
    errors = list(make_validator().iter_errors(load(GOLDEN)))
    assert errors == [], [e.message for e in errors]


def test_full_route_set_including_twins_and_smoke():
    keys = set(_endpoints().keys())
    expected = {
        ("GET", "/"),
        ("GET", "/auth/register"), ("POST", "/auth/register"),
        ("GET", "/auth/login"), ("POST", "/auth/login"),
        ("GET", "/auth/logout"),
        ("GET", "/create"), ("POST", "/create"),
        ("GET", "/{id}/update"), ("POST", "/{id}/update"),
        ("POST", "/{id}/delete"),
        ("GET", "/hello"),
    }
    assert expected <= keys, f"missing: {expected - keys}"


def test_hello_is_non_journey():
    assert _endpoints()[("GET", "/hello")]["in_journey"] is False


def test_create_post_is_form_encoded():
    assert _endpoints()[("POST", "/create")]["request"]["media_type"] == "application/x-www-form-urlencoded"


def test_create_post_success_is_302_with_location_and_no_401():
    statuses = { r["status"] for r in _endpoints()[("POST", "/create")]["responses"] }
    assert 302 in statuses
    assert 401 not in statuses  # auth gate redirects; never a synthesized 401
    redirect = next(r for r in _endpoints()[("POST", "/create")]["responses"] if r["status"] == 302)
    assert any(h["name"].lower() == "location" for h in redirect.get("headers", []))


def test_update_uses_integer_path_param():
    params = _endpoints()[("POST", "/{id}/update")]["request"]["path_params"]
    assert any(p["name"] == "id" and p["type"] == "integer" for p in params)


def test_delete_models_403_and_404_only_where_get_post_guards():
    statuses = { r["status"] for r in _endpoints()[("POST", "/{id}/delete")]["responses"] }
    assert {403, 404} <= statuses
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_flaskr_golden.py -v`
Expected: FAIL — `flaskr.model.json` does not exist.

- [ ] **Step 3: Author the golden fixture**

Create `tests/fixtures/valid/flaskr.model.json` by reading the facts out of `examples/Flaskr-Walkthrough.html`. It MUST contain all twelve `(method, path)` entries the test enumerates. Two fully-worked endpoints to follow as the pattern for the rest:

```json
{
  "schema_version": "1.0",
  "project": { "name": "Flaskr", "version": "0.0.0-from-walkthrough", "source_ref": "flask-tutorial" },
  "endpoints": [
    {
      "id": "get_hello", "operationId": "getHello", "group": "Smoke", "in_journey": false,
      "method": "GET", "path": "/hello", "source_path": "/hello", "summary": "Smoke-test route",
      "handler": { "file": "flaskr/__init__.py", "symbol": "hello", "line": 26 }, "auth": [],
      "request": { "media_type": null, "path_params": [], "query_params": [], "headers": [], "body": { "grounded": true, "schema": null, "gap": null } },
      "responses": [ { "status": 200, "description": "Returns the literal string 'Hello, World!'", "content": [ { "media_type": "text/html", "body": { "grounded": true, "schema": { "name": "root", "type": "string" }, "gap": null } } ], "anchor": { "file": "flaskr/__init__.py", "symbol": "hello", "line": 27 } } ]
    },
    {
      "id": "post_blog_update", "operationId": "updatePost", "group": "Blog", "in_journey": true,
      "method": "POST", "path": "/{id}/update", "source_path": "/<int:id>/update", "summary": "Update a post the current user owns",
      "handler": { "file": "flaskr/blog.py", "symbol": "update", "line": 100 },
      "auth": [ { "scheme_name": "session", "kind": "apiKey", "in": "cookie", "name": "session", "gap": "cookie name is configurable via SESSION_COOKIE_NAME; default assumed", "sources": [ { "file": "flaskr/auth.py", "symbol": "login_required", "line": 19 } ] } ],
      "request": {
        "media_type": "application/x-www-form-urlencoded",
        "path_params": [ { "name": "id", "type": "integer", "required": true, "anchor": { "file": "flaskr/blog.py", "symbol": "update" } } ],
        "query_params": [], "headers": [],
        "body": { "grounded": true, "schema": { "name": "root", "type": "object", "properties": [ { "name": "title", "type": "string", "required": true, "anchor": { "file": "flaskr/blog.py", "symbol": "update" } }, { "name": "body", "type": "string", "required": false, "anchor": { "file": "flaskr/blog.py", "symbol": "update" } } ] }, "gap": null }
      },
      "responses": [
        { "status": 302, "description": "On success, redirect to blog.index", "headers": [ { "name": "Location", "type": "string", "anchor": { "file": "flaskr/blog.py", "symbol": "update" } } ], "content": [], "anchor": { "file": "flaskr/blog.py", "symbol": "update", "line": 112 } },
        { "status": 200, "description": "Re-renders the update form with a flash on validation error", "headers": [], "content": [ { "media_type": "text/html", "body": { "grounded": false, "schema": null, "gap": "rendered template; shape not modeled" } } ], "anchor": { "file": "flaskr/blog.py", "symbol": "update" } },
        { "status": 404, "description": "get_post aborts 404 when the post id does not exist", "headers": [], "content": [], "anchor": { "file": "flaskr/blog.py", "symbol": "get_post" } },
        { "status": 403, "description": "get_post aborts 403 when the post is not owned by the current user", "headers": [], "content": [], "anchor": { "file": "flaskr/blog.py", "symbol": "get_post" } }
      ]
    }
  ]
}
```

Add the remaining ten endpoints in the same style (`GET /`, `GET|POST /auth/register`, `GET|POST /auth/login`, `GET /auth/logout`, `GET|POST /create`, `GET /{id}/update`, `POST /{id}/delete`), sorted by `id`. GET twins render a form → `200 text/html`; POST twins submit → `302` (success) and `200` (validation re-render). `GET /auth/logout` (Flask `@bp.route('/logout')` with no `methods=` — GET only) clears the session → `302`. Auth-gated endpoints carry the same `session` auth entry as `post_blog_update`; public ones (`GET /`, register, login) carry `auth: []`.

- [ ] **Step 4: Run both test files to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS — schema tests, golden validation, and all fact assertions green.

- [ ] **Step 5: Commit**

Run:
```bash
git add tests/fixtures/valid/flaskr.model.json tests/test_flaskr_golden.py
git commit -m "Add Flaskr golden sidecar fixture with fact-assertion tests"
```

---

### Task 4: Document the sidecar in `walkthrough-spec.md`

Add the schema definition and the sidecar-field → HTML-region mapping so the render step is reproducible.

**Files:**
- Modify: `skills/generate-walkthrough/walkthrough-spec.md`
- Create: `tests/test_docs_structure.py`

**Interfaces:**
- Consumes: the field names from the schema (Tasks 1–2).
- Produces: a `## Sidecar knowledge model` section in `walkthrough-spec.md` referenced by SKILL.md in Task 5.

- [ ] **Step 1: Write the failing structure test**

`tests/test_docs_structure.py`:
```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "skills" / "generate-walkthrough" / "walkthrough-spec.md"
SKILL = ROOT / "skills" / "generate-walkthrough" / "SKILL.md"


def test_spec_has_sidecar_section():
    text = SPEC.read_text()
    assert "## Sidecar knowledge model" in text
    assert "schema/walkthrough-model.schema.json" in text
    # every top-level sidecar key is documented
    for key in ["endpoints", "aws_calls", "data_model", "parameters", "boundaries", "architecture", "sequence", "state"]:
        assert key in text, f"{key} not documented in walkthrough-spec.md"


def test_spec_has_field_to_html_region_mapping():
    text = SPEC.read_text()
    assert "HTML region" in text  # the mapping table header
    for region in ["Foundations", "Primary journey", "Boundaries", "Parameter glossary"]:
        assert region in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_docs_structure.py::test_spec_has_sidecar_section -v`
Expected: FAIL — the section does not exist yet.

- [ ] **Step 3: Append the sidecar section to `walkthrough-spec.md`**

Add at the end of `skills/generate-walkthrough/walkthrough-spec.md`:
```markdown
## Sidecar knowledge model

Phase 2 emits `<Project>-walkthrough.model.json` **before** rendering the HTML, and the HTML is written from it. Its shape is pinned by `schema/walkthrough-model.schema.json` (JSON Schema Draft 2020-12) at the repo root; validate every sidecar against it.

Top-level keys:

- `endpoints` — every route (journey and non-journey), each with `method`, normalized `path` + `source_path`, `handler` anchor, `auth` (array of schemes), `request` (with explicit `media_type`), and `responses` (source-observed statuses only, each with a non-empty `description`, `headers`, and a `content` map). GET/POST on one route are two endpoints with distinct `operationId`s.
- `aws_calls` — AWS SDK side-effects (service, operation, resource, purpose, anchor).
- `data_model` — DB catalog (reference-only; NOT the API contract).
- `parameters` — config/env glossary (reference-only).
- `boundaries` — correctness/security findings (reference-only).
- `architecture`, `sequence`, `state` — narrative-bearing sections that back the prose HTML regions.

Anchors are symbol-primary (`file` + `symbol`, `line` optional). Unrecoverable data is `grounded:false` + a `gap` string — never invented.

### Sidecar field → HTML region

| Sidecar section | HTML region |
|-----------------|-------------|
| `architecture`, `sequence` | Foundations (architecture at a glance + sequence overview) |
| `endpoints`, `state` | Primary journey (one section per screen; state lifecycle) |
| `data_model` | Reference — data model / schemas |
| `parameters` | Parameter glossary |
| `boundaries` | Boundaries (grouped by severity) |
| `aws_calls` | Reference — external/AWS calls |

Every rendered HTML value (line, method, field, key) must trace to a sidecar entry; that identity is what phase 3 checks.
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_docs_structure.py -v`
Expected: PASS for both `test_spec_has_sidecar_section` and `test_spec_has_field_to_html_region_mapping` (the SKILL tests in Task 5 may still fail — that is expected).

- [ ] **Step 5: Commit**

Run:
```bash
git add skills/generate-walkthrough/walkthrough-spec.md tests/test_docs_structure.py
git commit -m "Document sidecar schema + field-to-HTML-region mapping in walkthrough-spec"
```

---

### Task 5: Invert phase 2 and rewrite phase 3 in `SKILL.md`

**Files:**
- Modify: `skills/generate-walkthrough/SKILL.md`
- Modify: `tests/test_docs_structure.py` (add SKILL assertions)

**Interfaces:**
- Consumes: the `## Sidecar knowledge model` section from Task 4.
- Produces: updated phase-2/phase-3 instructions the skill executor follows.

- [ ] **Step 1: Add the failing SKILL assertions**

Append to `tests/test_docs_structure.py`:
```python
def test_skill_phase2_is_sidecar_first():
    text = SKILL.read_text()
    assert "walkthrough-model.schema.json" in text
    assert "sidecar" in text.lower()
    # phase 2 builds the sidecar before rendering HTML
    assert "before" in text.lower() and "render" in text.lower()


def test_skill_phase3_has_three_way_verification():
    text = SKILL.read_text().lower()
    assert "sidecar vs source" in text
    assert "html vs sidecar" in text
    assert "narrative" in text and "source" in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_docs_structure.py -k skill -v`
Expected: FAIL — neither phrase set is present yet.

- [ ] **Step 3: Rewrite the Phase 2 heading/body**

In `skills/generate-walkthrough/SKILL.md`, replace the Phase 2 section (currently "## Phase 2 — Write one self-contained HTML file (solo — do not parallelize)" and its paragraph) with:
```markdown
## Phase 2 — Serialize the sidecar, then render HTML from it (solo)

Work in two ordered steps, single-threaded:

1. **Build the sidecar before rendering any HTML.** Serialize the verified coverage inventory into `<Project>-walkthrough.model.json`, conforming to `schema/walkthrough-model.schema.json`. This file — not the HTML — is the source of truth. Sort every array by a stable id/name. Mark anything unrecoverable as `grounded:false` + a `gap` string; never invent. Validate it against the schema before proceeding.
2. **Render the HTML from the sidecar.** Following `walkthrough-spec.md` (including the sidecar field → HTML region mapping), write the single self-contained HTML file from the sidecar's contents — structured sections become tables/flows, narrative sections become prose/callouts. Every value in the HTML must trace to a sidecar entry.

Keep a claim ledger as before; it and the sidecar carry the same facts, feeding phase 3.
```

- [ ] **Step 4: Rewrite the Phase 3 verification list**

In the Phase 3 section of `SKILL.md`, replace the opening line about what the loop runs with a three-way verification preamble, keeping the existing forward/reverse/boundaries/cross-consistency/whole-file passes beneath it:
```markdown
Phase 3 verifies three relationships (the HTML is no longer trusted just because it was written):

1. **Sidecar vs source** — the forward/reverse/boundaries passes below re-derive every sidecar claim from source.
2. **HTML vs sidecar** — a render-consistency check: every value shown in the HTML (line, method, field, key, formula) matches the sidecar entry it came from. This is an explicit cross-check of the emitted prose against the sidecar, not merely re-reading source.
3. **Narrative vs source** — prose claims in `architecture`/`sequence`/`state` and callouts are re-derived from source as before (they are not mechanically checkable against the sidecar alone).

Run every pass below; fix failures; re-run until a full pass yields zero WRONG, zero UNVERIFIABLE, an empty coverage gap, clean whole-file audits, and a clean HTML-vs-sidecar diff.
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_docs_structure.py -v`
Expected: PASS — all doc-structure tests green.

- [ ] **Step 6: Commit**

Run:
```bash
git add skills/generate-walkthrough/SKILL.md tests/test_docs_structure.py
git commit -m "Invert generate-walkthrough phase 2 (sidecar-first) and add three-way phase 3"
```

---

### Task 6: Changelog + narrative-quality regression checklist

Records the change and captures the manual acceptance step (the one thing pytest cannot check: that the inverted render still produces high-quality prose).

**Files:**
- Modify: `CHANGELOG.md`
- Create: `docs/superpowers/plans/plan-a-acceptance.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: an acceptance checklist referenced when running the skill end-to-end.

- [ ] **Step 1: Add an Unreleased changelog entry**

At the top of `CHANGELOG.md`, under a new `## [Unreleased]` heading (create it if absent), add:
```markdown
### Added
- `generate-walkthrough` now emits a machine-readable sidecar (`<Project>-walkthrough.model.json`) as its primary artifact, pinned by `schema/walkthrough-model.schema.json`. The HTML is rendered from the sidecar.

### Changed
- Phase 2 is now sidecar-first; phase 3 performs three-way verification (sidecar↔source, HTML↔sidecar, narrative↔source).
```

- [ ] **Step 2: Write the acceptance checklist**

`docs/superpowers/plans/plan-a-acceptance.md`:
```markdown
# Plan A acceptance — narrative-quality regression

Automated tests cover the schema and the Flaskr golden. This manual pass confirms the phase-2 inversion did not degrade prose quality. Run `generate-walkthrough` on a small real repo (e.g. the Flask tutorial) and confirm:

- [ ] `<Project>-walkthrough.model.json` is emitted and validates against `schema/walkthrough-model.schema.json`.
- [ ] The HTML Foundations section still reads as narrative prose (architecture-at-a-glance + a sequence overview), not a bare table dump.
- [ ] "How it works" callouts and positive assertions (e.g. "correct by construction") are still present and specific.
- [ ] Every route in the sidecar appears in the HTML, and every HTML line/method/field matches the sidecar (spot-check 5).
- [ ] Boundaries render grouped by severity with concrete failure scenarios.
- [ ] Both light and dark themes render; body does not scroll horizontally.
```

- [ ] **Step 3: Verify the changelog and checklist are consistent**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS — full suite still green (no code changed; confirms nothing regressed).

- [ ] **Step 4: Commit**

Run:
```bash
git add CHANGELOG.md docs/superpowers/plans/plan-a-acceptance.md
git commit -m "Add Unreleased changelog entry + Plan A narrative-quality acceptance checklist"
```

---

## Notes for the executor

- The schema at `schema/walkthrough-model.schema.json` is the **frozen contract**. Plan B (extract-api-spec) and the future PR-diff feature build on it — do not reshape it without updating this plan's tests.
- Run the whole suite between tasks: `.venv/bin/python -m pytest tests/ -v`.
- Tasks 4–6 edit LLM-facing skill prose; their tests are structural (the content is verified by the reviewer, not by assertion). Keep the wording faithful to `walkthrough-spec.md` and the spec.
