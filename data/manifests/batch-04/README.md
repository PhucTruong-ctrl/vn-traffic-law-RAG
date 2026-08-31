# Corpus Batch 04 — VNLRAG-124

Bốn văn bản giao thông chính thức, có manifest và SHA-256 đo từ PDF tải được ngày 26/08/2026. Cùng 14 văn bản của batch-01..03, corpus có **18 documents**.

## Danh sách

| document_id | Văn bản | Trạng thái review |
|---|---|---|
| `nd-119-2024` | Nghị định 119/2024/NĐ-CP — thanh toán điện tử giao thông đường bộ | PENDING |
| `nd-44-2024` | Nghị định 44/2024/NĐ-CP — tài sản kết cấu hạ tầng giao thông đường bộ | PENDING |
| `tt-16-2024` | Thông tư 16/2024/TT-BGTVT — lựa chọn nhà đầu tư trạm dừng nghỉ | PENDING |
| `tt-39-2024` | Thông tư 39/2024/TT-BGTVT — tải trọng, khổ giới hạn và hàng siêu trường | PENDING |

## Chuỗi quan hệ

1. `nd-119-2024` **IMPLEMENTS** `luat-35-2024-qh15` và `luat-36-2024-qh15`.
2. `nd-44-2024` **IMPLEMENTS** `luat-35-2024-qh15`.
3. `tt-16-2024` **IMPLEMENTS** `luat-35-2024-qh15`.
4. `tt-39-2024` **IMPLEMENTS** `luat-35-2024-qh15`.

Các quan hệ là quan sát từ tiêu đề/phạm vi điều chỉnh và cần provision-level resolver xác nhận; không gắn AMENDS khi văn bản không nêu sửa đổi.
## Structural QA

Biên bản QA cấu trúc mục tiêu, gồm các mốc `Điều/Khoản/Điểm` của Nghị định 168/2024 và ghi chú routing cho bốn văn bản batch này, nằm tại [`docs/evaluation/batch-04-structural-qa.md`](../../../docs/evaluation/batch-04-structural-qa.md). Báo cáo chỉ ghi nhận cấu trúc đã có trong artifact/references của repository và các candidate relation; không khẳng định OCR/provision counts chưa được review.

PDF không commit theo chính sách repository; `file_hash` là SHA-256 của đúng URL trong manifest. Chưa đánh dấu ACCEPTED vì batch này chỉ cung cấp provenance và routing evidence.
