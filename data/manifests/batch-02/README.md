# Corpus Batch 02 — VNLRAG-122

4 văn bản chính thức pháp luật giao thông Việt Nam (born-digital text-layer PDF,
đã verify qua pdftotext), có manifest + SHA-256, validate theo
`templates/corpus-manifest.schema.json` (VNLRAG-16).

## Danh sách văn bản (4)

| document_id | Văn bản | Loại | Hiệu lực | Trạng thái |
|---|---|---|---|---|
| `luat-35-2024-qh15` | Luật Đường bộ 35/2024/QH15 | LAW | 01/01/2025 → (hiện hành) | EFFECTIVE |
| `vbhn-49-2026-vpqh` | VBHN 49/VBHN-VPQH (hợp nhất Luật Đường bộ) | OTHER | 17/03/2026 → (hiện hành) | EFFECTIVE |
| `vbhn-55-2026-vpqh` | VBHN 55/VBHN-VPQH (hợp nhất Luật TTATGTĐB) | OTHER | 23/03/2026 → (hiện hành) | EFFECTIVE |
| `tt-35-2024` | Thông tư 35/2024/TT-BGTVT (đào tạo, sát hạch, cấp GPLX) | CIRCULAR | 01/01/2025 → (hiện hành) | EFFECTIVE |

## Nguồn

Tất cả PDF tải từ **Cổng TTĐT Chính phủ** (`datafiles.chinhphu.vn`), nguồn
chính thức, curl-verified 200 + application/pdf ngày 2026-08-09 (browser
User-Agent — portal 403 plain curl). URL từng văn bản ghi trong `source_url`
của mỗi manifest.

## Cấu trúc

```
data/
├── luat-35-2024-qh15/source/luat-35-2024-qh15.pdf   (743,123 bytes)
├── vbhn-49-2026-vpqh/source/vbhn-49-2026-vpqh.pdf   (1,500,044 bytes)
├── vbhn-55-2026-vpqh/source/vbhn-55-2026-vpqh.pdf   (2,379,606 bytes)
├── tt-35-2024/source/tt-35-2024.pdf                  (1,443,001 bytes)
└── manifests/batch-02/*.manifest.json                (4 manifests — COMMIT)
```

## Trạng thái text layer (từng file)

| document_id | Text layer | pdftotext | Nguồn | Ghi chú |
|---|---|---|---|---|
| `luat-35-2024-qh15` | YES (born-digital) | 69 trang, 2631 dòng | datafiles.chinhphu.vn/cpp/files/vbpq/2024/9/35-2024-qh15.pdf | Văn bản gốc Luật Đường bộ |
| `vbhn-49-2026-vpqh` | YES (born-digital) | 66 trang, 2723 dòng | datafiles.chinhphu.vn/cpp/files/vbpq/2026/3/49-vbhn-vpqh.pdf | VBHN Luật Đường bộ (incl. sửa đổi 118/2025/QH15) |
| `vbhn-55-2026-vpqh` | YES (born-digital) | 74 trang, 3135 dòng | datafiles.chinhphu.vn/cpp/files/vbpq/2026/3/55-vbhn-vpqh.pdf | VBHN Luật TTATGTĐB 36/2024 (incl. sửa đổi 118/2025/QH15) |
| `tt-35-2024` | YES (born-digital) | 69 trang, 3740 dòng | datafiles.chinhphu.vn/cpp/files/vbpq/2024/12/35-bgtvt.pdf | PDF chính có text layer |

Toàn bộ 4 file là born-digital text layer (đã verify qua pdftotext: 2 trang đầu
hiển thị nội dung pháp lý thật, không rỗng/ký số-only) — **không đi qua router
scan/OCR**, đi thẳng đường born-digital text.

## Ghi chú

- **PDFs nằm trong `data/` — gitignored, KHÔNG commit**; chỉ manifests +
  README được commit (doc 05 §5.3.1: "chỉ manifest được commit").
- **Loại trừ phụ lục TT 35/2024**: `tt-35-2024` có phụ lục kèm theo tại
  `35-bgtvt-kem.pdf` nhưng file đó là **scan-only** (không có text layer) — bị
  loại khỏi batch-02 để ưu tiên born-digital text. Nội dung phụ lục chưa được
  corpus bao phủ cho đến khi OCR và review. Việc loại trừ được ghi trong
  `relation_notes` của manifest `tt-35-2024`.
- **Chính sách VBHN (văn bản hợp nhất)**: `vbhn-49-2026-vpqh` và
  `vbhn-55-2026-vpqh` là bản hợp nhất phục vụ **current-text retrieval**,
  quan hệ `RELATED_TO` luật gốc, **không** `SUPERSEDES` luật gốc. Effective
  windows của từng provision phải được resolver xác định từ luật gốc và các
  sự kiện sửa đổi (vd. Luật 118/2025/QH15 có hiệu lực 01/07/2026) — chi tiết
  trong `relation_notes` của từng manifest.
- Mọi manifest đã validate: `cd backend && uv run python -m scripts.validate_manifest
  ../data/manifests/batch-02/<id>.manifest.json` → PASS.
