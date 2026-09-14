# VNLRAG

A structure-aware, temporal RAG system for Vietnamese traffic-law question answering with verifiable citations. Legal documents are ingested into a canonical representation, resolved into version-bound provisions with effective intervals, indexed, retrieved, and answered with citation verification.

## Language

**Legal Reference Resolver**:
The MVP is single-user on localhost/private network. It has no authentication, admin/reviewer role, approval UI/API, or human approval. Manual CLI ingestion is the sole ingestion trigger; automatic quality, provenance and temporal gates classify records as `ACCEPTED` or `REJECTED`. Only `ACCEPTED` records may be indexed or served, and a failed rebuild leaves the prior alias active.

The serving corpus is exactly 14 deduplicated local PDFs from `datafiles.chinhphu.vn`, identified by immutable snapshot/file hashes. Release evaluation is a fixed 200-question gold set across 17 categories, split 40 development / 40 validation / 120 final test. Feedback is anonymous `LIKE`/`DISLIKE` telemetry only and is explicitly non-gating. Local embedding candidates are benchmarked before selecting and recording one model/version manifest; no unmeasured model or threshold is an active claim.

**Historical terminology**:
References to reviewer decisions, review routing, upload ingestion, background ingestion, or a 5–10-document / 30–50-question scope in older material are superseded. They may remain only when explicitly labeled historical; they are not runtime requirements.

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
