# VNLRAG-22 Spike Findings — Structure Extraction Evidence (patterns, d/đ, short points)

## 1. Context & method

- Spike (not implementation): fixture-driven evidence for the Legal Structure Extractor (VNLRAG-26/28, W3) and parsing rules (VNLRAG-23). No production extractor code.
- Method: read-only analysis of real P1 Docling IR artifacts (`data/evaluation/suite-a-first-pass/run-20260809-113849-137550/p1-docling/ir/*.ir.json` — luat-36-2024-qh15 26 el/1pg, nd-168-2024 5 el/2pg, tt-24-2024-tt-bgtvt 17 el/1pg), gold annotations (`backend/tests/fixtures/parser_benchmark/gold/` — nd/luat/tt-gold.json, point_label_d_dd.json, short_point_annotation.json, parent_context_annotation.json; stable-ID fixture at sibling `backend/tests/fixtures/parser_benchmark/golden-stable-id/stable_id_diem_d_dd.json`), raw fixture text (`.pdf.txt` files), spec (docs/03 §3.8, §3.7.3, §3.14, §3.15; docs/06 structure metrics; templates/legal-provision.schema.json), plus VNLRAG-20/21 artifacts (OCR report, IR-provenance spike).

## 2. Hierarchy recognition patterns

### 2.1 CRITICAL: IR strips point/clause labels from list_item elements

The Docling→IR adapter classifies point/clause lines as `element_type: "list_item"` and drops the label prefix from element text. Verified: luat p1-e2/e3/e4/e5/e7 list_items lost a)/b)/c)/d)/e) (raw fixture lines 9-14 have them); luat p1-e1 (ro=1) lost "1." clause number (raw line 8 "1. Trong Luật này..."); tt p1-e14/e15 lost a)/b). But marker retention is INCONSISTENT even among list_items: some list_items strip markers (luat p1-e2..e5/e7, tt p1-e14/e15), while others keep them — tt p1-e10 IS a `list_item` (tt-24-2024-tt-bgtvt.ir.json) that retains "đ) Ảnh chân dung theo quy định." `text`-classified elements also retain labels (luat p1-e6 "đ) Người đi bộ...", p1-e16 "b) Đường quốc lộ;", p1-e19 "đ) Đường xã;" — all three are `text` in the IR; tt p1-e9 inline a)–d)). Label survival is inconsistent (luat kept đ) lost a/c/d/e/g; tt kept đ) lost a/b) and does NOT correlate with element_type.

- **Consequence**: extractor cannot rely on element.text containing the label for list_items, and must NOT use element_type as a marker-presence predictor (retention is inconsistent even among list_items). Strategy: PARSE an existing marker from element text first, and reconstruct (from raw text/page text OR reading_order+position) only when absent; alternatively ask VNLRAG-129 adapter to preserve markers.

### 2.2 Pattern candidates (with matched examples)

| Level | Regex candidate | Matched example | IR evidence |
| Chương | `^Chương\s+([IVXLCDM]+)\.\s*(.*)$` | luat raw L4 "Chương I. NHỮNG QUY ĐỊNH CHUNG", L24 Chương II | luat p1-e12 (text, ro=12); Chương I merged into p1-e0 title (ro=0) |
| Điều | `^Điều\s+(\d+)\.\s*(.*)$` | nd L4/28/56; luat L6/18/26/39; tt L4/13/24 | ALWAYS `text` (luat p1-e9/e13/e23; tt p1-e1/e7/e12) — NOT `heading` (confirmed gap, spike-vnlrag-21:75-80) |
| Khoản | `^\d+\.\s` (raw) | nd L6/14/19/24; luat L8/16/20/22 | `list_item`, number stripped (luat p1-e1 = Khoản 1 of Điều 3; p1-e8 Khoản 2; p1-e10/11 of Điều 5; p1-e22 of Điều 8; p1-e24/25 of Điều 9) |
| Điểm | `^([a-zđ])\)\s` (raw) | nd L7-12 a–e; luat L9-14, L29-35 a–g; tt L7-9, L16-20 | Mixed, NOT correlated with element_type: label kept in some list_items (tt p1-e10 "đ) Ảnh chân dung…") and in `text` elements (luat p1-e6/e16/e19; tt p1-e9 inline); stripped in other list_items (luat p1-e2..e5,e7,e15,e17,e18,e20,e21) |

### 2.3 Concrete article→clause→point examples (with IR element_ids)

