# Design: Walkthrough sidecar + OpenAPI/Postman extraction

Date: 2026-07-09
Status: Approved design, pre-implementation
Scope: This spec covers **two** deliverables — (1) a machine-readable *sidecar*
emitted by `generate-walkthrough`, and (2) a new `extract-api-spec` skill that
turns the sidecar into an OpenAPI 3.0.3 spec + Postman collection. A third,
future feature — PR review against the doc + living-doc updates on AWS CodeCommit
— is **out of scope here** but informed the sidecar's shape.

## Context & motivation

`generate-walkthrough` today produces one self-contained HTML file that traces a
codebase's primary journey, every claim anchored to `file:line`, verified to zero
in a phase-3 loop. Two new needs consume that walkthrough as a *source of truth*:

- Review CodeCommit PRs against the walkthrough, and on approval update it so it
  stays authoritative (a living doc).
- Extract Swagger/OpenAPI + a Postman collection from the walkthrough's context.

HTML is great for humans but hostile to machine diffing (PR review) and structured
extraction (OpenAPI/Postman). Rather than parse HTML back or re-derive from source
each time, we add a **structured sidecar** as the real source of truth. This spec
designs the sidecar together with its first consumer (extraction), so the schema is
validated against a concrete need instead of built speculatively.

### Decisions locked during brainstorming

| Decision | Choice |
|----------|--------|
| Source of truth | Structured machine-readable sidecar (JSON) alongside HTML |
| First consumer | OpenAPI/Postman extraction (stress-tests the schema before the harder PR feature) |
| API surface | REST endpoints → OpenAPI; AWS SDK calls → companion reference list |
| Fidelity | Ground-only; mark gaps explicitly, never invent |
| Packaging | Sidecar built into `generate-walkthrough`; extraction is a separate skill |
| OpenAPI flavor | Vanilla OpenAPI 3.0.3 (tool-agnostic; no AWS coupling) |
| Generation order | **Sidecar-first** — HTML renders from the sidecar |
| Source anchoring | **Symbol-primary** (`file` + `symbol`), `line` as a hint |

## Part 1 — The sidecar knowledge model

**Key idea:** the walkthrough already derives this exact data (method, route,
handler, auth, DB reads/writes, returns, params, schemas, boundaries — each
`file:line`-anchored) and verifies it in phase 3. The sidecar is that verified
coverage inventory, serialized. To make "verified by construction" *true* rather
than hoped-for, generation **inverts**: phase 2 builds the sidecar first, then
renders the HTML from it. The sidecar is the single source; the HTML is a
projection; they cannot drift.

### Anchor type

Used anywhere a claim cites source. Symbol is the stable key (survives edits that
shift line numbers — essential for the future sidecar-vs-sidecar PR diff); line is
a hint.

```jsonc
"anchor": { "file": "flaskr/blog.py", "symbol": "create", "line": 88 }
```

### Schema (`<Project>-walkthrough.model.json`)

