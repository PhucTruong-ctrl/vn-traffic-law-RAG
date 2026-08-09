# VNLRAG-21 Spike Findings — Docling→Canonical-IR Provenance Mapping Contract

Spike findings report (no implementation). Analysis of how the VNLRAG-20
Docling→IR adapter (`backend/app/evaluation/suites/suite_a.py`) maps Docling
provenance (page, bbox, source_parser, parser_version, raw_reference) onto the
frozen canonical Document IR, observed on real P1 run artifacts. Feeds the
production adapter tickets VNLRAG-129/130.

## 1. Context & method

- **Spike, not implementation**: the goal is to validate the
  `DocumentElement` provenance mapping (page, bbox, source_parser,
  parser_version, raw_reference) on a real legal document and record what the
  production adapter (VNLRAG-129/130) must handle. **No IR schema change and no
  adapter implementation are made in this spike.**
- **Method**: read-only analysis of the real P1 Docling run artifacts
  `data/evaluation/suite-a-first-pass/run-20260809-113849-137550/p1-docling/ir/*.ir.json`
  (documents `luat-36-2024-qh15`, `nd-168-2024`, `tt-24-2024-tt-bgtvt`; 48
  elements total), produced by the VNLRAG-20 `suite_a.py` Docling→IR adapter,
  cross-checked against the frozen contract
  `docs/canonical-document-ir-design.md` and
  `backend/app/ingestion/document_ir.py`, and Docling 2.118.1 internals.

## 2. Provenance mapping validation (observed on real artifacts)

