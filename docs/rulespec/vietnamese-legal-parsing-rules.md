# Quy tắc Parsing và Chuẩn hóa Văn bản Pháp luật Việt Nam (VNLRAG-23)

> Tài liệu này là **v2 rules spec** thay thế toàn bộ nội dung `docs/rulespec/` v1 (kỷ nguyên UDEF, đã gỡ theo ADR-001). Đây là tài liệu quy tắc (rules) — **không implement code**; Legal Structure Extractor (VNLRAG-26/28) và normalization metadata pháp lý (Sprint 2) triển khai theo đúng các quy tắc dưới đây.

## 1. Phạm vi & mục đích

- Drives **Legal Structure Extractor** (VNLRAG-26/28, W3) và normalization pháp lý trong Sprint 2.
- Nguồn chính thức của tài liệu này:
  - doc 00 mục 4.2 (scope & decisions);
  - doc 03 §3.8 (Legal Structure Extractor, L1023-1139), §3.7.3 (gates, L948-999), §3.14.1 (REFERS_TO, L2874-2887), §3.15 (Temporal, L2925-2987);
  - spike VNLRAG-22 evidence: `docs/spike-vnlrag-22-structure-extraction-evidence.md` (phân tích IR thực + gold + fixtures);
  - spike VNLRAG-21: `docs/spike-vnlrag-21-ir-provenance-contract.md` (provenance adapter, 48 elements);
  - gold fixtures: `backend/tests/fixtures/parser_benchmark/gold/` (+ `golden-stable-id/`);
  - schema: `templates/legal-provision.schema.json`, `templates/corpus-manifest.schema.json`, `docs/parser_router.yaml`.
- Tài liệu này chỉ định nghĩa **quy tắc**; extractor là nơi triển khai theo doc này. Không có code extractor trong phạm vi VNLRAG-23.

## 2. Phân loại loại văn bản

- Các loại văn bản được hỗ trợ: **Luật / Nghị định / Thông tư** và các loại khác theo enum `DocumentType` của corpus manifest — `LAW` / `DECREE` / `CIRCULAR` / `RESOLUTION` / `DECISION` / `OTHER` (`templates/corpus-manifest.schema.json`, dòng 54).
- Cách xác định loại văn bản: đọc từ **manifest** — field `document_type` kết hợp `document_title` — **KHÔNG suy luận từ text IR** (IR text không phải nguồn tin cậy cho metadata văn bản; xem spike VNLRAG-21 về provenance).

## 3. Pattern nhận diện cấu trúc (fixture-validated, từ spike VNLRAG-22)

Bảng regex đã được validate trên 3 fixtures born-digital (luat-36-2024-qh15 26 el/1pg, nd-168-2024 5 el/2pg, tt-24-2024-tt-bgtvt 17 el/1pg — 48 elements tổng):

| Cấp | Regex | Bằng chứng |
|---|---|---|
| Chương | `^Chương\s+([IVXLCDM]+)\.\s*(.*)$` | luat raw L4 "Chương I. NHỮNG QUY ĐỊNH CHUNG", L24 Chương II (IR: luat p1-e12, text ro=12) |
| Điều | `^Điều\s+(\d+)\.\s*(.*)$` | nd L4/28/56; luat L6/18/26/39; tt L4/13/24 — luôn là `text` (luat p1-e9/e13/e23; tt p1-e1/e7/e12), KHÔNG phải `heading` |
| Khoản | `^(\d+)\.\s` | nd L6/14/19/24; luat L8/16/20/22 — `list_item`, số bị strip (luat p1-e1 = Khoản 1 Điều 3; p1-e8 Khoản 2; p1-e10/11 Điều 5; p1-e22 Điều 8; p1-e24/25 Điều 9) |
| Điểm (born-digital / strict) | `^([a-zđ])\)\s` | nd L7-12 a–e; luat L9-14, L29-35 a–g; tt L7-9, L16-20 — giữ/strip không đồng nhất (xem lưu ý dưới) |
| Điểm (scan/OCR-tolerant) | `^([a-zđ])\)\s*` | OCR variant: nhãn dính không khoảng trắng `a)Điều` vẫn là điểm bắt đầu hợp lệ (doc 03:1059). Chỉ dùng cho scan/OCR route, xem §9. |

