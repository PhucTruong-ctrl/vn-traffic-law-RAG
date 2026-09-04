# Project guardrails

- Keep backend Python/uv and frontend workflows on their existing toolchains.
- Keep `backend/src/rule_engine/` domain-agnostic; put domain plugins elsewhere.
- Put declarative business values in `RuleSpec` objects.
- New Pydantic models must use `ConfigDict(extra="forbid")`.
- Add regression tests for bug fixes and update user-facing docs for pipeline changes.
- Never commit secrets, credentials, uploads, caches, or local databases.
- The primary agent controls Git; subagents do not commit or rewrite history.
- Do not weaken assertions, hide failures, hardcode identities, or silently drop unsupported records.
- Verify focused behavior plus the repository-required lint and format checks before completion.
