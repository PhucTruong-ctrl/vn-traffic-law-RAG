# AGENTS.md — VNLRAG Agent Working Rules

## 1. Non-negotiable rules

- **Always commit after writing any file** (at the end of a coherent unit of work belonging to one task). Never leave the working tree dirty at the end of a task.
- **Always maintain the todo list** (`todowrite`): break each ticket into sub-tasks, keep exactly one `in_progress`, and update statuses in real time (never batch at the end of the session).
- **Always transit the Jira ticket status** through its lifecycle (see §3). Transition immediately when state changes — never defer to end of session.
- **Oracle review BEFORE commit** for every ticket: after all tasks of a ticket are done, an `@oracle` review must pass (or all its findings must be fixed) before the deliverable is committed (see §4 step 7).

## 2. Conventional Commits

The commit message should be structured as follows:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

The commit contains the following structural elements, to communicate intent to the consumers of your library:

- `fix:` a commit of the type fix patches a bug in your codebase (this correlates with PATCH in Semantic Versioning).
- `feat:` a commit of the type feat introduces a new feature to the codebase (this correlates with MINOR in Semantic Versioning).
- `BREAKING CHANGE:` a commit that has a footer `BREAKING CHANGE:`, or appends a `!` after the type/scope, introduces a breaking API change (correlating with MAJOR in Semantic Versioning). A BREAKING CHANGE can be part of commits of any type.
- Types other than `fix:` and `feat:` are allowed, for example `@commitlint/config-conventional` (based on the Angular convention) recommends `build:`, `chore:`, `ci:`, `docs:`, `style:`, `refactor:`, `perf:`, `test:`, and others.
- Footers other than `BREAKING CHANGE: <description>` may be provided and follow a convention similar to git trailer format.

Additional types are not mandated by the Conventional Commits specification, and have no implicit effect in Semantic Versioning (unless they include a BREAKING CHANGE). A scope may be provided to a commit's type, to provide additional contextual information and is contained within parenthesis, e.g., `feat(parser): add ability to parse arrays`.

## 3. Jira ticket lifecycle

| Status | When |
|---|---|
| To Do | Default on ticket creation |
| In Progress | When the first task of the ticket starts (transit immediately at dispatch) |
| In Review | When all tasks are done and the deliverable is awaiting/undergoing oracle review or findings fixes |
| Done | After the deliverable is committed and the oracle review passed |

Transition rules:

- Fetch the actual transition id via `getTransitionsForJiraIssue` before transiting — do not hardcode transition ids.
- The ticket description's **Acceptance Criteria** and **Definition of Done** are the measure of completion.
- Project access: cloudId `da53fe11-6155-438a-9816-e8d94b244341`; `createIssueLink(inwardIssue=A, outwardIssue=B, type="Blocks")` means **A blocks B**.
- Sprint ids (customfield_10020 accepts a plain number): Sprint 5 = 6, Sprint 6 = 7, Sprint 7 = 8. Dates: `customfield_10015` = start, `customfield_10016` = story points, `duedate` = due.

## 4. Standard per-ticket workflow

1. **Update todos**: split the ticket into sub-tasks, mark the first one `in_progress`.
2. **Transit ticket → In Progress**.
3. **Recon**: read the ticket on Jira + survey the relevant repo/docs (delegate fast surveys to `@explorer`).
4. **Plan**: identify independent lanes (runnable in parallel, no file conflicts) vs dependency-ordered lanes.
5. **Dispatch** background specialist lanes, record task ids, wait for completion hooks, reconcile terminal results.
6. **Verify** outputs against the ticket's acceptance criteria (narrowest meaningful check first).
7. **Oracle review BEFORE commit**: dispatch `@oracle` to review all deliverables against the acceptance criteria.
   - Verdict `READY` → proceed to commit.
   - Verdict `READY-WITH-FIXES` → fix every finding, then commit (no re-review needed unless a fix changed substance).
   - Verdict `NOT-READY` → fix findings and re-run the oracle review.
8. **Commit** with Conventional Commits (§2) once the oracle review passes.
9. **Transit ticket → Done** and mark the todo list complete.

## 5. Role routing

- `@explorer` — fast codebase/docs recon; returns a compressed map (paths + line refs), not full contents.
- `@librarian` — external docs/API/library research.
- `@oracle` — architecture decisions, complex debugging, and the mandatory pre-commit review gate (§4 step 7).
- `@fixer` — bounded execution with a complete spec; no research, no architectural decisions.
- `@designer` — UI/UX work only; never simplify/refactor designer output later.

## 6. Project notes

- Documentation-first repo: `docs/00` (scope & decisions) is the highest authority; `docs/03` (system design, incl. ADR §3.32, IR §3.6, Parser Router §3.7), `docs/04` (tech stack), `docs/05` (implementation plan + gates M0-M8), `docs/08` (maintenance/versioning). Code is created per doc 05.
- Deliverables created for VNLRAG-14 (M0 scope freeze, committed): `SCOPE.md`, `ARCHITECTURE.md`, `docs/adr/ADR-001..020.md`, `docs/parser_router.yaml`, `docs/canonical-document-ir-design.md`.
- This project has a **gate path M1→M8** (labels `gate-M1`..`gate-M8`) and `reestimate-w2` labels on 8-SP tickets — respect these when scheduling work.
- Doc 00 forbids cutting scope for schedule or difficulty; non-gate-path work may slip, gate path may not.
