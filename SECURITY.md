# Security Policy

## Supported Versions

OpenAgent is in early development. Security fixes are applied to the **current minor release line** only. Older tags or forks are not guaranteed to receive patches.

| Version   | Supported |
| --------- | --------- |
| 0.1.x     | Yes       |
| &lt; 0.1  | No        |

When we publish **0.2.x** or later, this table will be updated to state which lines still receive security updates.

## Reporting a Vulnerability

**Please do not open a public GitHub issue** for undisclosed security problems.

1. **Preferred:** If the repository has [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) enabled, submit the report there.
2. **Otherwise:** Email the maintainers at **REPLACE_WITH_SECURITY_EMAIL** (replace this placeholder in your fork with a working address).

Include:

- A short description of the issue and its impact
- Steps to reproduce (or a proof-of-concept), if possible
- Affected component (backend, frontend, config, dependencies), if known

### What to expect

- We aim to acknowledge receipt within **7 days**. For small or volunteer-run teams, delays may happen; a short follow-up ping is welcome.
- We will work on a fix for **accepted** issues in supported versions and coordinate disclosure when a release is ready.
- If a report is **declined** (e.g. out of scope, not reproducible, or by design), we will explain briefly.

## Scope (high level)

In scope for security reports:

- OpenAgent backend (`backend/`), API/WebSocket surface, default configuration handling
- Frontend (`frontend/`) when it leads to concrete risk (e.g. XSS, unsafe handling of secrets in the browser)
- Documented deployment paths (e.g. default bind addresses, CORS)

Generally out of scope:

- Issues that require the attacker to already control the machine or `openagent.yaml`
- Third-party model providers (Ollama, OpenAI, etc.) — report those to the respective vendor
- Dependency advisories: we track upgrades in normal development; critical chains may still be worth reporting if exploitation goes through OpenAgent-specific usage

## Secure configuration reminders

- Do not commit API keys or `openagent.yaml` with secrets; use environment variables (e.g. `OPENAI_API_KEY`, keys referenced via `api_key_env` in config).
- The API defaults to a local bind; exposing it on the public internet requires TLS, authentication, and network controls appropriate to your threat model.

---

Maintainers: replace **REPLACE_WITH_SECURITY_EMAIL** with your contact, or remove the email bullet if you rely only on GitHub private reporting.
