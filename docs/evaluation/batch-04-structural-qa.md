# Batch 04 structural QA — VNLRAG-124

## Scope and evidence

This is targeted structural QA, not an acceptance decision. The four batch-04 manifests point to official `datafiles.chinhphu.vn` PDFs; SHA-256 values were measured from HTTP 200 `application/pdf` downloads. PDFs remain uncommitted under the repository corpus policy. All four manifests remain `PENDING` pending ingestion/reviewer confirmation.

## Key-document observations: Nghị định 168/2024/NĐ-CP

The existing NĐ 168 artifact and OCR regression reference establish the expected hierarchy: `Điều` (article) → `Khoản` (clause) → `Điểm` (point), with Vietnamese labels `a)`, `b)`, `c)`, `d)` and `đ)`. The regression window covers Điều 5, Điều 7, and Điều 9; it expects 8 clauses, 19 points, and distinct `d)`/`đ)` counts (4 each). These observations are structural anchors for batch-04 relation resolution and must not be treated as newly downloaded NĐ 168 content.

## Batch-04 structural/routing notes

- NĐ 119/2024: route as decree; inspect chapter/article headings for electronic road-traffic payment and resolve implementation edges to Luật Đường bộ 35/2024/QH15 and Luật TTATGTĐB 36/2024/QH15.
- NĐ 44/2024: route as decree; inspect articles governing management, use, and exploitation of road-infrastructure assets; candidate implementation edge to Luật Đường bộ 35/2024/QH15.
- TT 16/2024: route as circular; inspect article/chapter headings for investor selection for road rest-stop projects; candidate implementation edge to Luật Đường bộ 35/2024/QH15.
- TT 39/2024: route as circular; inspect provisions for load limits, dimensional limits, oversized/overweight vehicles, and extraordinary cargo; candidate implementation edge to Luật Đường bộ 35/2024/QH15.

The candidate edges are recorded in `relation_notes` for retrieval/routing coverage. Provision-level `Điều/Khoản/Điểm` extraction is intentionally routed to the parser and reviewer; no unavailable OCR text or invented provision counts are claimed here.

## Cumulative evidence

Batch-01 (5) + batch-02 (4) + batch-03 (5) + batch-04 (4) = **18 corpus documents**. Batch-04 alone records four implementation chains, exceeding the target of at least three relation chains.
