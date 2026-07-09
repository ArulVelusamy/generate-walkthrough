# Walkthrough HTML output spec

The exact structure and design system for the phase-2 file. One self-contained `.html`, no external requests (inline all CSS/JS; no CDN, remote fonts, scripts, or images).

## Document head (required)

Start the file with these, in order, before `<title>`:

```html
<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
```

`<meta charset="utf-8">` is mandatory — without it, em-dashes/bullets/arrows render as mojibake when the file is served over HTTP (as opposed to opened via `file://`). The viewport meta is mandatory so the responsive layout holds on mobile. Both must appear within the first 1024 bytes.

## Layout

Two columns: a sticky left sidebar TOC (~288px) + a centered main column (`max-width: 820px`). The TOC is grouped with uppercase group labels and numbered mono links. **Derive group names from this system's actual arc** — foundations/overview, one or more for the primary journey, secondary flows, reference, parameter glossary, boundaries. The active section highlights on scroll (inlined IntersectionObserver).

## Design tokens (CSS variables in `:root`)

Support light AND dark. Provide three blocks: `:root` (light default), `@media (prefers-color-scheme:dark)`, and explicit `:root[data-theme="dark"]` / `:root[data-theme="light"]` overrides so a manual toggle wins both ways.

- Neutrals: `--bg`, `--surface`, `--surface-2`, `--ink`, `--ink-2`, `--line`, `--line-2`.
- One accent: `--accent`, `--accent-2`, `--accent-soft` (pick a fitting accent for the project).
- Semantic color+bg pairs: `--good/--good-bg`, `--warn/--warn-bg`, `--crit/--crit-bg`, `--info/--info-bg`.
- Code: `--code`, `--code-bg`, `--code-line`. Plus `--shadow`.
- Fonts: `--sans` (system UI stack), `--mono` (SF Mono/Menlo stack), `--serif` (Iowan/Palatino/Georgia stack).

## Typography

- Headings in `--serif`, semibold, tight tracking, `text-wrap:balance` (`h1` large clamp; `h2` ~27px; `h3` ~17px; `h4` ~14px).
- Body in `--sans`, ~15px, line-height ~1.6.
- `code` in `--mono` on `--code-bg` with a subtle border — mono for every identifier: files, routes, functions, keys, params.
- Each `<section>` (with an `id`) opens with a small mono **stage badge** in its `h2`, styled as an accent pill.

## Reusable components (build these classes, use consistently)

- **Callout box** — `.call` / `.call-top` / `.call-tag` / `.call-body`, for "how it works" asides.
- **Severity paragraphs** — tinted left-border blocks `.okp` / `.infop` / `.warnp` / `.critp`; bugs under a ⚠ heading.
- **Flow / sequence diagram** — `.flow` with numbered `.num` steps and `.row` lines, for request→handler→store→response chains; label each step (BRIDGE / POST / Handler / Returns …).
- **File/path pills** — `.file`, `.path`, to tag which source file a section covers.
- **Tables** — wrapped in `.tbl-wrap` (horizontal scroll on overflow), for schemas and the parameter glossary.
- **Legend/status dots** — `.dot`, `.pill`, `.sev` where useful.

## Polish

- Page body never scrolls horizontally (wide tables/diagrams scroll inside their own container).
- `scroll-behavior:smooth` with a `prefers-reduced-motion` guard.
- A small light/dark/auto theme toggle that stamps `data-theme` on `<html>` (inlined JS).
- A short hero at top: mono eyebrow, serif `h1`, and a one-sentence lede describing the arc in the system's own terms.

## Document arc

1. **Foundations** — architecture at a glance + one end-to-end sequence overview.
2. **Primary journey** — one section per screen/step, in order, tracing load → action → backend → state, bugs flagged inline.
3. **Secondary flows** — corrections, edits, archival, status transitions, schedulers.
4. **Reference** — persisted-state keys, data model / schemas + indexes.
5. **Parameter glossary** — every parameter: what it is, where set, who reads it.
6. **Boundaries** — correctness/security/consistency issues, grouped by severity, each citing the file and the concrete failure scenario.

## Sidecar knowledge model

Phase 2 emits `<Project>-walkthrough.model.json` **before** rendering the HTML, and the HTML is written from it. Its shape is pinned by `schema/walkthrough-model.schema.json` (JSON Schema Draft 2020-12) at the repo root; validate every sidecar against it.

Top-level keys:

- `endpoints` — every route (journey and non-journey), each with `method`, normalized `path` + `source_path`, `handler` anchor, `auth` (array of schemes), `request` (with explicit `media_type`), and `responses` (source-observed statuses only, each with a non-empty `description`, `headers`, and a `content` array (one entry per media type)). GET/POST on one route are two endpoints with distinct `operationId`s.
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
