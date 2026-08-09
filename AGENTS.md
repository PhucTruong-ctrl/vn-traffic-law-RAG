# AGENTS.md — VNLRAG Agent Working Rules

Canonical agent instructions for this repository (agents.md spec). Keep `CLAUDE.md` / `.cursorrules` thin and pointing here instead of duplicating rules.

## 1. Non-negotiable rules

Rules use a three-tier boundary model:

**Always**

- Maintain the todo list (`todowrite`): break each ticket into sub-tasks, keep exactly one `in_progress`, update statuses in real time (never batch at the end of the session).
- Transit the Jira ticket status through its lifecycle (§4) immediately when state changes — never defer to end of session.
- Work on a **feature branch**, never on `main`. Commit at coherent unit boundaries on that branch; never leave the working tree dirty at the end of a task.
- Run local checks before opening a PR (mirrors CI, doc 07 §7.11.1): backend `uv run ruff check .`, `uv run mypy app`, `uv run pytest` (unit + integration, core coverage ≥ 80%); frontend `npm run lint`, `npm run typecheck`, `npm run build`.
- Follow Conventional Commits (§3); commitlint runs automatically via `.husky/commit-msg`.
- Request `@oracle` review BEFORE commit (workflow §5 step 7).
- When a rule conflicts with reality, or you need an exception to a Never rule: stop and ask.

**Ask first** (explicit user permission required)

- Any change touching frozen scope (doc 00), gold set, evaluation baselines, ADRs, or gates M1–M8.
- Deleting or restructuring existing code, or when multiple valid approaches exist.
- Any exception to a Never rule, no matter how small.

**Never**

- Never push to `main`/`master`. `main` is protected and release-only; all changes land via PR.
- Never commit to `main`, never merge a PR yourself, never self-approve, never auto-merge.
- Never force-push (`--force`), never `--amend` pushed commits, never `--no-verify` (or otherwise skip hooks/signing).
- Never consider work complete — and never transit a ticket to Done — until a **human** has reviewed and merged the PR (§2, §5 step 11). **Unreviewed work is not done.**
- Never commit secrets, `.env` files, API keys, or internal URLs.
- Never run migrations against production manually; schema changes ship via an Alembic migration inside the PR (doc 07 §7.8.1).

## 2. Git workflow: branch → PR → main (human merges)

**Every ticket produces exactly one PR to `main`. The agent proposes; a human disposes.**

- **One branch per ticket**, named `{type}/{VNLRAG-XXX}-short-description` (e.g. `feat/VNLRAG-131-parser-router`), branched from `main` (or the current integration branch per doc 05 §5.16.1). Never branch from another feature branch.
- Commit to the feature branch at coherent unit boundaries. These commits are the PR content — never commit to `main`.
- Push the branch and open **exactly one PR per ticket** targeting `main`, with the ticket key in the title/body and CI passing.
- **The agent never merges.** After the PR is created: report, then STOP.
- The human reviews; the agent answers feedback with follow-up commits on the same branch; the human merges to `main`. The agent never merges and never approves its own PR.

Hard rules — never without explicit user permission:

- Do NOT `git push` to `main`.
- Do NOT `gh pr merge`, do NOT auto-merge.
- Do NOT force-push, ever. If history needs rewriting, describe it and let the human do it.
- Do NOT `--amend` pushed commits; do NOT bypass hooks.
- Do NOT commit to the default branch; do NOT open a PR unless the ticket calls for it.

Quick check before any git/gh action: *push / merge / force-push / amend? → STOP, the human does this.*

PR requirements (doc 05 §5.15.3, doc 07 §7.11): clear objective, no scope creep, unit/integration tests, Alembic migration if the schema changes, config docs if a new env var is added, ADR if the architecture changes. Retrieval-affected PRs must additionally run the retrieval regression subset, temporal regression, citation invariant (Returned Invalid Citation Rate = 0) and gold-set integrity (doc 07 §7.11.2). Full LLM evaluation never runs per-PR (doc 07 §7.11).

## 3. Conventional Commits

