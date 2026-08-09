# Corpus Batch 01 — VNLRAG-19

3-5 văn bản chính thức pháp luật giao thông Việt Nam (hiện hành + lịch sử),
có manifest + SHA-256, validate theo `templates/corpus-manifest.schema.json`
(VNLRAG-16).

## Danh sách văn bản (5)

| document_id | Văn bản | Loại | Hiệu lực | Trạng thái |
|---|---|---|---|---|
| `nd-168-2024` | Nghị định 168/2024/NĐ-CP (xử phạt VPHC TTATGT) | DECREE | 01/01/2025 → (hiện hành) | EFFECTIVE |
| `nd-100-2019` | Nghị định 100/2019/NĐ-CP (xử phạt VPHC GTĐB+ĐS) | DECREE | [01/01/2020, 01/01/2025) phần đường bộ | PARTIALLY_EFFECTIVE (phần đường sắt còn hiệu lực) |
| `luat-36-2024-qh15` | Luật Trật tự, ATGT đường bộ 2024 | LAW | 01/01/2025 → (hiện hành) | EFFECTIVE |
| `tt-79-2024` | Thông tư 79/2024/TT-BCA (đăng ký xe) | CIRCULAR | 01/01/2025 → (hiện hành) | EFFECTIVE |
| `tt-24-2023` | Thông tư 24/2023/TT-BCA (đăng ký xe cũ) | CIRCULAR | [15/08/2023, 01/01/2025) | EXPIRED (bãi bỏ bởi 79/2024) |

## Nguồn

Tất cả PDF tải từ **Cổng TTĐT Chính phủ** (`datafiles.chinhphu.vn` —
`vanban.chinhphu.vn`), nguồn chính thức, curl-verified 200 + application/pdf.
Chi tiết docid + URL từng văn bản ghi trong `relation_notes` của mỗi manifest.

## Cấu trúc

```
data/
├── nd-168-2024/source/nd-168-2024.pdf          (1 phần)
├── nd-100-2019/source/nd-100-2019.pdf          (merged từ 2 phần nguồn)
├── luat-36-2024-qh15/source/luat-36-2024.pdf   (merged từ 2 phần nguồn)
├── tt-79-2024/source/tt-79-2024.pdf             (1 phần)
├── tt-24-2023/source/tt-24-2023.pdf             (1 phần)
└── manifests/batch-01/*.manifest.json           (5 manifests — COMMIT)
```

## Ghi chú

- **PDFs nằm trong `data/` — gitignored, KHÔNG commit**; chỉ manifests +
  README được commit (doc 05 §5.3.1: "chỉ manifest được commit").
- Văn bản 2 phần (ND 100/2019, Luật 36/2024): merge thành 1 PDF canoncial
  bằng `pdfunite`; `file_hash` = SHA-256 của file merged đầy đủ (không phải
  hash một phần). URL nguồn 2 phần ghi trong `relation_notes`.
- `effective_to` là cận trên loại trừ (half-open interval): văn bản bị bãi
  bỏ từ 01/01/2025 ghi `effective_to: "2025-01-01"` (TT 24/2023); NĐ 100/2019
  chỉ bãi bỏ phần đường bộ nên `status = PARTIALLY_EFFECTIVE`, `effective_to
  = null` — khoảng [2020-01-01, 2025-01-01) áp cho provision đường bộ ở tầng
  temporal resolution.
- Một số PDF (168/2024, 79/2024) là bản scan signed — không có text layer;
  pipeline parser sẽ dùng OCR (Docling/MinerU) — ghi nhận cho Suite A.
- Mọi manifest đã validate: `cd backend && uv run python -m scripts.validate_manifest
  ../data/manifests/batch-01/<id>.manifest.json` → PASS.
