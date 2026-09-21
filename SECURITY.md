# Security Policy

## Supported versions

Security fixes are applied to the `main` branch only. Tagged releases before the
latest minor are not maintained.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report vulnerabilities privately:

- Email: security@linyer.dev
- Subject prefix: \`[SECURITY] Knowledge Platform\`

Include:

1. Affected version / commit SHA.
2. Reproduction steps (minimal, using fictitious data only — never paste real
   customer records or credentials).
3. Impact assessment and suggested fix if any.

We acknowledge within 48 hours and aim to publish an advisory with a fix within
14 days for high-severity issues. Coordinated disclosure timelines can be
negotiated for more complex fixes.

## Scope

In scope:

- The application code under `server/` and `web/`.
- The deployment workflow defined in `.github/workflows/`.
- Credentials, data-source connectors and the metadata database boundary.

Out of scope:

- Vulnerabilities in third-party dependencies that are already disclosed and
  fixed upstream — report to the upstream project and upgrade via a PR.
- Self-XSS or social engineering requiring user action on the attacker's site.
- The local `demo/` archive (never shipped; excluded from the repository).

## Hardened conventions

Per `.agents/conventions/security-and-license.md`:

- Data-source credentials are held by the backend only and are never returned
  in API responses, logs, or export bundles.
- Connectors are read-only; write statements are intercepted.
- The metadata database and the source database are physically separated.
- National-standard text (GB/T 48000.3—2026) is not stored in the repository;
  only clause numbers with self-authored descriptive references are retained.

## DCO

The project uses the Developer Certificate of Origin (DCO). Contributors
`Signed-off-by` their commits, attesting to their right to submit the code under
the project license.