Enforced by commitlint (`.husky/commit-msg` → `commitlint.config.mjs`): lowercase type, subject ≤ 100 chars, no trailing period, imperative mood, body/footer ≤ 100 chars per line.

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

- `feat:` new feature (MINOR) · `fix:` bug fix (PATCH) · `BREAKING CHANGE:` footer or `!` after type/scope (MAJOR).
- Allowed types: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`.
- Append the ticket key: `feat(ingestion): add parser router (VNLRAG-131)`.

## 4. Jira ticket lifecycle

| Status | When |
|---|---|
| To Do | Default on ticket creation |
| In Progress | When the first task of the ticket starts (transit immediately at dispatch) |
| In Review | When all tasks are done, oracle review passed, and the PR is awaiting human review |
| Done | Only after the PR is merged to `main` by a human AND the oracle review passed |

Transition rules:

- Fetch the actual transition id via `getTransitionsForJiraIssue` before transiting — do not hardcode transition ids.
- The ticket description's **Acceptance Criteria** and **Definition of Done** are the measure of completion.
- Project access: cloudId `da53fe11-6155-438a-9816-e8d94b244341`; `createIssueLink(inwardIssue=A, outwardIssue=B, type="Blocks")` means **A blocks B**.
- Sprint ids (`customfield_10020` accepts a plain number): Sprint 5 = 6, Sprint 6 = 7, Sprint 7 = 8. Dates: `customfield_10015` = start, `customfield_10016` = story points, `duedate` = due.

## 5. Standard per-ticket workflow

1. **Todos**: split the ticket into sub-tasks, mark the first one `in_progress`.
2. **Branch**: create `{type}/{VNLRAG-XXX}-short-description` from `main` (never work on `main`).
3. **Transit ticket → In Progress**.
4. **Recon**: read the ticket on Jira + survey the relevant repo/docs (delegate fast surveys to `@explorer`).
5. **Plan**: identify independent lanes (runnable in parallel, no file conflicts) vs dependency-ordered lanes. Dispatch background specialist lanes, record task ids, reconcile terminal results.
6. **Verify** outputs against the ticket's acceptance criteria (narrowest meaningful check first); run the local checks (§1 Always).
7. **Oracle review BEFORE commit**: dispatch `@oracle` to review all deliverables against the acceptance criteria.
   - Verdict `READY` → proceed to commit.
   - Verdict `READY-WITH-FIXES` → fix every finding, then commit (no re-review needed unless a fix changed substance).
   - Verdict `NOT-READY` → fix findings and re-run the oracle review.
8. **Commit** to the feature branch with Conventional Commits (§3). Never commit to `main`.
9. **Push branch + open exactly one PR → `main`**, with title/body referencing the ticket and CI passing. Report the PR, then STOP — do not merge, do not self-approve.
10. **Human review (mandatory HITL)**: the human reviews the PR; address feedback with follow-up commits on the same branch; never merge your own PR.
11. **Human merges the PR to `main`.** Only then: transit ticket → Done and mark the todo list complete.

## 6. Project notes

- Documentation-first repo: `docs/00` (scope & decisions) is the highest authority; `docs/03` (system design, incl. ADR §3.32, IR §3.6, Parser Router §3.7), `docs/04` (tech stack), `docs/05` (implementation plan + gates M0–M8, PR gate §5.15.3, branch strategy §5.16), `docs/06` (test/evaluation + regression §6.10), `docs/07` (deployment + CI/CD §7.11), `docs/08` (maintenance/versioning). Code is created per doc 05.
- Deliverables created for VNLRAG-14 (M0 scope freeze, committed): `SCOPE.md`, `ARCHITECTURE.md`, `docs/adr/ADR-001..020.md`, `docs/parser_router.yaml`, `docs/canonical-document-ir-design.md`.
- This project has a **gate path M1→M8** (labels `gate-M1`..`gate-M8`) and `reestimate-w2` labels on 8-SP tickets — respect these when scheduling work.
- Doc 00 forbids cutting scope for schedule or difficulty; non-gate-path work may slip, gate path may not.