### 3.1. LƯU Ý QUAN TRỌNG (spike 22 finding)

- **Adapter hiện tại STRIP label khỏi text của `list_item`** — luat p1-e2..e5/e7 mất a)–e); tt p1-e14/e15 mất a)/b). Nhưng **KHÔNG phải luôn luôn**: tt p1-e10 là `list_item` **giữ** "đ) Ảnh chân dung theo quy định."; element loại `text` cũng giữ label (luat p1-e6 "đ) Người đi bộ...", p1-e16 "b) Đường quốc lộ;", p1-e19 "đ) Đường xã;"). Label survival không tương quan với `element_type`.
- **Hệ quả cho extractor**:
  1. Parse label từ element text **TRƯỚC** (dùng marker còn sót nếu có);
  2. Chỉ tái dựng label khi thiếu (từ raw text/page text hoặc reading_order + vị trí);
  3. **KHÔNG dùng `element_type` làm predictor của marker-presence**.
- **IR degenerate** (nd):
  - nd p1-e0 là merged text 3049 ký tự chứa toàn bộ body inline (NGHỊ ĐỊNH… Điều 5… 1. Phạt tiền… a) … e)… Điều 7…) — label sống inline;
  - p2-e2/p2-e3 là boundary-corrupted: p1-e1 kết thúc giữa câu "…vượt quá mức quy", p2-e2 tiếp tục "định; c) Điều khiển xe…"; p2-e3 là merged/boundary-corrupted 1.371 ký tự trải qua khoản, điểm và Điều 9 (charspan 0-1371).
  - **Hệ quả**: khi element là merged text — regex-parse toàn bộ text; merge các page-boundary fragment cho tới khi gặp label mới / `Điều` / `\d+.` mới. **Không giả định 1 element = 1 provision.**
- **`element_type == "heading"` KHÔNG BAO GIỜ được emit bởi docling PDF route** — heading thực tế được phân loại là `text` (spike VNLRAG-21 §4 gap 2; histogram `{"list_item": 32, "text": 16}`). Extractor **không được phụ thuộc** `element_type == "heading"`.
- Hierarchy: `parent_element_id` null 48/48 (spike VNLRAG-21:38) → cây phải dựng từ reading_order contiguity + pattern label (xem §10).

## 4. Quy tắc d)/đ) (điểm trọng tâm)

- **Bảng chữ cái tiếng Việt**: `a b c d đ e ...` — `đ` là ký tự thứ 7/29, `d` thứ 6/29 (doc 03:1041; không dùng giả định `[a-z]` đơn giản, doc 03 §3.8.2).
- **Phân biệt bắt buộc**:
  - `d)` → `diem-d`;
  - `đ)` → `diem-đ`;
  - **GIỮ NGUYÊN ký tự `đ` trong provision_id**, KHÔNG strip diacritics cho `đ` (chỉ strip các dấu khác; doc 03 §3.8.5 L1080-1088).
- **Gold**: `point_label_d_dd.json` (diem-d "KHÔNG va chạm với đ)", diem-đ "giữ nguyên ký tự đ trong ID, distinct khỏi diem-d"; assertions `both_labels_distinct: true`, `diem_da_keeps_đ: true`); `golden-stable-id/stable_id_diem_d_dd.json`: `diem_d = nd-168-2024__dieu-7__khoan-4__diem-d`, `diem_d_da = nd-168-2024__dieu-7__khoan-4__diem-đ`, `distinct: true`.
- **8 cặp d)/đ) đồng hiện trong fixtures**: nd 5 (raw L10-12, L34-36, L42-44, L50-51, L62-63), luat 2 (L12-13/L32-33), tt 1 (L19-20).
- **Quy tắc phân biệt**:
  1. **PRIMARY — thứ tự bảng chữ cái** `a→b→c→d→đ→e` (d = thứ 4, đ = thứ 5 trong point run). Nếu label thiếu (list_item bị stripped) hoặc mờ (OCR): gán theo vị trí ordinal trong run. Validate được trên cả 8 cặp.
  2. **CONTEXT**: `đ)` thường — nhưng **KHÔNG luôn** — đứng trước `e)`. Chỉ 5/8 cặp có `e)` theo sau (nd L10-12/L34-36/L42-44, luat L12-14/L32-34); nd L50-51, nd L62-63, tt L19-20 thì KHÔNG. **Đây KHÔNG phải hard rule** (spike 22 đã sửa quan điểm này) — chỉ dùng như soft sanity check.
  3. **OCR** (tesseract vie trên scan): d↔đ nhạy cảm diacritic → nếu pattern/context không đủ → gắn cờ `needs_review`, **KHÔNG đoán** (doc 03:1056-1064; doc 06:216-219; scan routing VNLRAG-155).
