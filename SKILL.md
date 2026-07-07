---
name: generate-walkthrough
description: Use when the user wants a forensic, end-to-end technical walkthrough of a codebase as a single self-contained HTML file — tracing the primary user journey screen-by-screen from real source, with a data model, a parameter glossary, and a security/correctness "boundaries" section. Triggers on "walkthrough", "end-to-end doc", "how this codebase works from X to Y", "architecture + journey doc", "onboarding doc for this repo".
---

# Generate Walkthrough

## Overview

Produces ONE self-contained `.html` file that traces what a codebase actually does, from first entry point to terminal outcome, grounded in real `file:line` evidence. The deliverable opens in any browser with zero external assets — no build, no dependencies.

**Core principle:** every factual claim is independently re-derived from source or deleted. Accuracy over coverage; nothing unverified ships.

Run in three phases. Do not write the file until phase 1's inventory is verified; do not report done until phase 3 converges with zero surviving corrections and an empty coverage gap.

## When to use

- User asks for an end-to-end / screen-by-screen / "how it works from tap to done" walkthrough of a repo.
- Onboarding or handover doc that must trace real routes, handlers, keys, and formulas — not a marketing overview.
- Not for: a README, an API reference, or a design doc for code that doesn't exist yet.

## Orchestration model

You are the **lead**. You own the single output file and its design system. Parallelize the parts that parallelize — reading and verifying — but write the file yourself, single-threaded, so tokens/TOC/CSS stay coherent.

- **Investigator subagents (phase 1, parallel, read-only):** each maps one slice and returns structured `file:line`-anchored findings — never prose, never HTML. A finding with no source anchor is invalid.
- **Verifier subagents (phase 3, parallel, read-only):** each independently re-derives assigned claims from source without trusting the doc's wording; returns CONFIRMED / WRONG (+correct value) / UNVERIFIABLE.

If the source is packaged (zip/tarball) or not a git repo, extract only what's needed first (selectively — don't unpack huge vendored trees).

## Phase 1 — Investigate, then verify

1. **Recon (solo):** identify entry points, primary actor(s), the terminal outcome (the thing that means "done" — discover it, don't assume), and the rough list of screens/routes/flows/tables/params. Use it to slice the work.
2. **Fan out (parallel investigators):** one per journey segment, one for the data model/schemas+indexes, one for the parameter glossary, one for the boundaries sweep. Each returns, from real source with `file:line`: what fires on load and on the primary action; every backend/service call (method+route, handler, what it does — auth, DB reads/writes with exact table/key names, external calls, metrics — and what it returns); where state is persisted with exact key names; derived values/formulas reproduced exactly; and boundary issues with a concrete reproduction path + severity.
3. **Merge & verify (lead):** consolidate into a **coverage inventory** — every step, route, key, schema, param, and issue, each with its `file:line`. Resolve conflicts by re-opening source yourself. Discard anything not grounded. Label dead/never-run code as such. Do not proceed with any unverified claim or placeholder.

**Voice:** forensic and concrete, not marketing. Real names, routes, keys, formulas. Flag bugs inline where the reader meets them. Adapt all terminology to THIS system's domain.

## Phase 2 — Write one self-contained HTML file (solo — do not parallelize)

Write the whole file in one pass. **Follow `walkthrough-spec.md` in this skill directory for the exact layout, design tokens, typography, components, and document arc.** While writing, keep a **claim ledger**: every fact tagged with the `file:line` it came from — this feeds phase 3.

## Phase 3 — Review loop (parallel verify; loop to zero)

Run every pass below; fix failures; re-run until a full pass yields **zero WRONG, zero UNVERIFIABLE, an empty coverage gap, and clean whole-file audits.**

- **Forward (parallel verifiers):** split the claim ledger; each verifier re-opens the cited `file:line` and re-derives the claim from scratch. Apply corrections; for UNVERIFIABLE, re-anchor to real code or **delete the claim** — nothing unverifiable ships.
- **Reverse (coverage diff):** enumerate from code the full set of routes/handlers, screens/steps, persisted keys, tables+indexes, and parameters; diff against what the doc covers. Anything in code but absent is a gap — add it, or state it as explicitly out of scope. Never drop silently.
- **Boundaries (adversarial):** re-check each reported issue reproduces given real code paths; delete anything speculative.
- **Cross-consistency:** any value stated in more than one place (key, timeout, formula, status) is identical everywhere.
- **Whole-file audits:** zero external requests (grep: no `http://`, `https://`, `//cdn`, remote `src`/`href`/`@import`/`fetch`/`url(http`); renders in both themes + manual toggle; body never scrolls horizontally); every TOC link resolves to a real section id; colors from token variables (no stray hex), identifiers in mono, components used consistently.

If a coverage gap genuinely can't be closed (generated/vendored code you can't trace), do not hide it — add a short explicit "not covered / could not verify" note naming exactly what and why.

Name the file `<ProjectName>-Walkthrough.html`. Final report: claims confirmed, corrections applied, gaps closed (or explicit exceptions), and that render/nav/design audits pass.
