# Design: Walkthrough sidecar + OpenAPI/Postman extraction

Date: 2026-07-09
Status: Approved design, ready for planning (3 review rounds applied)
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
validated against a concrete need instead of built speculatively. The target
codebases are AWS-native REST APIs (API Gateway + Lambda, JSON bodies, Cognito/JWT/
API-key/IAM auth, DynamoDB), so the schema is designed for those, with Flaskr
(form-encoded, session auth) as an additional shape it must also handle.

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
| Extraction impl | **Committed deterministic script** the skill invokes (not LLM-rendered) |

## Part 1 — The sidecar knowledge model

**Key idea:** the walkthrough already derives this data (architecture, sequence,
per-screen load→action→backend→state traces, data model, params, boundaries — each
`file:line`-anchored) and verifies it in phase 3. The sidecar is that verified
inventory, serialized. Generation **inverts**: phase 2 builds the sidecar first,
then renders the HTML from it.

**Projection scope — the sidecar backs the *whole* HTML.** The schema carries the
narrative-bearing sections (`architecture`, `sequence`, `state`, per-item
`notes`) *and* the structured API subset. Extraction consumes only `endpoints`
(plus `aws_calls`, rendered to the companion markdown); `data_model`, `parameters`,
`boundaries`, and all narrative fields are HTML/reference-only. This keeps a single
source without pretending a thin schema can regenerate rich prose.

**How the HTML "renders from" the sidecar.** This is not a mechanical template: the
lead LLM writes the HTML prose *from the sidecar's facts* (structured sections →
tables/flows; narrative sections → prose/callouts, using their `text` + anchors).
`walkthrough-spec.md` must therefore carry a full **sidecar-field → HTML-region
mapping** so the render is reproducible. Consequently phase-3(ii) below is an LLM
cross-check that every value in the emitted HTML matches the sidecar (right line,
method, field, key) — not a literal text diff.

### Shared types

**Anchor** — symbol is the stable key (survives line shifts, for the future PR
diff); line is a hint. Multi-site facts use `sources: [anchor]`.
```jsonc
"anchor": { "file": "flaskr/blog.py", "symbol": "create", "line": 88 }
```

**FieldSchema** — the neutral, recursive field/type model. Covers real JSON-REST
constructs (arrays, enums, formats, polymorphism, free-form maps); each extractor
renders it to its own dialect.
```jsonc
{
  "name": "items",
  "type": "string|number|integer|boolean|object|array|enum",
  "format": "date-time|uuid|int64|binary|email|...",   // optional; preserves fidelity
  "required": true, "nullable": false,
  "readOnly": false, "writeOnly": false,               // input vs output semantics
  "enum": ["DRAFT","PUBLISHED"],                        // when type == enum
  "items": { /* FieldSchema — array element */ },       // when type == array
  "properties": [ /* FieldSchema[] — object members */ ],
  "additionalProperties": true,                         // or a FieldSchema — free-form maps
  "oneOf": [ /* FieldSchema[] */ ], "discriminator": "type",   // polymorphic bodies
  "constraints": ["PRIMARY KEY","FK -> user(id)"],      // documented, non-mapped extras
  "anchor": { /*...*/ }
}
```

**AuthScheme** — open model (a closed `session|bearer|none` enum cannot express
API-key, Cognito/JWT, OAuth2 scopes, or IAM SigV4). Names are grounded or marked as
gaps — never defaulted.
```jsonc
{
  "scheme_name": "cognito",                       // securityScheme key
  "kind": "apiKey|http|oauth2|openIdConnect|mutualTLS|none|custom",
  "in": "header|cookie|query",                    // apiKey only
  "name": "x-api-key",                            // apiKey param/cookie name — grounded or gap
  "scheme": "bearer|basic",                       // http only
  "bearerFormat": "JWT",                          // optional
  "scopes": ["posts.write"],                      // per-operation required scopes
  "sources": [ /*anchors*/ ],
  "gap": null                                     // e.g. "IAM SigV4 — not expressible in OpenAPI"
}
```
IAM SigV4 and custom Lambda authorizers set `kind:"custom"` + a `gap` string; they
are never silently rendered as `none`.

### Schema (`<Project>-walkthrough.model.json`)

