# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Instead, report privately via [GitHub Security Advisories](https://github.com/epr-ds/nutriplan/security/advisories/new)
or email the maintainers. Please include:

- A description of the vulnerability and its impact
- Steps to reproduce (proof-of-concept if possible)
- Affected component(s) and version/commit

We aim to acknowledge reports within **2 business days** and provide a remediation timeline
after triage.

## Handling sensitive data

- **Never commit secrets** (API keys, tokens, credentials). Use environment variables and a
  secrets manager. `.env` files are git-ignored.
- Payment data is tokenized by the payment provider — the application **never** stores raw
  card numbers (PAN).
- Personally identifiable information (PII) and dietary/health data are treated as sensitive
  and encrypted in transit (TLS) and at rest.

## Supported versions

During pre-release development, only `main` receives security updates.
