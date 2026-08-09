# Canonical Document IR — Thiết kế contract (M0 scope baseline / W1; triển khai: VNLRAG-128 / W2)

> Nguồn: `docs/03-thiet-ke-he-thong.md` §3.6 (+ doc 08 versioning) — VNLRAG v2 scope freeze M0

## 1. Mục đích

Canonical Document IR là biểu diễn trung gian **parser-neutral** do dự án sở hữu (FR-02). Nó cô lập toàn bộ phân tích pháp lý khỏi định dạng đầu ra của Docling/MinerU: Legal Structure Extractor và các module phía sau chỉ đọc IR, không đọc `DoclingDocument` hay output JSON của MinerU.

Tài liệu này là contract IR ở trạng thái **M0 scope baseline**; thiết kế contract được thực hiện ở W1 (22/07, `docs/05-ke-hoach-trien-khai.md` §5.4: "Thiết kế schema Canonical Document IR — `ParsedDocument`, `ParsedPage`, `DocumentElement`", FR-02; doc 03 mục 3.6) và làm **baseline cho triển khai** ticket VNLRAG-128 (W2). Toàn bộ field, kiểu và cấu trúc dưới đây được **đóng băng (freeze)** cho scope M0 của VNLRAG v2; thay đổi sau này phải qua quy tắc versioning ở mục 8.

## 2. Cấu trúc tổng quan

Cấu trúc phân cấp ba tầng (doc 03 §3.6.1):

```text
ParsedDocument
  └── ParsedPage[]
      └── DocumentElement[]
```

- `ParsedDocument` chứa metadata cấp tài liệu và danh sách trang.
- Mỗi `ParsedPage` chứa thông tin vật lý của trang và danh sách element.
- Mỗi `DocumentElement` mang đầy đủ field theo canonical spec (xem mục 6).

Tất cả model dùng **Pydantic v2** với `ConfigDict(extra="forbid")` — mọi field không khai báo đều bị từ chối, đảm bảo IR không bị nhiễm field không canonical từ parser (doc 03 §3.6.2-3.6.4).

## 3. ParsedDocument

Từ doc 03 §3.6.2 (dòng 803-816). Model gốc:

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ParsedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parsed_document_id: str            # UUID, không phải document_id pháp lý
    document_id: str                   # document_id pháp lý từ manifest
    parser: str                        # "DOCLING" | "MINERU"
    parser_version: str                # pin version, ví dụ "docling-2.1.x"
    ir_schema_version: str             # ví dụ "document-ir-v1"
    source_object_key: str             # object key PDF nguồn trong MinIO
    pages: list["ParsedPage"]
    parse_started_at: datetime
    parse_completed_at: datetime
    quality_report: dict               # kết quả quality gate cấp tài liệu
```

| Field | Kiểu | Mô tả |
|---|---|---|
| `parsed_document_id` | `str` | UUID, **không phải** `document_id` pháp lý |
| `document_id` | `str` | `document_id` pháp lý lấy từ manifest |
| `parser` | `str` | `"DOCLING" \| "MINERU"` |
| `parser_version` | `str` | Pin version, ví dụ `"docling-2.1.x"` |
| `ir_schema_version` | `str` | Ví dụ `"document-ir-v1"` |
| `source_object_key` | `str` | Object key PDF nguồn trong MinIO |
| `pages` | `list["ParsedPage"]` | Danh sách trang |
| `parse_started_at` | `datetime` | Thời điểm bắt đầu parse |
| `parse_completed_at` | `datetime` | Thời điểm hoàn tất parse |
| `quality_report` | `dict` | Kết quả quality gate cấp tài liệu |

## 4. ParsedPage

Từ doc 03 §3.6.3 (dòng 821-829). Model gốc:

```python
class ParsedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int                   # số trang 1-based theo PDF
    width: float | None
    height: float | None
    text: str | None                   # văn bản toàn trang (khi parser cung cấp)
    elements: list["DocumentElement"]
