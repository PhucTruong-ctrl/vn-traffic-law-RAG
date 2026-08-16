# AGENTS.md — VNLRAG Agent Working Rules

Canonical agent instructions for this repository (agents.md spec). Keep `CLAUDE.md` / `.cursorrules` thin and pointing here instead of duplicating rules.

## 1. Non-negotiable rules

Rules use a three-tier boundary model:

**Always**

- Maintain the todo list (`todowrite`): break each ticket into sub-tasks, keep exactly one `in_progress`, update statuses in real time (never batch at the end of the session).
- Transit the Jira ticket status through its lifecycle (§4) immediately when state changes — never defer to end of session.
- Work on a **feature branch inside its own worktree**, never on `main`. Commit at coherent unit boundaries on that branch; never leave the working tree dirty at the end of a task.
- Run local checks before opening a PR (mirrors CI, doc 07 §7.11.1): backend `uv run ruff check .`, `uv run mypy app`, `uv run pytest` (unit + integration, core coverage ≥ 80%); frontend `npm run lint`, `npm run typecheck`, `npm run build`. Full checks run at **phase level** (the merged phase state) before batch oracle review and before the per-phase PR (§6 step 7).
- Follow Conventional Commits (§3); commitlint runs automatically via `.husky/commit-msg`.
- Request oracle review (harness `reviewer` agent) at **batch level**, not per ticket (§5, §6 step 9).
- When a rule conflicts with reality, or you need an exception to a Never rule: stop and ask.

**Ask first** (explicit user permission required)

- Any change touching frozen scope (doc 00), gold set, evaluation baselines, ADRs, or gates M1–M8.
- Deleting or restructuring existing code, or when multiple valid approaches exist.
- Any exception to a Never rule, no matter how small.

**Never**

- Never commit to `main`, never push to `main` directly. `main` is protected and release-only; all changes land via PR.
- Never merge a PR without **oracle verdict `READY` AND CI green** (§2, §6 step 10). Self-approve is allowed only through that gate — nothing else.
- Never force-push (`--force`), never `--amend` pushed commits, never `--no-verify` (or otherwise skip hooks/signing).
- Never consider work complete — and never transit a ticket to Done — until the PR is merged to `main` AND the oracle review passed (§4, §6 step 11). **Unreviewed work is not done.**
- Never commit secrets, `.env` files, API keys, or internal URLs.
- Never run migrations against production manually; schema changes ship via an Alembic migration inside the PR (doc 07 §7.8.1).

## 2. Git workflow: ticket branch → `dev/<sprint>` → batch review → per-phase PR → main

**Every ticket gets its own branch in its own worktree. Unreviewed work accumulates on `dev/<sprint>`. The oracle gates; the agent merges; the human vetoes.**