```jsonc
{
  "schema_version": "1.0",
  "project": { "name": "Flaskr", "source_ref": "<git commit/branch if available>" },

  "endpoints": [{                              // sorted by id — deterministic
    "id": "post_blog_create",                  // stable slug: method + route/handler
    "operationId": "createPost",
    "group": "Blog",                           // journey screen / path segment → OpenAPI tag + Postman folder
    "method": "POST", "path": "/create",
    "summary": "...",
    "handler": { "file": "flaskr/blog.py", "symbol": "create", "line": 88 },
    "auth": { "type": "session|bearer|none", "sources": [ { /*anchor*/ } ] },  // array: may be enforced in >1 place
    "request": {
      "media_type": "application/x-www-form-urlencoded",  // NOT assumed JSON
      "path_params": [], "query_params": [], "headers": [],
      "body": {
        "grounded": true,
        "fields": [ { "name": "title", "type": "string", "required": true, "anchor": { /*...*/ } } ],
        "gap": null
      }
    },
    "responses": [                             // non-2xx captured, incl. redirects
      { "status": 302, "media_type": null, "note": "redirect to blog.index",
        "body": { "grounded": true, "fields": [], "gap": null }, "anchor": { /*...*/ } },
      { "status": 200, "media_type": "text/html",
        "body": { "grounded": false, "fields": null, "gap": "rendered template; shape not modeled" },
        "anchor": { /*...*/ } }
    ],
    "callers": [ { "screen": "Blog index", "anchor": { /*...*/ } } ]
  }],

  "aws_calls":  [ { "service": "DynamoDB", "operation": "PutItem",
                    "resource": { "table": "...", "keys": ["pk","sk"] },
                    "purpose": "...", "anchor": { /*...*/ } } ],

  "data_model": [ { "name": "Post",
                    "fields": [ { "name": "title", "type": "string", "anchor": { /*...*/ } } ],
                    "indexes": [], "anchor": { /*...*/ } } ],

  "parameters": [ { "name": "SECRET_KEY", "kind": "config|env",
                    "where_set": { /*anchor*/ }, "who_reads": [ { /*anchor*/ } ] } ],

  "boundaries": [ { "severity": "crit", "title": "...", "scenario": "...", "anchor": { /*...*/ } } ]
}
```

### Rules

- **Neutral field model.** Bodies/params use `name / type / required / nested /
  enum?` — *not* raw JSON Schema. Fields are read off source, so a neutral model is
  honest and lets each extractor render to its own dialect (OpenAPI 3.0.3 today,
  others later) without down-conversion.
- **Media types are explicit.** `request.media_type` and `responses[].media_type`
  are captured, never assumed `application/json` (Flaskr is form-encoded).
- **Non-2xx captured.** Redirects (302) and errors (400/401/404) are first-class
  entries in `responses[]`.
- **Gaps explicit.** Anything not recoverable is `grounded:false` + a `gap` reason
  string. Never invented.
- **Deterministic ordering.** Every array is sorted by stable id/name on emit, so
  two regenerations (and future cross-commit diffs) are clean.
- **No double-sourcing.** `parameters` is the cross-cutting glossary (config/env
  and derived values) only; per-endpoint request params live under `endpoints`.
- **`sources` is an array** where a single claim is enforced in more than one place
  (e.g. auth in middleware *and* handler).

### Changes to `generate-walkthrough`

- `SKILL.md` phase 2: build the sidecar from the verified inventory first, then
  render HTML from the sidecar.
- `walkthrough-spec.md`: add a **"Sidecar knowledge model"** section defining the
  schema above.
- Phase 3 verifies the sidecar with the existing forward/reverse/boundaries loop;
  the HTML is correct because it is derived from verified data.

## Part 2 — The `extract-api-spec` skill

**Input:** an existing `<Project>-walkthrough.model.json`. If absent, the skill
instructs the user to run `generate-walkthrough` first — it does not silently
re-derive from source. One trusted input, three renderers in a single pass so the
outputs cannot diverge.

### Outputs (next to the HTML)

- **`<Project>-openapi.yaml`** — OpenAPI 3.0.3.
- **`<Project>.postman_collection.json`** — Postman Collection v2.1.
- **`<Project>.postman_environment.json`** — `baseUrl` + auth variables.
- **`<Project>-aws-calls.md`** — companion AWS SDK reference (not expressible in OpenAPI).

### Mapping — sidecar → OpenAPI 3.0.3

