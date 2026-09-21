# Security hardening notes

This document records the protections that are part of the current deployment
and the boundaries that operators must understand.

## AI provider requests

Configured provider URLs must use HTTP(S), cannot contain credentials or a
fragment, and are resolved before use. Every returned address is rejected when
it is loopback, private, link-local, reserved, or unspecified. HTTP redirects
are disabled and 3xx responses are rejected; a provider cannot redirect a
request to a second host.

## Authentication rate limits

Login, registration-code, and password-reset-code endpoints have process-local
IP and identifier limits. Expired entries are pruned and the in-memory stores
are capped to prevent unbounded growth. These limits are effective per worker.
Deployments with multiple workers must also enforce limits at a reverse proxy,
WAF, or shared Redis/database layer; the local guard is not a distributed
limiter.

## Updater and Docker Socket

The updater intentionally runs with Docker management access so it can replace
the app/updater containers during online updates. Access to
`/var/run/docker.sock` is effectively host-level Docker administration. Do not
expose the socket remotely, run untrusted images, or grant access to untrusted
users. Replacing this with a socket proxy or a host-side restricted updater is
a future architecture change and must preserve the digest checks before it is
enabled.

## Build and release

The compatibility build disables BuildKit provenance and SBOM attestations for
registries that do not accept OCI attachment manifests. This is separate from
security scanning: candidates should be scanned in CI (dependency audit and
container vulnerability scan) before a human approves publication. The local
release process remains the source of truth for production publishing.

The candidate workflow also audits the locked Python dependency graph,
including the OCR and PostgreSQL extras, and runs `npm audit` against the
frontend lock file. The lock file currently retains two moderate Vitest
development-tool advisories that require a breaking Vitest upgrade; they do
not ship in the runtime image. High-severity production dependency findings
fail the workflow.

When the application is served through HTTPS (including a TLS-terminating
reverse proxy), the API adds HSTS. Keep `VX_COOKIE_SECURE=true` in that
deployment and preserve the forwarded-protocol configuration.