```jsonc
{
  "schema_version": "1.0",
  "project": { "name": "Flaskr", "version": "0.0.0-from-walkthrough",   // → info.version
               "source_ref": "<git commit/branch if available>" },

  // ---- narrative-bearing sections (HTML-only; extraction ignores) ----
  "architecture": [ { "title": "Application factory", "text": "...", "sources": [ /*anchors*/ ] } ],
  "sequence":     [ { "step": 1, "text": "Every request first runs load_logged_in_user", "anchor": { /*...*/ } } ],
  "state":        [ { "name": "session['user_id']", "scope": "session|request(g)|global",
                      "lifecycle": "set on login; cleared on logout", "anchor": { /*...*/ } } ],

  // ---- API subset consumed by extract-api-spec: endpoints (+ aws_calls → companion md) ----
  "endpoints": [{                              // sorted by id — deterministic
    "id": "post_blog_create",                  // stable slug: method + route/handler
    "operationId": "createPost",               // UNIQUE across the spec (GET/POST twins differ)
    "group": "Blog",                           // → OpenAPI tag + Postman folder
    "in_journey": true,                        // false for smoke routes (GET /hello); still emitted
    "method": "POST",
    "path": "/create",                         // NORMALIZED (see path-syntax transform, Part 2)
    "source_path": "/create",                  // verbatim source route (Flask syntax) for provenance
    "summary": "...",
    "handler": { "file": "flaskr/blog.py", "symbol": "create", "line": 88 },
    "auth": [ /* AuthScheme[] — empty means unauthenticated */ ],
    "request": {
      "media_type": "application/x-www-form-urlencoded",  // NOT assumed JSON
      "path_params": [ /* FieldSchema[] (in: path) */ ],
      "query_params": [], "headers": [],
      "body": { "grounded": true, "schema": { /* FieldSchema (object) */ }, "gap": null }
    },
    "responses": [                             // one entry per STATUS; source-observed only
      { "status": 302, "description": "redirect to blog.index",   // description REQUIRED, non-empty
        "headers": [ { "name": "Location", "type": "string", "anchor": { /*...*/ } } ],
        "content": [], "anchor": { /*...*/ } },
      { "status": 200, "description": "re-renders form with flash on validation error",
        "headers": [],
        "content": [ { "media_type": "text/html",
                       "body": { "grounded": false, "schema": null, "gap": "rendered template" } } ],
        "anchor": { /*...*/ } }
    ],
    "callers": [ { "screen": "Blog index", "anchor": { /*...*/ } } ]
  }],

  "aws_calls":  [ { "service": "DynamoDB", "operation": "PutItem",
                    "resource": { "table": "...", "keys": ["pk","sk"] },
                    "purpose": "...", "anchor": { /*...*/ } } ],

  // reference-only: DB catalog. NOT emitted into OpenAPI components (DB rows != payloads).
  "data_model": [ { "name": "Post",
                    "fields": [ /* FieldSchema[] with constraints/nullable */ ],
                    "indexes": [], "anchor": { /*...*/ } } ],

  // reference-only (HTML): config/env glossary
  "parameters": [ { "name": "SECRET_KEY", "kind": "config|env",
                    "where_set": { /*anchor*/ }, "who_reads": [ { /*anchor*/ } ] } ],

  // reference-only (HTML): correctness/security findings
  "boundaries": [ { "severity": "crit", "title": "...", "scenario": "...", "sources": [ /*anchors*/ ] } ]
}
```

### Rules

- **Responses are source-observed only.** A status enters `responses[]` only if
  emitted in source. Auth gates are modeled as what the code does — Flaskr's
  `login_required` is a `302`, *not* a synthesized `401`. Each response has a
  non-empty `description`, a `headers[]` list (captures `Location`, pagination,
  rate-limit, `Set-Cookie`), and a `content[]` map keyed by media type (content
  negotiation).
- **Body schemas come from body fields, keyed by `operationId` — never from
  `data_model`.** DB requiredness (`NOT NULL`) is not payload requiredness; server-set
  fields (`id`, `createdAt`, `pk`) use `readOnly`. `data_model` stays a separate DB
  catalog for the HTML reference section, not the API contract.
- **GET/POST twins are separate endpoints** with distinct `operationId`s.
- **Non-journey routes still emitted** with `in_journey:false`, so "operations ==
  endpoints" is well-defined.
- **Gaps explicit** (`grounded:false` + `gap`); never invented.
- **Deterministic ordering** — every array sorted by stable id/name on emit.
- **No double-sourcing** — `parameters` is the config/env glossary only; per-endpoint
  request params live under `endpoints`.

### Changes to `generate-walkthrough`

- `SKILL.md` phase 2: build the sidecar first, then render HTML from it.
- `walkthrough-spec.md`: add a **"Sidecar knowledge model"** section defining the
  schema and which sections back which HTML regions.
- **Phase 3 verifies three things** (replacing "verified by construction"):
  (i) sidecar vs source (existing loop); (ii) HTML vs sidecar (render-consistency
  diff, catching a wrong line/method/field in prose); (iii) narrative prose vs source
  (as today — not mechanically checkable against the sidecar alone).

## Part 2 — The `extract-api-spec` skill

