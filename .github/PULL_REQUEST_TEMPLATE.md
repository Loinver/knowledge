## Summary

One paragraph: what this PR changes and why. Reference the task ID from
docs/implementation-plan.zh-CN.md (e.g. M0 / H-04) and any linked issue.

## Type of change

- [ ] feat     New feature
- [ ] fix       Bug fix
- [ ] refactor Code restructuring, no behavior change
- [ ] perf     Performance improvement
- [ ] docs     Documentation only
- [ ] ci       CI / tooling
- [ ] test     Test additions or fixes
- [ ] chore    Build / deps / housekeeping

## Checklist

- [ ] `make lint` is green and `make test` passes.
- [ ] Frontend text goes through vue-i18n; new keys exist in **both**
      `web/src/locales/zh-CN.json` and `web/src/locales/en-US.json` with
      identical key sets.
- [ ] Backend returns error codes and enums, not Chinese sentences; any new
      status code has a matching frontend i18n entry.
- [ ] No national-standard text (GB/T 48000.3—2026 verbatim) committed; only
      clause numbers with self-authored descriptions.
- [ ] No `demo/`, `.workbuddy/`, `node_modules/`, `.venv/`, `dist/` files
      staged.
- [ ] Dependencies, if added, are MIT / BSD / Apache-2.0 / ISC / PSF; the
      license is recorded in NOTICE and the PR description.

## Verification

Describe how the change was verified (unit / integration / e2e). For
extraction / graph changes, confirm idempotency and failure-protection
assertions still hold. If a smaller-than-full verification was used (per
AGENTS.md risk tiers), note its coverage.

## DCO

This project uses the Developer Certificate of Origin. Each commit message
ends with:

\`\`\`
Signed-off-by: Your Name <your.email@example.com>
\`\`\`

By signing off, you attest that you have the right to submit the contribution
under the project's MIT license. Commits without `Signed-off-by` cannot be
merged.