```

| Field | Kiểu | Mô tả |
|---|---|---|
| `page_number` | `int` | Số trang **1-based** theo PDF |
| `width` | `float \| None` | Chiều rộng trang (khi parser cung cấp) |
| `height` | `float \| None` | Chiều cao trang (khi parser cung cấp) |
| `text` | `str \| None` | Văn bản toàn trang (khi parser cung cấp) |
| `elements` | `list["DocumentElement"]` | Danh sách element trên trang |

## 5. BoundingBox

Từ doc 03 §3.6.4 (dòng 836-844). Model gốc:

```python
class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    right: float
    bottom: float
    page_height: float | None = None
    page_width: float | None = None
```

| Field | Kiểu | Mô tả |
|---|---|---|
| `left` | `float` | Tọa độ trái |
| `top` | `float` | Tọa độ trên |
| `right` | `float` | Tọa độ phải |
| `bottom` | `float` | Tọa độ dưới |
| `page_height` | `float \| None` | Chiều cao trang (mặc định `None`) |
| `page_width` | `float \| None` | Chiều rộng trang (mặc định `None`) |

## 6. DocumentElement

Từ doc 03 §3.6.4 (dòng 847-862). Mỗi element mang đầy đủ field theo canonical spec mục 5. Model gốc:

```python
class DocumentElement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_id: str                   # định danh ổn định trong parsed document
    element_type: str                 # title, heading, paragraph, table, list_item, figure, page_header, page_footer, ...
    text: str                         # nội dung văn bản của element
    page_number: int
    bbox: BoundingBox | None = None
    reading_order: int                # thứ tự đọc toàn tài liệu (0-based)
    parent_element_id: str | None     # element cha (cấu trúc khối)
    table_html: str | None = None     # khi element_type = table
    source_parser: str                # "DOCLING" | "MINERU"
    parser_version: str               # pin version parser
    parser_confidence: float | None   # confidence parser nếu cung cấp
    raw_reference: dict               # tham chiếu trở lại đầu ra parser gốc
