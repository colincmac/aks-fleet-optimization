---
applyTo: "infra/**/*.bicep,.github/workflows/**/*.yml"
---
Use least privilege, managed identity, immutable images/actions, no public data access by default, and no broad Contributor grants. The advisor runtime must remain read-only. Explain any network egress and permissions in documentation.