**Input:** an existing `<Project>-walkthrough.model.json`. If absent, the skill tells
the user to run `generate-walkthrough` first — it never silently re-derives.

**Implementation — a committed deterministic script, not LLM prose.** The skill ships
`skills/extract-api-spec/serialize.py`, written and committed as part of Plan B (it is
a normal source file authored during implementation, not regenerated by the agent per
run; it handles *arbitrary* sidecars conforming to the schema). It is **stdlib-only**
and emits **JSON** for both OpenAPI and Postman via `json.dumps(..., sort_keys=True,
indent=2)` — Python has no stdlib YAML writer, and 3.0.3 is fully valid as JSON, so JSON
is what makes "byte-identical on re-run" real and dependency-free. (An optional `.yaml`
convenience copy can be produced only if PyYAML is present; the canonical, tested
artifact is JSON.) The agent's job is to **invoke** the script
(`python serialize.py <sidecar.json> <outdir>`), then run validation — not to
hand-render. Both OpenAPI and Postman come from one normalized model in the same
script, so the path-syntax and auth transforms are shared and cannot drift.

### Outputs (next to the HTML)

`<Project>-openapi.json` (3.0.3, JSON — canonical artifact) ·
`<Project>.postman_collection.json` (v2.1) ·
`<Project>.postman_environment.json` (`baseUrl` + auth vars) ·
`<Project>-aws-calls.md` (AWS SDK companion). Optional `<Project>-openapi.yaml` when
PyYAML is available.

### Path-syntax transform (shared by both targets)

Resolve blueprint/router prefixes into the full path and typed converters into
param types, once:

| Source (`source_path`) | Normalized `path` + param | Postman `url` |
|------------------------|---------------------------|---------------|
| `/<int:id>/update` (blog bp) | `/{id}/update`, `id` path param `integer` | `/:id/update` + `url.variable[{key:id}]` |
| `/register` (auth bp, prefix `/auth`) | `/auth/register` | `/auth/register` |

### Mapping — sidecar → OpenAPI 3.0.3

| Sidecar | OpenAPI |
|---------|---------|
| `project.name` / `project.version` | `info.title` / `info.version` (both required) |
| `endpoints[]` (incl. twins) | `paths.{path}.{method}` |
| `operationId` / `group` / `summary` | `operationId` (unique) / `tags` / `summary` |
| `path/query/header params` | `parameters[]` (`in:`, `required`, `schema` from FieldSchema) |
| `request.body.schema` + `media_type` | `requestBody.content[media_type].schema` → **`$ref components.schemas.<operationId>Request`** |
| `responses[]` (per status, `content[]`) | `responses.{status}` with required `description`, `headers`, and a `content` map (multi media type) → response bodies **`$ref …Response{status}`** |
| `auth[]` | `components.securitySchemes` (from AuthScheme) + per-op `security` (incl. `scopes`); SigV4/custom → documented gap, never `none` |
| body FieldSchemas | `components.schemas` keyed by `operationId` (always emitted + `$ref`d; no field-name-match heuristic) |
| `data_model` | **not emitted** into OpenAPI (DB catalog ≠ API contract) |
| — | `servers: [{ url: "{baseUrl}", variables: { baseUrl: { default: "https://REPLACE_ME", description: "not recoverable from source — set before use" } } }]` |
| `grounded:false` | `description` marker **and** top-level `x-coverage-gaps` list |

FieldSchema → OpenAPI: `type/format/enum/items/properties/additionalProperties/
nullable/readOnly/writeOnly` map directly. **Polymorphism needs hoisting:** 3.0.3's
`discriminator` is an object (`propertyName` + `mapping`) that can only reference
*named* `$ref`ed schemas, so the script hoists each `oneOf` branch into
`components.schemas` and synthesizes `discriminator.propertyName` (from FieldSchema's
`discriminator`) + `mapping`. Unknown type → `{}` (any) with a gap note and **no bare
`nullable`**.

### Postman (Collection v2.1)

Folders by `group`. Body mode by media type: `application/json` → `mode:"raw"` +
`options.raw.language:"json"`; `x-www-form-urlencoded` → `mode:"urlencoded"`;
`multipart/form-data` → `mode:"formdata"`. Path params → `url.variable[]`. Auth:
`http/bearer` → collection `{{token}}`; **`apiKey`-in-cookie / session → cookie jar,
not the `auth` object**; `apiKey`-in-header → a header with `{{apiKey}}`. Environment
file ships `baseUrl` + the relevant auth vars.

### AWS companion

`<Project>-aws-calls.md` renders `aws_calls[]` as a table: service → operation →
resource (table/keys) → purpose → anchor. AWS calls never enter the OpenAPI.

### Validation

