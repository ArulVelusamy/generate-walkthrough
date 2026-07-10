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