Example 1 — luat Điều 3 → Khoản 1 → Điểm a–đ–e: p1-e0 (text ro=0, chapter+article head merged "…Chương I…Điều 3. Giải thích từ ngữ"); p1-e1 (list_item ro=1, Khoản 1 intro, number stripped → gold luat-36-2024__dieu-3__khoan-1); p1-e2..p1-e7 (ro=2-7; p1-e6 text keeps đ)) = points a,b,c,d,đ,e → gold …__diem-a..__diem-đ..; p1-e8 (list_item ro=8) Khoản 2. Reading order ro1→ro7 contiguous; labels must be reconstructed.

Example 2 — luat Điều 8 → Khoản 1 → Điểm a–g: p1-e13 (text ro=13 "Điều 8. Phân loại đường bộ" after p1-e12 Chương II); p1-e14 (list_item ro=14, clause intro "Đường bộ được phân loại theo cấp kỹ thuật gồm:"); p1-e15..e21 (ro=15-21, points a..g; only e16 b) and e19 đ) kept); p1-e22 (ro=22) Khoản 2. Gold confirms __dieu-8__khoan-1__diem-a/d/đ.

Example 3 — nd Điều 5 → Khoản 1 → Điểm a–e (DEGENERATE): p1-e0 (text ro=0) is a single 3049-char merged element with the whole body inline ("NGHỊ ĐỊNH… Điều 5… 1. Phạt tiền… a) … e)… Điều 7…") — labels survive inline; p1-e1 (text) ends mid-sentence "…vượt quá mức quy", which p2-e2 (text) continues as "định; c) Điều khiển xe…" (page-boundary-corrupted fragment); p2-e3 (text) is another merged/boundary-corrupted element — 1,371 chars spanning clauses, points and Điều 9 (charspan 0-1371); p2-e4 (list_item) has its marker stripped ("Điều khiển xe gây tai nạn giao thông rồi bỏ trốn."). Implication: extractor must regex-parse merged inline text (page.text/charspan), cannot assume one element = one provision.

### 2.4 Parent-child implications

- parent_element_id null 48/48 (spike-vnlrag-21:38); hierarchy must derive from reading_order contiguity + label patterns (a Điều text head owns subsequent list_items until next Điều/Chương head; a clause intro owns its point-run until next clause/Điều head).
- element_type histogram {"list_item": 32, "text": 16} — extractor must NOT key on element_type=="heading".

## 3. d)/đ) distinction evidence

### 3.1 Co-occurrence (exact quotes): 8 adjacent d)–đ) pairs (a,b,c,d,đ,e sequence; đ = 7th of 29 VN letters, docs/03:1041)

- nd raw L10-12 "d) Không giữ khoảng cách… / đ) Lùi xe… / e) Vượt xe…" (followed by e)); L34-36 and L42-44 same shape (followed by e)); L50-51 and L62-63 have the d)–đ) pair but NO following e)
- luat raw L12-13 "d) Người sử dụng… / đ) Người đi bộ…" followed by e) at L14; L32-33 "d) Đường huyện; / đ) Đường xã;" followed by e) at L34
- tt raw L19-20 "d) Bản sao giấy xác nhận… / đ) Ảnh chân dung…" — NO following e)
- Of the 8 pairs, only FIVE are followed by e): nd L10-12/L34-36/L42-44 and luat L12-14/L32-34. nd L50-51, nd L62-63 and tt L19-20 are NOT. đ) often — but not always — precedes e) in these fixtures; not a hard rule.

### 3.2 Gold evidence

point_label_d_dd.json (d)→diem-d "KHÔNG va chạm với đ)", đ)→diem-đ "giữ nguyên ký tự đ trong ID, distinct khỏi diem-d"; assertions both_labels_distinct:true, diem_da_keeps_đ:true. stable_id_diem_d_dd.json: diem_d="nd-168-2024__dieu-7__khoan-4__diem-d", diem_d_da="…__diem-đ", distinct:true. Gold trees: __diem-đ under nd dieu-5-k1 (L66), dieu-7-k1 (L174), dieu-7-k2 (L198), dieu-9-k1 (L234); luat dieu-3-k1 (L78), dieu-8-k1 (L174); tt dieu-5-k1 (L126) — all separate from __diem-d siblings.

### 3.3 OCR risk (scans)

tesseract vie 300 DPI benchmark hit 0.5834; diacritics fragile (d vs đ differ by stroke); scan-derived docs with d/đ ambiguity → review (VNLRAG-155), never auto-index (suite-a-first-pass-report.md:93-105, 142-144). docs/03:1056-1064 OCR variants → needs_review when uncertain; docs/06:216-219 decide via alphabet order + context, else flag.

### 3.4 Disambiguation candidates

1. Sequence position a→b→c→d→đ→e (4th letter=d, 5th=đ) — works for all 8 pairs
2. Content context (docs/06:218)
3. VN alphabet order (d 6th, đ 7th, docs/03:1041)
4. Fallback needs_review (docs/03:1064, docs/06:219)

