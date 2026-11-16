# Security

Feeltriva is an engineering prototype. It runs in fixture mode with synthetic, nonmedical
content and must not be used with real health information.

## Reporting a vulnerability

Please report privately through GitHub's **Report a vulnerability** button on the repository's
Security tab. Do not open a public issue and do not include real personal or health data in a
report.

## What must never be committed

Raw datasets or archives, `.env` files, credentials, model artifacts, session exports and logs.
`.gitignore` and CI both guard against these.

## Design guarantees worth testing

- Every private request is authenticated and scoped to the token's subject; PostgreSQL
  row-level security enforces the same boundary below the application.
- Mock authentication cannot be enabled outside development or test configuration.
- Clinical mode refuses to start with synthetic or unapproved content.
- Error responses and audit events never contain symptom text.