| field | observed | notes |
|---|---|---|
| `element_type` | `text` (16) + `list_item` (32) only | fixtures contain no tables/headings/pictures/header-footer; real headings classified as `text` (see §4 gap 2) |
| `page_number` | 48/48 present, 1-based | multi-page `nd-168-2024` spans pages 1–2 correctly |
| `bbox` | 48/48 present, all with `page_height`/`page_width` matching page-level dims (595.28×841.89, A4) | — |
| bbox orientation | **CRITICAL: 48/48 bboxes have `top > bottom`** | PDF-native **BOTTOMLEFT** origin passed through raw — e.g. title block `top=792.79, bottom=714.99` on an 841.89-high page (§4 gap 1) |
| `source_parser` | `"DOCLING"` 48/48 | — |
| `parser_version` | `"docling-2.118.1"` 48/48 | — |
| `parser_confidence` | `null` 48/48 | Docling text/list items expose no per-item confidence |
| `raw_reference` | 5-key dict on 48/48 | `{docling_item_index` (global `enumerate` index), `docling_item_type` (Python class name, e.g. `TextItem`/`ListItem`), `docling_label` (`item.label.value`), `prov_page_no`, `charspan` (0-indexed char span tuple)` |
| `element_id` | `p{page}-e{global-index}` | matches the §7 illustrative `p12-e3` scheme |
| `reading_order` | 0-based contiguous `0..N-1` | adapter's own index, not a Docling-computed reading order |
| `parent_element_id` | `null` 48/48 | adapter never populates; Docling exposes parent/children (§4 gap 4) |
| `table_html` | `null` 48/48 | no tables in fixtures — **table path UNTESTED** (§4 gap 5) |

## 3. Adapter contract assumptions vs reality (`suite_a.py`)

| # | assumption | ref | held? | reality / note |
|---|---|---|---|---|
| 1 | `item.label.value` → `element_type` | :652 | held | label is verbatim (see §4 gap 2) |
| 2 | `prov[0]` page + bbox | :587-602 | held | `prov` is a **list** — multi-prov items drop all but the first (§4 gap 6) |
| 3 | bbox `l/t/r/b` 1:1 | :587-602 | syntactically held | **WRONG origin semantics** — Docling `BoundingBox` has a `coord_origin` field the adapter drops (§4 gap 1) |
| 4 | page size via `doc.pages[page_no].size` | :592-594 | held | — |
| 5 | page_no from `prov[0].page_no` | :651 | held | — |
| 6 | raw_reference identity = `enumerate` index | :615-623 | works | not stable across versions — `NodeItem.self_ref` JSON pointer is the stable id (§4 gap 3) |
| 7 | `reading_order` = adapter index | :659 | held | 0-based contiguous |
| 8 | `parent_element_id = None` always | :660 | held | hierarchy is available but discarded (§4 gap 4) |
| 9 | `table_html` via `export_to_markdown` | :605-612 | NOT exercised | field named `table_html` but code writes **markdown**; `TableItem.export_to_html` exists but unused (§4 gap 5) |
| 10 | `parser_confidence = None` | :664 | held | Docling exposes no per-item confidence |
| 11 | `source_object_key = str(pdf_path)` | :689 | works for bench | not a MinIO object key per contract (§4 gap 8) |
| 12 | `quality_report = {}` | :693 | held | gates computed separately in `routing-and-gates.json` — consistent with doc 03 |
| 13 | text = sanitized `item.text` | :582-584 | held | note `TextItem.orig` vs `text` |

**§7 example divergence**: the frozen contract's §7 example shows
`raw_reference {"item_id", "docling_type"}` and `element_type heading/paragraph`;
the adapter emits a richer 5-key dict and Docling-native `text`/`list_item`
labels. §7 is explicitly illustrative and `raw_reference` is a free dict — this
is **NOT a contract violation**. The adapter's actual shape is the de-facto
baseline for VNLRAG-129/130 consumers.

## 4. Gaps/risks for VNLRAG-129 (production Docling adapter)

Severity-ranked; numbered.

1. **Coordinate-origin ambiguity (HIGHEST)**: the IR `BoundingBox` has no origin
   field; the spike forwards BOTTOMLEFT (`top > bottom` on 48/48 elements).
   Origin is route-dependent in Docling: the pypdfium text-layer backend emits
   BOTTOMLEFT, while OCR boxes (tesseract CLI model, layout model) emit TOPLEFT.
   The production adapter must normalize (or record) to one convention.
2. **`element_type` = Docling label verbatim**: the contract advertises
   `title/heading/paragraph/...`, but the Docling PDF route emits
   `text/list_item/title/section_header/table/picture/caption/footnote/page_header/page_footer/document_index`.
   Real headings ("Điều 3. Giải thích từ ngữ") were classified as `text`, not
   `section_header`. The adapter should define an explicit label→IR mapping; the
   extractor must not rely on `element_type == "heading"`.
3. **`raw_reference` lacks a stable Docling id**: `docling_item_index` is
   unstable across Docling versions; add `docling_self_ref` (JSON pointer) — no
   schema change (free dict).
4. **`parent_element_id` never populated; hierarchy discarded**:
   `iterate_items()` yields `(item, level)`; Docling exposes `parent`/`children`;
   `SectionHeaderItem` carries a `level` field. This loses structure the
   extractor needs.
5. **`table_html` name/format mismatch + untested**: the contract promises HTML;
   the code writes markdown (`export_to_markdown`); the label gate `!= "table"`
   also rejects `DOCUMENT_INDEX`-labeled tables; no table fixtures exercised the
   path. Decide HTML-vs-markdown in VNLRAG-129 with a real table fixture.
6. **`prov[0]` only**: multi-prov items (cross-page blocks/tables) are silently
   truncated — record `prov_count`/page span in `raw_reference`.
7. **OCR vs text-layer**: the spike hardcodes `do_ocr=False`; the production
   route must support the scan route (tesseract vie, psm 3, dpi 300) and handle
   the bbox origin divergence (gap 1).
8. **`source_object_key` = local path in the spike**; production must use the
   real MinIO object key.
9. **Header/footer filtering not performed**: Docling can emit
   `page_header`/`page_footer`; a policy is needed (the `header_footer_leakage`
   metric anticipates it).

**W2-boundary coverage gaps (not defects)**: scans/OCR, complex/multi-page
tables, headers/footers, multi-prov items, `title`/`section_header`/`picture`/
`caption` types, parent/child hierarchy. `nd-168-2024` is the only multi-page
fixture (2 pages).

## 5. Recommended adapter guidance for VNLRAG-129/130 (frozen contract unchanged)

1. Normalize bbox to one documented origin at the adapter layer (recommend
   TOPLEFT via Docling `BoundingBox.to_top_left_origin(page_height)`) for BOTH
   routes, or record the origin per element.
2. Emit `docling_self_ref` (+ parent/cell refs) in `raw_reference` alongside
   `docling_item_index`.
3. Define an explicit label→`element_type` mapping table
   (`section_header→heading`, `picture→figure`, ...) and document that
   `heading`/`paragraph` are never emitted verbatim by the PDF route.
4. Populate `parent_element_id` from `NodeItem.parent` cref → IR `element_id`
   where hierarchy exists.
5. Resolve table export: use `export_to_html(doc)` to match the contract name,
   or document a markdown-in-v1 decision — with a real table fixture before
   relying on it.
6. Handle multi-prov: record `prov_count`/page span in `raw_reference` (or merge
   bboxes).
7. `source_object_key` injected at parse time from the pipeline, not derived
   from a filesystem path.
 8. Keep `element_id` `p{page}-e{global-index}` for v1 (satisfies §9
    stability-within-parse) and add a stability regression check (same Docling
    version + same PDF → identical `element_id`s).

### 5.1 Ticket applicability matrix

How the risks/gaps in §4 map to the three IR-related tickets. **VNLRAG-128 (IR
schema, already implemented)**: the spike validated the schema as-is on the
48-element sample and **NO schema change is required** — the frozen contract
stands. The coordinate-origin ambiguity is a schema-level observation
(`BoundingBox` has no origin field) that is recorded here for the record but
resolved at the ADAPTER layer per §5 recommendation 1 — do NOT propose a schema
change. **VNLRAG-129 (Docling adapter)**: all 9 gaps and all 8 recommendations
apply. **VNLRAG-130 (MinerU adapter)**: gaps #1, #2, #3, #4, #6, #7, #8 apply —
MinerU's JSON/Markdown output must be mapped with the same conventions; the
MinerU adapter must also record its parser version and normalize bbox origin
consistently with the Docling adapter.

| Risk/gap (§4) | VNLRAG-128 (schema — no change) | VNLRAG-129 (Docling adapter) | VNLRAG-130 (MinerU adapter) |
|---|---|---|---|
| 1. Coordinate-origin ambiguity | schema observation, recorded; resolved at adapter layer (no schema change) | Yes — normalize to one documented origin (rec #1) | Yes — normalize bbox origin consistently with Docling adapter |
| 2. `element_type` = label verbatim | — | Yes — explicit label→`element_type` mapping (rec #3) | Yes — same conventions on MinerU output |
| 3. `raw_reference` stable id | — | Yes — `docling_self_ref` (rec #2) | Yes — record a stable id per MinerU output |
| 4. `parent_element_id` population | — | Yes (rec #4) | Yes |
| 5. `table_html` name/format + untested | — | Yes (rec #5, with real table fixture) | — |
| 6. Multi-prov handling | — | Yes (rec #6) | Yes |
| 7. OCR vs text-layer + origin divergence | — | Yes — scan route (tesseract vie, psm 3, dpi 300) | Yes — OCR-origin divergence (#1/#7) |
| 8. `source_object_key` injection | — | Yes (rec #7) | Yes |
| 9. Header/footer filtering | — | Yes | — |

## 6. File:line references

- `backend/app/evaluation/suites/suite_a.py`: `_make_docling_converter` :570-579,
  `_item_text` :582-584, `_item_bbox` :587-602, `_item_table_html` :605-612,
  `_item_raw_reference` :615-623, `parse_with_docling` :626-694,
  `_make_docling_parse` :1085-1098, `_execute_docling` :1101-1159,
  `provenance_coverage` metric :309-334, `layout_coherence` :434-466.
- `backend/app/ingestion/document_ir.py`: `BoundingBox` :23-37,
  `DocumentElement` :40-62, `ParsedPage` :65-78, `ParsedDocument` :81-95.
- `docs/canonical-document-ir-design.md`: §3 :27-62, §4 :64-85, §5 :87-110,
  §6 :112-147, §7 :153-200, §8 :204-220, §9 :224-228.
- P1 artifacts `run-20260809-113849-137550`: run.json :6-19 (OCR config),
  :45-48 (parser_versions); `ir/luat-36-2024-qh15.ir.json` (bbox :8-15,
  raw_reference :22-31, source_object_key :800).
- Docling 2.118.1 internals: `ProvenanceItem` `reference.py:182-192`;
  `CharSpan` `scalars.py:10`; `CoordOrigin`/`BoundingBox` `base.py:17-62` +
  `to_top_left_origin` :245-260; `NodeItem.self_ref` `items/node.py:22-37`;
  `TextItem` `items/text.py:19-43`; `TableItem` `table.py:36-43` +
  `export_to_markdown` :138-184 + `export_to_html` :186-202;
  `iterate_items` `document.py:3305-3322`; `pypdfium2_backend.py:168-176`
  (BOTTOMLEFT); `tesseract_ocr_cli_model.py:372` and
  `layout_object_detection_model.py:178` (TOPLEFT); `heading_hierarchy_model.py:213`
  (`to_top_left_origin`).
- Committed report: `docs/evaluation/suite-a-first-pass-report.md`.

---

**Spike complete — provenance mapping validated on 3 born-digital fixtures (48
elements); 9 production gaps recorded; adapter guidance provided for
VNLRAG-129/130; frozen IR contract unchanged. No IR/adapter implementation in
this spike.**

Date: 2026-08-09 · Ticket: VNLRAG-21