Note: the "đ) immediately before e)" pattern is NOT a disambiguation rule — it holds for only 5 of 8 pairs in these fixtures (see §3.1); usable at most as a soft sanity check.

## 4. Short-point cases

### 4.1 Annotation policy

short_point_annotation.json L4-7: NO token-length threshold; short valid points retained (retained=true). 7 annotated cases: luat dieu-8-k1 diem-a "a) Đường cao tốc" (3 words), diem-d "d) Đường huyện" (2), diem-đ "đ) Đường xã" (2); nd dieu-7-k4 diem-a "a) Điều khiển xe lạng lách, đánh võng…", dieu-9-k2 diem-d, dieu-9-k3 diem-c; tt dieu-7-k1 diem-a clause-intro-with-2-points. All expected_retained:true.

### 4.2 Gold short_point flags

nd-gold dieu-7-k4-a (L210-220), dieu-9-k2-d (L246-256), dieu-9-k3-c (L258-268) → short_point:true, retained:true; luat-gold dieu-8-k1 a/d/đ (L150-184); tt-gold dieu-7-k1-a (L150-160). Parent-context fixture confirms single-point nd dieu-7-k4-diem-a.

### 4.3 Retention rule

docs/03 §3.8.3 (L1052-1054) short-but-valid point is still valid provision, never removed for token count; docs/06:197 case 12 + L1087 (no length threshold). Retention = don't filter by token count; validity = recognizable point label / point-position in clause run.

## 5. Cross-reference + temporal (for VNLRAG-23)

### 5.1 Cross-references ABSENT in fixtures

grep for `khoản\s*\d|điểm\s*[a-zđ]|quy định tại` → zero in all 3 fixtures (only false positives like "khoảng cách"). Patterns are SPEC-DRIVEN: docs/03 §3.14.1 (L2874-2887) REFERS_TO examples "quy định tại Điều 7 Nghị định 168/2024/NĐ-CP", "theo quy định tại Khoản 4 Điều 6", "hành vi quy định tại Điểm a Khoản 4 Điều 7" → regex candidates:

- `quy định tại (Điều|Khoản|Điểm)\s*(\d+|[a-zđ])`
- `theo quy định tại (Khoản|Điều)\s*\d+`
- chained `(Khoản|Điểm)\s*(\d+|[a-zđ])\s*(Khoản\s*\d+\s*)?Điều\s*\d+`

PENALTY_COMPANION "Khoản 13"-style citation (L2879, L2891). docs/06:1003 unresolved-ref count metric; L1264 Cross-reference Resolution Recall. Relations/ fixtures don't exist yet (W4 resolvers).

### 5.2 Temporal manifest-driven

no date refs in fixture bodies. docs/03 §3.15.1 (L2929-2934) effective interval source priority = manifest, then LegalEffectEvent/DocumentRelation/review; §3.15.6 (L2985) do NOT guess effective dates from PDF content → UNKNOWN/PENDING_REVIEW. Schema effective_from/effective_to nullable; ACCEPTED rows require effective_from (legal-provision.schema.json L57-69, L100-105).

## 6. Structural gate inputs (Group B)

- Gates (docs/03 §3.7.3 L961-968 + parser_router.yaml L55-62): point label detection ≥0.9, hierarchy completeness ≥0.9, short-point retention (no threshold), Article/Clause/Point P/R/F1 (thresholds post-Suite-A). Fallback (L970-974): Group B fail → discard structural, full rerun alternate parser, never index partial.
- Evidence in gold: point_label_d_dd.json + gold point_label fields; gold chapter/section/article/clause/point fields for hierarchy tree; short_point_annotation.json (7) + short_point/retained flags; gold __diem-đ ids (8) for đ) Recall; tuple (document_id, article, clause, point) vs gold for P/R/F1 (docs/06:1086-1088).
- Extractor must produce LegalProvision[] with provision_id per §3.8.5 (docs/03:1066-1106): `{loai}-{so}-{nam}__dieu-{n}__khoan-{n}__diem-{chu-cai}`; normalize lowercase, strip diacritics EXCEPT đ kept (L1080-1088); non-tree forms `__phu-luc/__bang/__khoan-chuyen-tiep/__chuyen-tiep/__tieu-de` (L1090-1098); schema regex legal-provision.schema.json:39 has [a-zđ]. Output with state parser current_chapter/section/article/clause/point + source_element_ids + page_number + bbox (docs/03 §3.8.6 L1108-1124).
- ⚠️ Slug vs document_id: gold slugs are luat-36-2024 / tt-24-2024 while IR document_id are luat-36-2024-qh15 / tt-24-2024-tt-bgtvt (only nd matches). Extractor must derive slug from MANIFEST, not document_id.

