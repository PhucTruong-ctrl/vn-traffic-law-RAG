# Corpus Batch 03 — VNLRAG-123

5 văn bản chính thức pháp luật giao thông Việt Nam, có manifest + SHA-256,
validate theo `templates/corpus-manifest.schema.json` (VNLRAG-16).
Ghi nhận **3 chuỗi sửa đổi/thay thế/bãi bỏ** (yêu cầu W3: ≥2 chuỗi).

## Danh sách văn bản (5)

| document_id | Văn bản | Loại | Hiệu lực | Trạng thái |
|---|---|---|---|---|
| `nd-238-2026` | Nghị định 238/2026/NĐ-CP (sửa đổi NĐ 168/2024) | DECREE | 15/08/2026 → (chưa hiệu lực tại ngày tải 14/08/2026) | NOT_YET_EFFECTIVE |
| `nd-236-2026` | Nghị định 236/2026/NĐ-CP (sửa đổi NĐ 151/2024) | DECREE | 01/07/2026 → (hiện hành) | EFFECTIVE |
| `nd-151-2024` | Nghị định 151/2024/NĐ-CP (chi tiết thi hành Luật TTATGTĐB) | DECREE | 01/01/2025 → (hiện hành, đã sửa đổi) | EFFECTIVE |
| `tt-51-2025` | Thông tư 51/2025/TT-BCA (sửa đổi TT 79/2024 đăng ký xe) | CIRCULAR | 01/07/2025 → (hiện hành) | EFFECTIVE |
| `tt-37-2026` | Thông tư 37/2026/TT-BCA (sửa đổi các TT đăng ký, kiểm định) | CIRCULAR | 08/06/2026 → (hiện hành) | EFFECTIVE |

## Chuỗi quan hệ (3 chuỗi AMENDS + 1 quan hệ IMPLEMENTS)

| Chuỗi | Quan hệ | Căn cứ trong văn bản |
|---|---|---|
| **A. Xử phạt giao thông đường bộ** | `nd-238-2026` **AMENDS** `nd-168-2024` (batch-01) | Chương I, Điều 1-19 sửa đổi/bổ sung/bãi bỏ nhiều điều của NĐ 168/2024; Điều 20 (hiệu lực 15/08/2026), Điều 21 (chuyển tiếp) |
| **B. Đăng ký xe** | `tt-51-2025` **AMENDS** `tt-79-2024` (batch-01); `tt-37-2026` **AMENDS** `tt-79-2024` (batch-01) | TT 51/2025 Điều 1, Điều 3 (hiệu lực 01/07/2025); TT 37/2026 Chương I, Điều 7 (hiệu lực 08/06/2026). Chuỗi đầy đủ: TT 79/2024 → TT 13/2025 (ngoài corpus) → TT 51/2025 → TT 37/2026 |
| **C. Thi hành Luật TTATGTĐB** | `nd-236-2026` **AMENDS** `nd-151-2024` (batch-03); `nd-151-2024` **IMPLEMENTS** `luat-36-2024-qh15` (batch-01) | NĐ 236/2026 Điều 1-16, Điều 18 (hiệu lực 01/07/2026); NĐ 151/2024 Điều 38.1 (hiệu lực 01/01/2025) + Điều 38.2 **REPEALS** NĐ 109/2009, NĐ 30/2024, NĐ 80/2009, một phần NĐ 10/2020 |

## Nguồn

Tất cả PDF tải từ **Cổng TTĐT Chính phủ** (`datafiles.chinhphu.vn` —
`vanban.chinhphu.vn`), nguồn chính thức, curl-verified 200 + application/pdf
ngày 2026-08-14 (browser User-Agent — portal 403 plain curl). docid vanban
của từng văn bản ghi trong `relation_notes` của mỗi manifest.

## Cấu trúc

```
data/
├── nd-238-2026/source/nd-238-2026.pdf   (626,064 bytes)
├── nd-236-2026/source/nd-236-2026.pdf   (1,260,116 bytes)
├── nd-151-2024/source/nd-151-2024.pdf   (2,224,921 bytes)
├── tt-51-2025/source/tt-51-2025.pdf      (241,476 bytes)
├── tt-37-2026/source/tt-37-2026.pdf      (2,722,734 bytes)
└── manifests/batch-03/*.manifest.json    (5 manifests — COMMIT)
```

## Ghi chú

- **PDFs nằm trong `data/` — gitignored, KHÔNG commit**; chỉ manifests +
  README được commit (doc 05 §5.3.1: "chỉ manifest được commit").
- **Text layer**: toàn bộ 5 file là scan-only (nội dung là ảnh; pdftotext chỉ
  ra dòng metadata chữ ký số) — đi qua router scan: Docling OCR → Group A gates
  → MinerU fallback, giống nhóm scan của batch-01. Các dữ kiện chuỗi quan hệ
  (điều/khoản sửa đổi, hiệu lực, bãi bỏ) được xác minh bằng OCR trực tiếp từ
  PDF tải về, đối chiếu với metadata chính thức trên vanban.chinhphu.vn.
- **`nd-238-2026`**: NĐ 238/2026 ban hành 26/06/2026, có hiệu lực 15/08/2026 —
  tại ngày tải manifest (14/08/2026) chưa hiệu lực nên `status =
  NOT_YET_EFFECTIVE` (hữu ích cho temporal resolver: sự kiện sửa đổi sắp tới
  của NĐ 168/2024).
- **`nd-151-2024`**: văn bản gốc hiện hành theo bản đã sửa đổi bởi NĐ
  184/2025/NĐ-CP và NĐ 236/2026/NĐ-CP (batch-03); các mắt xích trung gian ghi
  trong `relation_notes`.
- Mọi manifest đã validate: `cd backend && uv run python -m scripts.validate_manifest
  ../data/manifests/batch-03/<id>.manifest.json` → PASS.