| Sidecar | OpenAPI |
|---------|---------|
| `endpoints[]` | `paths.{path}.{method}` |
| `id` / `operationId` | `operationId` |
| `group` | `tags: [group]` |
| `summary` | `summary` |
| `request.path_params/query_params/headers` | `parameters[]` (`in: path/query/header`, `required`, `schema`) |
| `request.body.fields` + `media_type` | `requestBody.content[media_type].schema` |
| `responses[]` (incl. non-2xx) | `responses[status].content[media_type].schema` |
| `auth` | `components.securitySchemes` + `security` (`session`→cookie/apiKey, `bearer`→http bearer) |
| `data_model[]` | `components.schemas` (referenced by `$ref` when a body's fields match a named model, else inlined) |
| — (not in source) | `servers: [{ url: "{baseUrl}", variables: { baseUrl: { default: "https://REPLACE_ME", description: "not recoverable from source — set before use" } } }]` |
| `grounded:false` | `description` marker **and** a top-level `x-coverage-gaps` list |

Neutral type → OpenAPI: `string/number/integer/boolean/object/array/enum`
map directly; nested fields → nested object properties; unknown type → `{}` (any)
with a gap note.

### Postman + AWS companion

- **Postman** is generated **from the sidecar directly** (not via the OpenAPI) so
  anchors and gap notes survive. Folders by `group`; each request is method +
  `{{baseUrl}}` + path + headers + a by-type placeholder body; auth via a
  collection variable. A matching environment file ships `baseUrl` + auth vars.
- **`<Project>-aws-calls.md`** renders `aws_calls[]` as a table: service →
  operation → resource (table/keys) → purpose → anchor.

### Grounding & verification

The sidecar is already verified in walkthrough phase 3, so extraction is a
**faithful, deterministic transform — not a re-derivation**. After emit, validate:

1. **Structural** — OpenAPI validates against 3.0.3; Postman validates against the
   Collection v2.1 schema.
2. **No invention** — every OpenAPI operation and Postman request maps back to
   exactly one sidecar endpoint `id`; nothing exists that isn't in the sidecar.
3. **Gap preservation** — every sidecar `grounded:false` appears as a visible marker
   in the output; none dropped or filled.
4. **Determinism** — paths/operations sorted; re-running yields byte-identical
   output (safe to commit and diff).

The skill may re-open one cited anchor to disambiguate a field type, but does not
re-derive.

## Part 3 — Packaging & file layout

- New `skills/extract-api-spec/SKILL.md` + `skills/extract-api-spec/mapping-spec.md`
  (mirrors `walkthrough-spec.md`).
- `generate-walkthrough`: update `SKILL.md` (sidecar-first phase 2) and
  `walkthrough-spec.md` (sidecar schema section).
- Register `extract-api-spec` in `.claude-plugin`; bump to **1.2.0**; update
  CHANGELOG + README.
- Output filenames, all beside `<Project>-Walkthrough.html`:
  `<Project>-walkthrough.model.json`, `<Project>-openapi.yaml`,
  `<Project>.postman_collection.json`, `<Project>.postman_environment.json`,
  `<Project>-aws-calls.md`.

## Part 4 — Testing

Golden test on **Flaskr** (already an example in this repo):

- **Sidecar:** regenerate → assert routes (`/`, `/auth/register`, `/auth/login`,
  `/auth/logout`, `/create`, `/<id>/update`, `/<id>/delete`), correct methods,
  `application/x-www-form-urlencoded` media type, and the `302` redirects.
- **OpenAPI:** validates as 3.0.3 (parser/linter) and renders in Swagger UI.
- **Postman:** validates as Collection v2.1 and imports.
- **Determinism:** run extraction twice → byte-identical outputs.
- **Gap preservation:** an unmodeled response body surfaces as a gap in both sidecar
  and OpenAPI.
- **No invention:** `#OpenAPI operations == #sidecar endpoints`.

## Non-goals

- The PR-review + living-doc feature (its own future spec). The sidecar's stable
  ids, symbol anchoring, and deterministic ordering were chosen to serve it.
- API Gateway `x-amazon-apigateway-*` extensions (vanilla 3.0.3 only).
- Best-effort/inferred schemas (ground-only).
- GraphQL and other non-REST API styles.
