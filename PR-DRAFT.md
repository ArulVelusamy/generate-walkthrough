# PR draft — for obra/superpowers-skills (or obra/superpowers)

> **Read first.** The upstream `obra/superpowers` README states: *"we don't generally
> accept contributions of new skills, and any updates to skills must work across all of
> the coding agents we support."* This skill currently targets Claude Code's subagent
> model, so expect one of: (a) declined by policy, (b) a request to make it cross-agent
> portable first. `obra/superpowers-skills` is the more appropriate target than the core
> repo. Treat this as *propose and hope*, not a merge. Fill in their actual PR template
> fields if they differ from the headings below.

---

**Title:** Add `generate-walkthrough` skill — forensic, source-verified codebase walkthroughs

## What this adds

A skill that produces a single self-contained HTML **walkthrough** of any codebase:
a screen-by-screen trace from first entry point to terminal outcome, a data model,
a parameter glossary, and a security/correctness boundaries section — every claim
anchored to `file:line`.

Core principle: **every factual claim is independently re-derived from source or
deleted.** Three phases — parallel read-only investigators → single-threaded write →
parallel verifiers looped until zero unverified claims and an empty coverage diff.

## Why it might fit Superpowers

- It *is* a Superpowers-style discipline skill: it encodes a verify-don't-trust loop
  and adversarial re-derivation, the same spirit as `requesting-code-review` and
  `verification-before-completion`.
- Read-only investigation + a written HTML artifact; no destructive operations.

## Honest caveats (please weigh these)

- **Not yet cross-agent.** It uses Claude Code's `Agent`/subagent orchestration for the
  parallel investigate/verify phases. It would need a portability pass to run on the
  other agents you support. Happy to do that work if you'd consider it.
- **New skill.** I'm aware new-skill contributions are generally not accepted; opening
  this in case a source-verified documentation skill is of interest, and to get a
  steer on whether a portable version would be welcome.

## Validation

Run end-to-end and output verified against source on two stacks:

1. **Python/Flask/SQLite/Jinja2** — the public `pallets/flask` tutorial (`flaskr`).
   Every route/SQL/schema/ownership claim confirmed line-by-line; boundaries section
   flagged real issues (weak default `SECRET_KEY`, missing CSRF, username enumeration,
   FK/pragma orphan risk) with no false positives (SQL injection explicitly cleared,
   no invented debug-mode issue). Sample output included in the skill's `examples/`.
2. **A private Vue/Express app** — on the auth slice it reproduced 100% of a
   hand-written reference doc from source alone and additionally surfaced a critical
   auth bug the reference had missed.

## Files

- `skills/generate-walkthrough/SKILL.md` — workflow + orchestration + verify loop
- `skills/generate-walkthrough/walkthrough-spec.md` — HTML output spec (loaded in the write phase)

## Checklist

- [ ] Skill follows the `writing-skills` structure (frontmatter: `name`, `description`; description = triggering conditions only)
- [ ] Read-only investigation; no destructive actions
- [ ] Example output included and attributed (BSD-3 flaskr)
- [ ] Cross-agent portability — **not done**, seeking guidance before investing
- [ ] Code of Conduct acknowledged