```

| Field | Kiểu | Mô tả |
|---|---|---|
| `element_id` | `str` | Định danh ổn định trong parsed document |
| `element_type` | `str` | `title`, `heading`, `paragraph`, `table`, `list_item`, `figure`, `page_header`, `page_footer`, ... |
| `text` | `str` | Nội dung văn bản của element |
| `page_number` | `int` | Số trang element nằm trên |
| `bbox` | `BoundingBox \| None` | Tọa độ khối (mặc định `None`) |
| `reading_order` | `int` | Thứ tự đọc toàn tài liệu (**0-based**) |
| `parent_element_id` | `str \| None` | Element cha (cấu trúc khối), mặc định `None` |
| `table_html` | `str \| None` | HTML của bảng khi `element_type = table` (mặc định `None`) |
| `source_parser` | `str` | `"DOCLING" \| "MINERU"` — parser đã tạo element |
| `parser_version` | `str` | Pin version parser |
| `parser_confidence` | `float \| None` | Confidence parser nếu cung cấp |
| `raw_reference` | `dict` | Tham chiếu trở lại đầu ra parser gốc |

## 7. Ví dụ JSON

Reproduce nguyên văn từ doc 03 §3.6.5 (dòng 866-913):

```json
{
  "parsed_document_id": "9f1c2e0a-4b3c-4d5e-8f90-1234567890ab",
  "document_id": "nd-168-2024",
  "parser": "DOCLING",
  "parser_version": "docling-2.1.0",
  "ir_schema_version": "document-ir-v1",
  "source_object_key": "documents/nd-168-2024/source/<sha256>.pdf",
  "pages": [
    {
      "page_number": 12,
      "width": 595.0,
      "height": 842.0,
      "elements": [
        {
          "element_id": "p12-e3",
          "element_type": "heading",
          "text": "Điều 7. Các hành vi xử phạt ...",
          "page_number": 12,
          "bbox": {"left": 60.0, "top": 80.0, "right": 540.0, "bottom": 100.0},
          "reading_order": 40,
          "parent_element_id": null,
          "table_html": null,
          "source_parser": "DOCLING",
          "parser_version": "docling-2.1.0",
          "parser_confidence": 0.99,
          "raw_reference": {"item_id": "docling_item_123", "docling_type": "paragraph"}
        },
        {
          "element_id": "p12-e4",
          "element_type": "paragraph",
          "text": "4. Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với một trong các hành vi sau:",
          "page_number": 12,
          "bbox": {"left": 60.0, "top": 105.0, "right": 540.0, "bottom": 135.0},
          "reading_order": 41,
          "parent_element_id": "p12-e3",
          "table_html": null,
          "source_parser": "DOCLING",
          "parser_version": "docling-2.1.0",
          "parser_confidence": 0.98,
          "raw_reference": {"item_id": "docling_item_124", "docling_type": "paragraph"}
        }
      ]
    }
  ],
  "quality_report": {}
}
```

> Ví dụ mang tính minh họa cấu trúc dữ liệu; con số trong nội dung không phải khẳng định về văn bản thực tế.

## 8. Versioning

IR được version hóa qua field `ir_schema_version` trên `ParsedDocument` (doc 03 §3.6.2; doc 08 §8.3.6, §8.4.5). Baseline hiện tại: `document-ir-v1` (doc 04, dòng 74).

**Quy tắc bump** (doc 08 §8.3.6, §8.4.5):

- Khi parsing pipeline thay đổi cấu trúc IR (thêm/bớt field, đổi semantics của `DocumentElement`), `ir_schema_version` phải bump (ví dụ `document-ir-v2`).
- `DocumentElement` fields được version hóa qua `ir_schema_version` trên `ParsedDocument`.
- Bất kỳ thay đổi field, kiểu field hoặc semantics của IR làm thay đổi cách Legal Structure Extractor đọc dữ liệu đều phải bump.

**Re-normalization procedure** (doc 08 §8.3.6, §8.4.5):

- Nếu **chỉ IR schema** thay đổi: đọc artifact parser gốc từ object storage bucket `parser-outputs`, chuyển sang IR mới bằng adapter hiện hành — **re-normalize, không cần re-parse** (có thể re-project mà không re-parse).
- Nếu **parser version** thay đổi: phải **re-parse** từ PDF nguồn (`source-pdfs`) vì parser output cũ không tương thích, không tái sử dụng parser output cũ.
- Sau khi re-normalize/re-parse, chạy lại quality gates và golden fixtures trước khi viết vào PostgreSQL.

**Idempotency** (doc 08 §8.3.6, dòng 299): idempotency key chứa IR schema version; bump schema làm key đổi, cho phép chạy lại pipeline.

## 9. Parser-neutrality (doc 03 §3.6.6)

- **Legal Structure Extractor chỉ đọc `ParsedDocument`/`DocumentElement`**, không đọc `DoclingDocument` hay output JSON của MinerU. Toàn bộ phân tích pháp lý phụ thuộc duy nhất vào IR.
- Khi thêm parser mới hoặc nâng cấp version parser, **chỉ cần một adapter chuyển output sang IR**; không thay đổi extractor hay các module phía sau (NFR-06).
- Mỗi element ghi `source_parser`, `parser_version`, `raw_reference` để truy vết provenance và phục vụ parser benchmark (Suite A).
- `element_id` ổn định trong phạm vi parsed document, được dùng làm một phần của `source_element_ids` trong `LegalProvision`.

**Hệ quả contract:** mọi consumer của IR (Legal Structure Extractor, quality gates, embedding, index) đọc trực tiếp IR; parser cụ thể chỉ là nguồn dữ liệu sau adapter. Điều này cho phép Parser Router (doc 03 §3.7) đổi parser / supersede artifact cũ mà không phá vỡ pipeline pháp lý.

## 10. Nguồn

- `docs/03-thiet-ke-he-thong.md` §3.6 "Canonical Document IR" (mục 3.6.1-3.6.6)
- `docs/03-thiet-ke-he-thong.md` §3.7 (tương tác IR với Parser Router / quality gates)
- `docs/08-bao-tri.md` §8.3.6 "Canonical Document IR schema versioning trong corpus update" và §8.4.5 "Document IR schema version"
- `docs/04-tech-stack-llm-research.md` (dòng 74: `document-ir-v1`)
- `docs/05-ke-hoach-trien-khai.md` (W2, dòng 198: "Thiết kế schema Canonical Document IR (`ParsedDocument`, `ParsedPage`, `DocumentElement`)" — FR-02; doc 03 mục 3.6)

**VNLRAG v2 scope freeze M0.**
