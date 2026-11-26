## Summary

Describe the changed behavior and why. Reference stable feature IDs from
[the feature catalog](../docs/product/feature-catalog.md) and any linked issue.

## Type of change

- [ ] feat New feature
- [ ] fix Bug fix
- [ ] refactor Code restructuring, no behavior change
- [ ] perf Performance improvement
- [ ] docs Documentation only
- [ ] ci CI / tooling
- [ ] test Test additions or fixes
- [ ] chore Build / deps / housekeeping

## Checklist

- [ ] Relevant validation passed; business changes include `make lint` and `make test`. For documentation/tooling-only work, record the scoped checks required by the documentation policy.
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
assertions still hold. If a smaller-than-full verification was used, note its
coverage.

## Documentation impact

Follow the [documentation policy](../.agents/conventions/documentation.md).

- Affected feature IDs and behavior:
- Updated user/product/operations/development documents:
- If no update is needed, concrete reason:
- `pnpm run check:docs` / `pnpm run check:docs:staged` results and any remaining manual review:

## License

By submitting this PR, you agree that your contribution is licensed under the
project's MIT license.
