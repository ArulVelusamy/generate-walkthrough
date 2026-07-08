# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Nothing yet._

## [1.0.0] — 2026-07-08

First public release: the `generate-walkthrough` skill, packaged as an
installable Claude Code plugin.

### Added
- **`generate-walkthrough` skill** — turns any codebase into one
  self-contained HTML walkthrough: a forensic, screen-by-screen trace from
  first entry point to terminal outcome, with a data model, a parameter
  glossary, and a security/correctness "boundaries" section. Every factual
  claim is independently re-derived from source (`file:line`) or deleted.
- **Three-phase workflow** — parallel read-only investigators → single-threaded
  HTML write → parallel verifiers looped until zero unverified claims and an
  empty coverage diff (`skills/generate-walkthrough/SKILL.md`).
- **HTML output spec** — layout, design tokens, typography, components, and
  document arc for the generated file
  (`skills/generate-walkthrough/walkthrough-spec.md`).
- **Claude Code plugin packaging** — `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json`, installable via
  `/plugin marketplace add ArulVelusamy/generate-walkthrough` then
  `/plugin install generate-walkthrough@generate-walkthrough-marketplace`.
- **Sample output** — `examples/Flaskr-Walkthrough.html`, verified line-by-line
  against the BSD-3 `flaskr` tutorial, plus light and dark hero screenshots in
  the README.

### Fixed
- The generated HTML now declares `<!doctype html>`, `<meta charset="utf-8">`,
  and a viewport meta in the first 1024 bytes. Without the charset declaration
  the file rendered mojibake (em-dashes, bullets, arrows) when served over HTTP
  rather than opened via `file://`; the spec now requires this head block for
  every walkthrough.

[Unreleased]: https://github.com/ArulVelusamy/generate-walkthrough/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ArulVelusamy/generate-walkthrough/releases/tag/v1.0.0
