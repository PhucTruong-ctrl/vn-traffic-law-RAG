# VNLRAG MVP execution map

**Master plan:** `EXECUTION-PLAN.md`
**Spec:** `spec.md`
**All tickets:** feature-slug folders below; numeric dependencies refer to paths shown here.

## Feature folders

1. `01-query-status/` — status taxonomy, greeting, out-of-scope, corpus coverage.
2. `02-serving-state/` — automatic ACCEPTED/REJECTED migration.
3. `03-corpus-snapshot/` — exact 14-PDF snapshot and reconciliation.
4. `04-full-ingestion/` — parser/IR/structure/relation/temporal ingestion.
5. `05-local-embedding/` — bounded local embedding benchmark.
6. `06-qdrant-promotion/` — versioned rebuild, reconciliation and alias rollback.
7. `07-legal-evidence/` — canonical concepts and evidence completeness.
8. `08-citation-passage/` — citation metadata and passage viewer contract.
9. `09-serving-search/` — sparse-vocabulary-correct serving search.
10. `10-feedback/` — anonymous LIKE/DISLIKE telemetry.
11. `11-gold-freeze/` — frozen 200-question gold set.
12. `12-release-evaluation/` — full evaluation and hard gates.
13. `13-defense-docs/` — README/docs/tracker/release manifest/runbook.

## Dependency graph

```text
01 ──→ 02 ──→ 04 ──→ 06 ──→ 08 ──→ 09 ──→ 12 ──→ 13
│       │       │       │       │       │       ↑
│       └───────┘       └───────┘       │       │
├────→ 07 ─────────────────────────────┘       │
└────→ 10                                      │
03 ──→ 04                                      │
03 ──→ 05 ──→ 06                              │
03 ──→ 11 ─────────────────────────────────────┘
```

Cross-folder dependency references use folder name plus ticket title; never bare numbers.
