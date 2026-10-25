# Security policy

## Supported versions

Only the latest release receives security fixes while the project is pre-1.0.

| Version | Supported |
|---|---|
| 0.1.x | yes |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

1. Preferred: use GitHub's private vulnerability reporting ("Security" tab, "Report a
   vulnerability") on the repository.
2. If that is unavailable, open a public issue that says only "security contact requested"
   (no details) and a maintainer will arrange a private channel.

Include what you found, how to reproduce it, and the affected version or commit. You should get
an acknowledgement within a few days; this is a volunteer-run project, so there is no formal SLA.
Please allow time for a fix before disclosing publicly.

## Scope notes

This is a starter template. Security of your deployment (secrets, TLS, database access, rate
limits at the edge, dependency updates) is your responsibility; see docs/deployment.md for the
defaults the template ships with and the exceptions it makes on purpose.