- `provision_id` **không được collision** giữa `diem-d` và `diem-đ` — schema regex cho phép ký tự `đ` (`legal-provision.schema.json:39` pattern `[a-zđ]`).

## 5. Quy tắc Short-Point retention

- **KHÔNG có ngưỡng token length**: một Điểm ngắn nhưng hợp lệ (có label nhận diện được / vị trí point trong clause run) vẫn là provision hợp lệ, `retained: true`.
- Bằng chứng: `short_point_annotation.json` — `token_length_threshold: null`, 7 cases đều `expected_retained: true` (luat dieu-8-k1 diem-a "a) Đường cao tốc" 3 từ; diem-d "d) Đường huyện" 2 từ; diem-đ "đ) Đường xã" 2 từ; nd dieu-7-k4-a, dieu-9-k2-d, dieu-9-k3-c; tt dieu-7-k1-a). Gold cũng gắn `short_point: true, retained: true` (nd-gold L210-220/246-268, luat-gold L150-184, tt-gold L150-160).
- **Phân biệt**: `validity` = label hợp lệ; `retention` ≠ lọc theo độ dài. Retention nghĩa là **không loại bỏ theo số token** (doc 03 §3.8.3 L1052-1054; doc 06:197 case 12 + L1087).

## 6. Quy tắc provision_id

- **Format** (doc 03 §3.8.5, L1066-1106):

  ```text
  {slug}__dieu-{n}(__khoan-{n})?(__diem-{chu-cai})?
  ```

  Ví dụ: `nd-168-2024__dieu-7`, `nd-168-2024__dieu-7__khoan-4`, `nd-168-2024__dieu-7__khoan-4__diem-b`.

- **Slug lấy từ MANIFEST** (`document_id` "luat-36-2024-qh15" → slug "luat-36-2024") — **KHÔNG dùng `document_id` trực tiếp** (spike 22 warning: gold slugs `luat-36-2024` / `tt-24-2024` khác IR `document_id` `luat-36-2024-qh15` / `tt-24-2024-tt-bgtvt`; chỉ `nd` khớp).
- **Chuẩn hóa**: lowercase; strip diacritics **NGOẠI TRỪ `đ`** (giữ đ); thay khoảng trắng bằng `-`; không dùng title text trong ID; version không nằm trong ID logic.
- **Non-tree forms** (node_kind khác ARTICLE/CLAUSE/POINT):

  ```text
  {slug}__phu-luc-{n}                    # APPENDIX
  {slug}__phu-luc-{n}__bang-{m}          # TABLE trong Phụ lục
  {slug}__dieu-{n}__bang-{m}             # TABLE trong Điều
  {slug}__dieu-{n}__khoan-chuyen-tiep     # TRANSITIONAL gắn Điều
  {slug}__chuyen-tiep-{k}                 # TRANSITIONAL độc lập
  {slug}__tieu-de-{n}                     # HEADING
  ```

- **Validate** chống lại regex `legal-provision.schema.json:39` (`^[a-zđ]+-[0-9]+-[0-9]{4}(?:__dieu-[0-9]+(...)?)?$`); unique key vật lý `(provision_id, version)` (doc 03:1087; khi provision bị sửa đổi, `provision_id` giữ nguyên, nội dung mới lưu dưới version mới).

## 7. Quy tắc cross-reference (REFERS_TO) — spec-driven

