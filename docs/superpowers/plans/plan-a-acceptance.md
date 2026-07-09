# Plan A acceptance — narrative-quality regression

Automated tests cover the schema and the Flaskr golden. This manual pass confirms the phase-2 inversion did not degrade prose quality. Run `generate-walkthrough` on a small real repo (e.g. the Flask tutorial) and confirm:

- [ ] `<Project>-walkthrough.model.json` is emitted and validates against `schema/walkthrough-model.schema.json`.
- [ ] The HTML Foundations section still reads as narrative prose (architecture-at-a-glance + a sequence overview), not a bare table dump.
- [ ] "How it works" callouts and positive assertions (e.g. "correct by construction") are still present and specific.
- [ ] Every route in the sidecar appears in the HTML, and every HTML line/method/field matches the sidecar (spot-check 5).
- [ ] Boundaries render grouped by severity with concrete failure scenarios.
- [ ] Both light and dark themes render; body does not scroll horizontally.