The **deterministic core** (serialize.py, stdlib-only) is separate from **best-effort
validation** (external tools the agent runs if available). Determinism and no-invention
are guaranteed by the core; structural validation is tooling on top.

1. **Structural (best-effort, named tools)** — validate the OpenAPI with
   `openapi-spec-validator` (or `swagger-cli`/Redocly if present); validate the Postman
   collection against the published Collection v2.1 JSON Schema (e.g. via `ajv`/newman).
   If none are installed, the agent does a structural self-check (every Response has a
   `description`; `info.title`/`version` present; no bare `nullable`).
2. **No invention (in-core)** — every OpenAPI operation & Postman request maps to one
   sidecar `id`; no response status lacks a sidecar anchor; no security scheme is
   invented for an unauthenticated endpoint.
3. **Gap preservation (in-core)** — every `grounded:false` surfaces as a visible marker.
4. **Determinism (in-core)** — same sidecar in → byte-identical JSON (guaranteed by
   `sort_keys=True` canonical serialization).

## Part 3 — Packaging & file layout

- New `skills/extract-api-spec/{SKILL.md, mapping-spec.md, serialize.py}`.
- `generate-walkthrough`: update `SKILL.md` (sidecar-first phase 2, three-way phase
  3) and `walkthrough-spec.md` (sidecar schema section).
- Register `extract-api-spec` in `.claude-plugin`; bump to **1.2.0**; update
  CHANGELOG + README.
- Outputs beside `<Project>-Walkthrough.html` (filenames as in Part 2; OpenAPI is
  `<Project>-openapi.json`).

### Implementation sequencing (two plans; freeze the schema first)

The **sidecar schema (Part 1) is the shared contract** — pin it before either plan.

- **Plan A — sidecar + `generate-walkthrough` inversion.** Emit the sidecar; invert
  phase 2 (sidecar-first render); add the three-way phase 3; add the sidecar-field →
  HTML-region mapping to `walkthrough-spec.md`. Golden: the Flaskr sidecar. Because
  this reworks a shipped 1.1.0 skill, include a **regression check that the HTML's
  narrative quality survives the inversion** (Foundations/callouts/assertions still
  read as before).
- **Plan B — `extract-api-spec`.** `serialize.py` + validators + goldens A and B.
  Depends only on the frozen schema, not on Plan A's code — golden B is a hand-authored
  sidecar, so Plan B is testable independently and can proceed in parallel once the
  schema is pinned.

## Part 4 — Testing

**Golden target A — Flaskr** (in-repo; REST, form-encoded, session auth):

- **Sidecar:** full route set incl. **GET/POST twins** and the non-journey route —
  `GET /`, `GET|POST /auth/register`, `GET|POST /auth/login`, `GET /auth/logout`
  (302), `GET|POST /create`, `GET|POST /{id}/update`, `POST /{id}/delete`,
  `GET /hello` (`in_journey:false`). POST bodies `x-www-form-urlencoded`; success →
  `302` (with `Location` header); validation error → `200` re-render;
  **auth-gate → `302`, never `401`**; `get_post` → `404`/`403` on update/delete only.
- **OpenAPI (`.json`):** validates as 3.0.3, renders in Swagger UI, unique
  `operationId`s, `/{id}` integer path param, every response has a `description`, no
  status without an anchor.
- **Postman:** validates as v2.1, imports, `url.variable` for `:id`, urlencoded bodies.
- **Determinism:** run the script twice → byte-identical JSON.
- **Gap preservation:** the 200 template re-render is a gap in both sidecar and OpenAPI.
- **No invention:** `#OpenAPI operations == #sidecar endpoints`.

**Golden target B — AWS/JSON fixture** (hand-authored sidecar; exercises what Flaskr
can't): JSON bodies with **arrays/enums/`format: date-time`+`uuid`/`readOnly`
server fields/a paginated list response with `nextToken` + a `Location`/cursor
header**; **`apiKey`-in-header (`x-api-key`)** and **Cognito `oauth2`/JWT with per-op
`scopes`** auth; and `aws_calls[]` (`PutItem` + `GetObject`). Asserts: OpenAPI models
arrays/enums/formats/scopes and emits an `x-api-key` `apiKey` scheme (not `none`);
`<Project>-aws-calls.md` renders correctly; AWS calls never leak into the OpenAPI;
IAM-SigV4 entry surfaces as a documented gap.

## Non-goals

- The PR-review + living-doc feature (its own future spec). The sidecar's stable
  ids, symbol anchoring, and deterministic ordering were chosen to serve it.
- API Gateway `x-amazon-apigateway-*` extensions (vanilla 3.0.3 only).
- Best-effort/inferred schemas (ground-only).
- GraphQL and other non-REST API styles.