- **Fixtures hiện tại KHÔNG chứa cross-refs**: grep `khoản\s*\d|điểm\s*[a-zđ]|quy định tại` → 0 kết quả trong cả 3 fixtures (chỉ false positive như "khoảng cách"). Vì vậy các pattern dưới đây **spec-driven**, lấy từ doc 03 §3.14.1 (L2874-2887):
  - `quy định tại (Điều|Khoản|Điểm)\s*(\d+|[a-zđ])`
  - `theo quy định tại (Khoản|Điều)\s*\d+`
  - chained: `(Khoản|Điểm)\s*(\d+|[a-zđ])\s*(Khoản\s*\d+\s*)?Điều\s*\d+`
  - PENALTY_COMPANION: citation kiểu "Khoản 13" (L2879, L2891) — Điều xử phạt liệt kê hành vi "quy định tại Khoản 13" → Khoản chứa định nghĩa hành vi là `PENALTY_COMPANION` của Điều xử phạt.
- **Relation types**: `PARENT_OF` (từ cây extractor), `REFERS_TO` (pattern tường minh), `SIBLING_OF` (cùng Khoản cha/Điều cha), `PENALTY_COMPANION` (suy luận).
- **Resolution trong W4** (resolvers); fixtures `relations/` chưa tồn tại — cần tạo (W4). Metric liên quan: `Cross-reference Resolution Recall` (doc 06:1264), `unresolved-ref count` (doc 06:1003).

## 8. Quy tắc temporal metadata

- **NGUỒN ưu tiên** (doc 03 §3.15.1, L2929-2934):
  1. **Manifest**: `effective_from`, `effective_to`, `status`, `relation_notes` (ưu tiên);
  2. `LegalEffectEvent` (EFFECTIVE/AMENDED/SUPERSEDED/REPEALED/CORRECTED/PARTIAL_AMENDED);
  3. `DocumentRelation` (AMENDS/REPEALS/SUPERSEDES/CORRECTS/GUIDES);
  4. Review (quyết định reviewer cho trường hợp không chắc chắn).
- **KHÔNG đoán effective dates từ nội dung PDF** khi manifest không cung cấp → ghi `UNKNOWN` / `PENDING_REVIEW`, tạo ReviewItem, không index vào Qdrant, không phục vụ temporal query tới khi reviewer quyết định (doc 03 §3.15.6 L2985).
- **Schema**: `effective_from`/`effective_to` nullable (`legal-provision.schema.json` L57-69, L100-105); **ACCEPTED rows require `effective_from`** (CHECK constraint DB: `review_status = 'ACCEPTED'` → `effective_from` bắt buộc khác NULL, doc 03 §3.15.6).
- Khoảng hiệu lực dạng nửa mở `[effective_from, effective_to)` (doc 03 §3.15.2).

## 9. Quy tắc OCR variants (scan route)

- Dùng **tesseract vie** (psm 3): đúng diacritics VN; benchmark 300 DPI ~29.78 s/page, phrase hit 0.5834 trên NĐ 168 1-bit CCITT scan — **600 DPI không cải thiện chất lượng, giữ 300** (suite-a-first-pass-report.md §5; data/evaluation/ocr-dpi-benchmark/run-20260809-120116-24f592/). **CER/WER chưa được đo trong first pass** — sẽ đo trong VNLRAG-97 (Suite A finalization) với human transcription.
- Xử lý (doc 03:1056-1064):
  - khoảng trắng/thụt lề bất thường;
  - nhãn bị dính (`a)Điều` thay vì `a) Điều`): trên text OCR-derived dùng regex **`^([a-zđ])\)\s*`** (khoảng trắng optional — label ngay sau `)` không có space vẫn là điểm bắt đầu hợp lệ, doc 03:1059); trên born-digital text-layer dùng dạng strict `^([a-zđ])\)\s` (§3);
  - **d↔đ** nhầm lẫn (dùng pattern ngữ cảnh + bảng chuẩn hóa, ghi cờ ambiguity khi không chắc);
  - chữ số La Mã bị lẫn (Chương I/II/III…);
  - header/footer lặp không phải nội dung pháp lý (loại bỏ theo quy tắc, ghi leakage vào corpus QA).
- **Khi pattern/context không đủ → gắn cờ `needs_review`, KHÔNG tự sửa/suy đoán**.
- **Scan-derived docs**: d/đ ambiguity / provenance thấp (Group A `provenance_coverage < 0.9` hoặc bbox thiếu) / structural mismatch → route review (VNLRAG-155), **KHÔNG auto-index partial OCR** (parser_router.yaml scan-review policy; suite-a-first-pass-report.md L93-105, 142-144).

