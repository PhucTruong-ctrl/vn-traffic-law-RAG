# VNLRAG

A structure-aware, temporal RAG system for Vietnamese traffic-law question answering with verifiable citations. Legal documents are ingested into a canonical representation, resolved into version-bound provisions with effective intervals, indexed, retrieved, and answered with citation verification.

## Language

**Legal Reference Resolver**:
Extracts version-bound relations between legal entities — `ProvisionReference` (PARENT_OF, REFERS_TO, SIBLING_OF, PENALTY_COMPANION) and `DocumentRelation` (AMENDS, REPEALS, SUPERSEDES, CORRECTS, GUIDES, RELATED_TO) — from extracted text and manifest relation notes, persisting them in PostgreSQL. Never guesses: unresolved references route to review.
_Avoid_: reference extraction, relation parser

**Temporal & Amendment Resolver**:
Computes the half-open effective interval `[effective_from, effective_to)` per provision version from manifests, `LegalEffectEvent`s, document relations, and reviewer decisions. A provision is valid at date `d` iff `effective_from <= d` AND (`effective_to IS NULL` OR `d < effective_to`) AND `review_status = ACCEPTED`. Partial amendments produce new versions of the same stable `provision_id`.
_Avoid_: effective-date calculator, time resolver

**LegalEffectEvent**:
A dated record of a change to a provision: EFFECTIVE, AMENDED, PARTIAL_AMENDED, SUPERSEDED, REPEALED, CORRECTED, EXPIRED. Carries structured `affected_provision_versions`. The input to interval computation, never the output.

**Provision version**:
A concrete revision of a provision. `provision_id` stays stable across amendments; the version increments and the lineage registry records `superseded_by_version`. Intervals belong to versions, not provisions.
_Avoid_: provision row, provision edit

**Canonical date policy**:
The query-side rule deciding which date a question is answered at (doc 03 §3.16.4): request date, explicit query date, or a canonical date for year-only references — with the applied date always shown to the user. Distinct from ingestion-side interval computation; year-only references with an in-year effect change yield `MISSING_QUERY_DATE` and abstention.
_Avoid_: date normalization, effective-date policy

**Gold set record**:
A reviewed evaluation item: id, question, category (17 categories), query_date, expected/acceptable provision IDs, required evidence, must/must-not facts, temporal metadata, review status, gold version, and hash. Split into development (40), validation (40), and final test (120).

**Gate M2**:
The accept+index gate: one ACCEPTED provision runs end-to-end through the real resolvers (never placeholders) into PostgreSQL with a resolver-derived effective interval, is embedded and indexed in Qdrant, and is returned by search. No provision is indexed without a resolver-derived interval.
