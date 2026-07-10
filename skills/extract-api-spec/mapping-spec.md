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