- **One branch per ticket**, named `{type}/{VNLRAG-XXX}-short-description` (e.g. `feat/VNLRAG-131-parser-router`), branched from `dev/<sprint>` (never from `main`, never from another feature branch).
- Each ticket branch is checked out in its **own git worktree** in a sibling directory outside the repo: `../<repo>-phase<NN>-t<NN>` for implementation, `../<repo>-fix<NN>` for fix rounds (§5). This keeps the orchestrator workspace clean on `main`.
- Commit to the ticket branch at coherent unit boundaries. These commits are the PR content — never commit to `main`.
- After a ticket is implemented and its focused tests pass, merge the ticket branch into **`dev/<sprint>`** (the accumulation branch, branched from `main` at sprint start; the solo-worker `develop` equivalent per doc 05 §5.16.1). Work on `dev/<sprint>` is **unreviewed** until the batch oracle review.
- When a **batch** (~5 tickets, or a natural phase group) has accumulated, dispatch the oracle (`reviewer` agent) over the whole unreviewed diff: `git diff main...dev/<sprint>` (§5).
  - Verdict `READY` → open **exactly one PR per phase** targeting `main` with the ticket key(s) in title/body; wait for CI green; **the agent merges** (§6 step 10).
  - Verdict `READY-WITH-FIXES` → fix every finding (the owning ticket's subagent), commit; no re-review needed unless a fix changed substance.
  - Verdict `NOT-READY` → fix findings and re-run a **focused** oracle review on the fixed areas only.
- **The agent never merges without the gate**: oracle `READY` **and** CI green. If CI is pending or red, wait.
- The human reviews after the merge; requested changes are addressed with follow-up commits and a follow-up PR on the same branch. The human may veto any merged PR at any time.
- At sprint end: delete `dev/<sprint>` and all merged ticket branches.

Hard rules — never without explicit user permission:

- Do NOT `git push` to `main`.
- Do NOT `gh pr merge` without oracle `READY` + CI green; do NOT auto-merge as a routine bypass of review.
- Do NOT force-push, ever. If history needs rewriting, describe it and let the human do it.
- Do NOT `--amend` pushed commits; do NOT bypass hooks.
- Do NOT open a PR unless the phase calls for it.

Quick check before any git/gh action: *push to main / merge without oracle READY / force-push / amend? → STOP, the gate applies.*

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
| In Review | When the ticket's tasks are done, merged into `dev/<sprint>`, and the batch oracle review (or its focused re-review) is pending |
| Done | Only after the phase PR is merged to `main` AND the oracle review passed (agent merge via the §2 gate; no human-merge requirement) |

Transition rules:

- Fetch the actual transition id via `getTransitionsForJiraIssue` before transiting — do not hardcode transition ids.
- The ticket description's **Acceptance Criteria** and **Definition of Done** are the measure of completion.
- Project access: cloudId `da53fe11-6155-438a-9816-e8d94b244341`; `createIssueLink(inwardIssue=A, outwardIssue=B, type="Blocks")` means **A blocks B**.
- Sprint ids (`customfield_10020` accepts a plain number): Sprint 5 = 6, Sprint 6 = 7, Sprint 7 = 8. Dates: `customfield_10015` = start, `customfield_10016` = story points, `duedate` = due.

## 5. Sprint execution model

- **The orchestrator stays on `main`.** It never checks feature branches out in the main workspace; all per-ticket work happens in worktrees (§2). The orchestrator owns: ticket dispatch, todo/Jira tracking, verification runs, batch oracle dispatch, PR opening/merging.
- **1 ticket = 1 subagent.** Each ticket is implemented by exactly one subagent inside its own worktree. Subagents within a phase run in parallel.
- **Parallelism cap: at most 4 subagents concurrently.** Excess batches queue.
- **Agent roles (harness names):** `reviewer` = the oracle (batch reviews + focused re-reviews); `scout` = read-only recon/exploration (the former `@explorer`); `task` = the default worker subagent (1 per ticket). Worker model is the configured `task` role.
- **Fix rounds are owned by the ticket's subagent.** Oracle findings are dispatched back to the owning agent in its fix worktree; it fixes, tests, and commits; the orchestrator re-merges into `dev/<sprint>`.
- **Batch oracle review:** the oracle reviews the accumulated unreviewed diff (`git diff main...dev/<sprint>`) once per ~5 tickets. Verdicts: `READY` → proceed to per-phase PRs; `READY-WITH-FIXES` → fix all findings then commit (no re-review unless substance changed); `NOT-READY` → fix and re-run a focused review of the fixed areas.
- Batch review never waives the Ask-first rules (§1): frozen scope, ADRs, gold set, and gates M1–M8 still require explicit user approval regardless of oracle verdict.

## 6. Standard per-phase workflow

A **phase** is a group of tickets (per the sprint plan, e.g. `VNLRAG-37 + 38`). Work phases sequentially — never all at once.

1. **Todos**: split each ticket in the phase into sub-tasks, mark the first `in_progress`.
2. **Branch + worktree**: for each ticket, create `{type}/{VNLRAG-XXX}-short-description` from `dev/<sprint>` and add a worktree `../<repo>-phase<NN>-t<NN>`.
3. **Transit ticket → In Progress**.
4. **Recon**: read the ticket on Jira + survey the relevant repo/docs (delegate fast surveys to `scout`).
5. **Plan**: identify independent lanes (parallel tickets, no file conflicts) vs dependency-ordered lanes. Dispatch one subagent per ticket; define cross-ticket contracts up front (shared interfaces); cap at 4 concurrent.
6. **Implement**: each subagent works only in its worktree, commits on its ticket branch (Conventional Commits §3), runs its own tests + directly-affected existing tests, and does **not** push or merge.
7. **Verify (orchestrator)**: merge the phase's ticket branches together; run the full local checks (§1 Always) on the merged phase state — `uv run ruff check .`, `uv run mypy app`, `uv run pytest` (with integration `DATABASE_URL`), frontend checks.
8. **Accumulate**: merge each verified ticket branch into `dev/<sprint>`. Unreviewed.
9. **Batch oracle review**: when ~5 tickets (or the phase group) have accumulated, dispatch the oracle over `git diff main...dev/<sprint>` (§5). Apply the verdict semantics.
10. **PR + merge**: on `READY`, open one PR per phase → `main`, wait for CI green, merge (the §2 gate). Transit tickets → Done and mark todos complete.
11. **Human follow-up**: post-merge feedback → follow-up commits on the same branch + follow-up PR; never merge without the gate.

## 7. Project notes

- Documentation-first repo: `docs/00` (scope & decisions) is the highest authority; `docs/03` (system design, incl. ADR §3.32, IR §3.6, Parser Router §3.7), `docs/04` (tech stack), `docs/05` (implementation plan + gates M0–M8, PR gate §5.15.3, branch strategy §5.16), `docs/06` (test/evaluation + regression §6.10), `docs/07` (deployment + CI/CD §7.11), `docs/08` (maintenance/versioning). Code is created per doc 05.
- Deliverables created for VNLRAG-14 (M0 scope freeze, committed): `SCOPE.md`, `ARCHITECTURE.md`, `docs/adr/ADR-001..020.md`, `docs/parser_router.yaml`, `docs/canonical-document-ir-design.md`.
- This project has a **gate path M1→M8** (labels `gate-M1`..`gate-M8`) and `reestimate-w2` labels on 8-SP tickets — respect these when scheduling work.
- Doc 00 forbids cutting scope for schedule or difficulty; non-gate-path work may slip, gate path may not.