## 7. Recommendations for VNLRAG-23 (rules) + VNLRAG-26/28 (extractor)

1. **Pattern table** (exact regexes above, fixture-validated). For Điểm/Khoản, element_type is NOT a marker-presence predictor (see §2.1): parse an existing marker from element text first, reconstruct only when absent.
2. **d/đ rule**: primary = VN alphabet sequence a,b,c,d,đ,e,g (d=4th, đ=5th in point runs; validated on all 8 pairs); KEEP đ in provision_id (diem-đ vs diem-d, never strip); OCR ambiguity on scans → needs_review, never guess.
3. **Short-point rule**: keep any label-valid point regardless of token length (0 threshold); retained:true.
4. **provision_id**: `{slug}__dieu-{n}(__khoan-{n})?(__diem-{letter})?` with đ kept; slug from manifest; validate against schema regex; unique key (provision_id, version).
5. **Hierarchy fallback** (reading_order-based when labels absent): text element matching `^Điều\s+\d+\.` starts an article; following list_item run (until next Điều/Chương head) belongs to it; clause intros (lines ending ": gồm:/như sau:/sau đây:") open a clause whose point-run is subsequent list_items; assign clause numbers by count, point letters by position a→b→c→d→đ→e. For merged-text IRs (nd p1-e0 3049 chars, tt p1-e9 inline a-d): run regexes on full page/element text; merge page-boundary sentence fragments until a new label/Điều/`\d+.` appears. Do NOT rely on element_type=="heading" (never emitted).
6. **Group B gates** then verify reconstruction (point label detection ≥0.9, hierarchy completeness ≥0.9, short-point retention, P/R/F1 vs gold).
7. **Highest-leverage adapter note for VNLRAG-129/130**: point/clause labels stripped from list_item text in the current adapter — production adapter should preserve the list marker (raw_reference or element text) so the extractor doesn't have to reconstruct letters by position.

## 8. File:line references

- IR artifacts: nd-168-2024.ir.json (p1-e0 L16-35 merged body, p1-e1 L46-65, p2-e2 L84-103, p2-e3 L114-133, p2-e4 L144-163); luat-36-2024-qh15.ir.json (p1-e0 L16-35, p1-e1 L46-65, p1-e2 L76-95, p1-e6 L196-215, p1-e9 L286-305, p1-e12 L376-395, p1-e13 L406-425, p1-e14 L436-455, p1-e16 L496-515, p1-e19 L586-605, p1-e23 L706-725); tt-24-2024-tt-bgtvt.ir.json (p1-e1 L46-65, p1-e9 L286-305, p1-e10 L316-335, p1-e14 L436-455)
- Gold: nd-gold.json L6-16/65-76/210-220/246-268; luat-gold.json L7-15/77-88/150-184; tt-gold.json L126-136/150-160; point_label_d_dd.json L4/20-31/38-42; short_point_annotation.json L4-7/8-47; parent_context_annotation.json L6-11/13-18; golden-stable-id/stable_id_diem_d_dd.json (in backend/tests/fixtures/parser_benchmark/golden-stable-id/, sibling of gold/) L6-16
- Raw: nd-168-2024-fixture.pdf.txt L4/6-12/28/53-54/56/69/74; luat-traffic-2024-fixture.pdf.txt L4/24/6/8-14/26/29-35/12-13/32-33; tt-traffic-2024-fixture.pdf.txt L4/13/24/15-20/19-20
- Spec: docs/03 §3.8 L1023-1139 (L1041 alphabet, L1046-1048 d/đ, L1052-1054 short-point, L1056-1064 OCR, L1066-1106 provision_id, L1108-1124 output); §3.7.3 L948-999 (L961-968 B gates, L989-990 config); §3.14 L2868-2921 (L2874-2887 REFERS_TO); §3.15 L2925-2987 (L2929-2934 manifest priority, L2985 no-guessing); docs/06 L196-202/204-219/260-274/1070-1092/2266-2271; legal-provision.schema.json L33/39/57-69/100-105; parser_router.yaml L39-48/55-62; suite-a-first-pass-report.md L34/67-71/93-105/136-144; spike-vnlrag-21 L28/35/37/38/75-80

## Footer

- **Verdict**: "Spike complete — hierarchy patterns validated on 3 born-digital fixtures (48 IR elements, 7 short-point cases, 8 d/đ co-occurrence pairs); critical finding: IR strips point/clause labels from list_item elements; extractor guidance + rules input provided for VNLRAG-23/26/28; no production extractor code in this spike."
- Date 2026-08-09, ticket VNLRAG-22.