## 10. Fallback hierarchy (khi labels absent trong IR)

- **Dựng cây từ reading_order contiguity**:
  - text element match `^Điều\s+\d+\.` = article head;
  - list_item run sau nó (tới Điều/Chương head kế) thuộc article;
  - clause intro (dòng kết thúc "gồm:" / "như sau:" / "sau đây:") mở clause;
  - point-run = các list_item kế tiếp cho tới clause head / Điều head kế;
  - **Gán số Khoản theo count**, **chữ Điểm theo vị trí** `a→b→c→d→đ→e`.
- **Merged-text IR** (nd p1-e0 3049 chars, tt p1-e9 inline a–d): chạy regex trên toàn bộ page/element text; merge page-boundary sentence fragments tới khi gặp label mới / `Điều` / `\d+.`.
- **Group B gates verify** (doc 03:961-968, parser_router.yaml L55-62):
  - Point label detection ≥ 0.9;
  - Hierarchy completeness ≥ 0.9;
  - Short-Point retention (không ngưỡng loại bỏ);
  - Article/Clause/Point P/R/F1 vs gold (thresholds sau Suite A).
  - Fallback (L970-974): Group B fail → hủy kết quả structural (supersede), full rerun alternate parser, **không index kết quả structural một phần**.
- **State parser**: `current_chapter / current_section / current_article / current_clause / current_point`; output `LegalProvision[]` với `source_element_ids`, `page_number`, `bbox` kế thừa từ element (doc 03 §3.8.6 L1108-1124).

## 11. Ví dụ từ văn bản giao thông thực tế

### Ví dụ 1 — nd-168 Điều 5 → Khoản 1 → Điểm a–đ–e

Raw (nd-168-2024-fixture.pdf.txt, L6-12):

```text
Điều 5. Xử phạt người điều khiển xe ô tô và các loại xe tương tự xe ô tô vi phạm quy tắc giao thông đường bộ

1. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng đối với người điều khiển xe thực hiện một trong các hành vi vi phạm sau đây:
a) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;
b) Điều khiển xe đi ngược chiều trên đường có biển báo "Đường một chiều";
c) Dừng xe, đỗ xe tại nơi có biển cấm dừng, cấm đỗ;
d) Không giữ khoảng cách an toàn với xe chạy liền trước theo quy định;
đ) Lùi xe không quan sát phía sau, gây nguy hiểm cho người và phương tiện;
e) Vượt xe trong các trường hợp không được vượt theo quy định.
```

provision_id sinh ra:

```text
nd-168-2024__dieu-5__khoan-1__diem-a
nd-168-2024__dieu-5__khoan-1__diem-b
nd-168-2024__dieu-5__khoan-1__diem-c
nd-168-2024__dieu-5__khoan-1__diem-d
nd-168-2024__dieu-5__khoan-1__diem-đ
nd-168-2024__dieu-5__khoan-1__diem-e
```

Gold cross-check: nd-gold có cây `dieu-5__khoan-1` với `__diem-đ` tách biệt khỏi `__diem-d` sibling (spike 22 §3.2; nd-gold L65-76).

### Ví dụ 2 — luat Điều 3 → Khoản 1 → Điểm a–đ–e

Raw (luat-traffic-2024-fixture.pdf.txt, L8-14):

```text
Điều 3. Giải thích từ ngữ

1. Trong Luật này, các từ ngữ dưới đây được hiểu như sau:
a) Phương tiện giao thông đường bộ gồm phương tiện giao thông cơ giới đường bộ và phương tiện giao thông thô sơ đường bộ;
b) Người tham gia giao thông đường bộ gồm người điều khiển phương tiện giao thông đường bộ, người sử dụng phương tiện giao thông đường bộ, người đi bộ trên đường bộ và người được phép lưu thông trên đường bộ;
c) Người điều khiển phương tiện giao thông đường bộ là người điều khiển phương tiện giao thông cơ giới đường bộ hoặc phương tiện giao thông thô sơ đường bộ;
d) Người sử dụng phương tiện giao thông đường bộ là người được chủ phương tiện giao thông đường bộ giao quản lý hoặc sử dụng phương tiện theo quy định của pháp luật;
đ) Người đi bộ là người đi bộ trên đường bộ, bao gồm cả người đi bộ qua đường;
e) Người được phép lưu thông trên đường bộ là người được cơ quan nhà nước có thẩm quyền cấp phép lưu thông trên đường bộ theo quy định của pháp luật.
```

