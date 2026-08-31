# Corpus Batch 05 — VNLRAG-125

Năm văn bản giao thông chính thức, có provenance và SHA-256 đo từ PDF tại `datafiles.chinhphu.vn` ngày 31/08/2026. Cùng 18 văn bản của batch-01..04, corpus có **23 documents** (nằm trong mục tiêu W5 17–25).

## Danh sách

| document_id | Văn bản | Hiệu lực | Trạng thái review |
|---|---|---|---|
| `nd-158-2024` | Nghị định 158/2024/NĐ-CP — hoạt động vận tải đường bộ | 01/01/2025 → | PENDING |
| `nd-67-2023` | Nghị định 67/2023/NĐ-CP — bảo hiểm bắt buộc trách nhiệm dân sự chủ xe cơ giới | 06/09/2023 → | PENDING |
| `tt-05-2024` | Thông tư 05/2024/TT-BGTVT — sửa đổi quy định vận tải, phương tiện và người lái | 01/06/2024 → | PENDING |
| `tt-18-2024` | Thông tư 18/2024/TT-BGTVT — sửa đổi quy định vận tải bằng xe ô tô | 15/07/2024 → | PENDING |
| `tt-51-2024` | Thông tư 51/2024/TT-BGTVT — QCVN 41:2024/BGTVT về báo hiệu đường bộ | 01/01/2025 → | PENDING |

## Chuỗi quan hệ ứng viên

1. `nd-158-2024` **REPLACES** Nghị định 10/2020/NĐ-CP và văn bản sửa đổi liên quan.
2. `nd-67-2023` có quan hệ liên ngành với Luật Trật tự, an toàn giao thông đường bộ 36/2024/QH15; Nghị định 220/2026/NĐ-CP là văn bản sửa đổi được phát hiện trong quá trình provenance review.
3. `tt-05-2024` **AMENDS** các thông tư về vận tải đường bộ, dịch vụ hỗ trợ vận tải đường bộ, phương tiện và người lái được nêu trong văn bản.
4. `tt-18-2024` **AMENDS** Thông tư 12/2020/TT-BGTVT.
5. `tt-51-2024` **REPLACES** QCVN 41:2019/BGTVT.

Các quan hệ trên là candidate relation từ trích yếu/nội dung sửa đổi hoặc thay thế; cần provision-level resolver xác nhận trước khi đưa vào serving graph. Không tự gắn `ACCEPTED` hoặc khẳng định quan hệ chưa được review.

## Review và provenance

- Tất cả manifest giữ `review_status: PENDING`; chưa có reviewer identity/decision nên chưa đủ điều kiện đánh dấu `ACCEPTED`.
- `file_hash` là SHA-256 của đúng PDF tại `source_url`; PDF không commit theo chính sách repository.
- Nguồn phát hành chính thức: Cổng Thông tin điện tử Chính phủ (`vanban.chinhphu.vn`) và kho tệp `datafiles.chinhphu.vn`.
- Cumulative count đã tính cả batch-01..04: 18 + 5 = 23. Gold-referenced documents và relation candidates vẫn cần corpus review records xác nhận trước evaluation-ready gate.
