# Batch 04 structural QA: VNLRAG-124 (historical corpus-review record)

> **Historical record.** This targeted QA was performed against the earlier manifest/PDF/parser-ingestion design. It is not an active release gate and does not imply external retrieval, agents, LangGraph, Redis, MinIO, PostgreSQL app-owned runtime, or a seven-service topology. The current MVP uses FastAPI/Python 3.11, Supabase REST/Auth for app persistence, local Qdrant 1.19 hybrid retrieval (OpenRouter dense + FastEmbed BM25), one OpenRouter generator, deterministic evidence/citation/temporal checks, and Markdown/PDF legal exploration. Frozen manifest hashes and observations below are preserved.

## Historical scope and evidence

This targeted structural QA was not an acceptance decision. The four batch-04 manifests pointed to official `datafiles.chinhphu.vn` PDFs, and SHA-256 values were measured from HTTP 200 `application/pdf` downloads. The PDFs remained uncommitted under the historical corpus policy, and all four manifests were `PENDING` pending ingestion and reviewer confirmation.

## Key-document observations: Nghị định 168/2024/NĐ-CP

The existing NĐ 168 artifact and OCR regression reference established the expected hierarchy: `Điều` (article) → `Khoản` (clause) → `Điểm` (point), with Vietnamese labels `a)`, `b)`, `c)`, `d)`, and `đ)`. The regression window covered Điều 5, Điều 7, and Điều 9; it expected 8 clauses, 19 points, and distinct `d)`/`đ)` counts (4 each). These observations are historical structural anchors and must not be treated as newly downloaded or currently indexed NĐ 168 content.

## Historical batch-04 routing notes

- NĐ 119/2024: route as decree; inspect chapter/article headings for electronic road-traffic payment and resolve implementation edges to Luật Đường bộ 35/2024/QH15 and Luật TTATGTĐB 36/2024/QH15.
- NĐ 44/2024: route as decree; inspect articles governing management, use, and exploitation of road-infrastructure assets; candidate implementation edge to Luật Đường bộ 35/2024/QH15.
- TT 16/2024: route as circular; inspect article/chapter headings for investor selection for road rest-stop projects; candidate implementation edge to Luật Đường bộ 35/2024/QH15.
- TT 39/2024: route as circular; inspect provisions for load limits, dimensional limits, oversized/overweight vehicles, and extraordinary cargo; candidate implementation edge to Luật Đường bộ 35/2024/QH15.

The candidate edges were recorded in historical `relation_notes` for retrieval and routing coverage. Provision-level `Điều/Khoản/Điểm` extraction was intentionally deferred to the historical parser/reviewer; no unavailable OCR text or invented provision counts were claimed.

## Historical cumulative evidence

Batch-01 (5) + batch-02 (4) + batch-03 (5) + batch-04 (4) = **18 corpus documents** in that historical planning and evidence record. Batch-04 alone recorded four candidate implementation chains, above the historical target of at least three relation chains.

## Current interpretation

These notes do not show that the active Markdown/PDF corpus contains all 18 documents or that the relations are available to Qdrant. Current evaluation must inspect the checked-in source/chunk manifests and local Qdrant collection, then report absent or unsupported material as `CORPUS_NOT_COVERED`/unavailable. Do not mutate frozen gold-set or historical manifest data to satisfy this QA record.