provision_id sinh ra:

```text
luat-36-2024__dieu-3__khoan-1__diem-a
luat-36-2024__dieu-3__khoan-1__diem-b
luat-36-2024__dieu-3__khoan-1__diem-c
luat-36-2024__dieu-3__khoan-1__diem-d
luat-36-2024__dieu-3__khoan-1__diem-đ
luat-36-2024__dieu-3__khoan-1__diem-e
```

Gold cross-check: luat-gold L77-88 (cây `dieu-3__khoan-1` với `__diem-đ` distinct, L78). IR note: points là p1-e2..p1-e7 (ro=2-7; p1-e1 ro=1 = Khoản 1 intro, số bị strip → label phải tái dựng; p1-e6 text giữ "đ) Người đi bộ...").

### Ví dụ 3 — luat Điều 8 → Khoản 1 → Điểm a–g (short points)

Raw (luat-traffic-2024-fixture.pdf.txt, L29-35):

```text
Điều 8. Phân loại đường bộ

1. Đường bộ được phân loại theo cấp kỹ thuật gồm:
a) Đường cao tốc;
b) Đường quốc lộ;
c) Đường tỉnh;
d) Đường huyện;
đ) Đường xã;
e) Đường đô thị;
g) Đường chuyên dùng.
```

provision_id sinh ra:

```text
luat-36-2024__dieu-8__khoan-1__diem-a   # "a) Đường cao tốc" — short point (3 từ)
luat-36-2024__dieu-8__khoan-1__diem-b
luat-36-2024__dieu-8__khoan-1__diem-c
luat-36-2024__dieu-8__khoan-1__diem-d   # "d) Đường huyện" — short point (2 từ)
luat-36-2024__dieu-8__khoan-1__diem-đ   # "đ) Đường xã" — short point (2 từ)
luat-36-2024__dieu-8__khoan-1__diem-e
luat-36-2024__dieu-8__khoan-1__diem-g
```

Gold cross-check: luat-gold L150-184 (`dieu-8-k1` a/d/đ short_point:true, retained:true); `short_point_annotation.json` 3 cases; `point_label_d_dd.json` xác nhận d)/đ) distinct. IR note: clause intro là p1-e14 (ro=14, "gồm:"); points p1-e15..e21 (ro=15-21; chỉ e16 "b) Đường quốc lộ;" và e19 "đ) Đường xã;" giữ label).

## 12. Nguồn tham khảo

- `docs/00-scope-and-decisions.md` mục 4.2
- `docs/03-thiet-ke-he-thong.md` §3.7.3 (L948-999), §3.8 (L1023-1139; L1041 bảng chữ cái, L1046-1048 d/đ, L1052-1054 short-point, L1056-1064 OCR, L1066-1106 provision_id, L1108-1124 output), §3.14.1 (L2874-2887), §3.15 (L2925-2987; L2929-2934 manifest priority, L2985 no-guessing)
- `docs/06-test-evaluation.md` L196-219, L1070-1092, L2266-2271
- `docs/spike-vnlrag-22-structure-extraction-evidence.md`
- `docs/spike-vnlrag-21-ir-provenance-contract.md`
- `templates/legal-provision.schema.json` (pattern L39, effective L57-69/100-105)
- `templates/corpus-manifest.schema.json` (DocumentType L54)
- `docs/parser_router.yaml` (L39-48, L55-62)
- Gold fixtures: `backend/tests/fixtures/parser_benchmark/gold/` (nd/luat/tt-gold.json, point_label_d_dd.json, short_point_annotation.json, parent_context_annotation.json) + `golden-stable-id/stable_id_diem_d_dd.json`
- `docs/evaluation/suite-a-first-pass-report.md` (OCR benchmark, scan-review policy)

---

**VNLRAG-23 — v2 parsing/normalization rules. Committed 2026-08-09. Drives VNLRAG-26/28 (extractor) + VNLRAG-97 (Suite A finalization). Replaces docs/rulespec/ v1 (UDEF-era).**
