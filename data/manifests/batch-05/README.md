# Corpus Batch 05 — VNLRAG-125

Năm văn bản giao thông chính thức được ghi nhận bằng provenance metadata (URL nguồn, thời điểm tải và SHA-256 được cung cấp trong từng manifest). Cùng 18 văn bản của batch-01..04, corpus có **23 documents** (nằm trong mục tiêu W5 17–25). PDF không commit theo chính sách repository, nên các digest không thể được kiểm chứng độc lập từ checkout này.

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

## Review, provenance và evaluation readiness

- Tất cả manifest giữ `review_status: PENDING`; chưa có reviewer identity/decision nên chưa đủ điều kiện đánh dấu `ACCEPTED`.
- `file_hash` được ghi là SHA-256 của PDF tại `source_url`; PDF không commit theo chính sách repository. Việc xác nhận digest và nội dung phải thực hiện từ bản tải chính thức tương ứng.
- Nguồn phát hành được ghi nhận là Cổng Thông tin điện tử Chính phủ (`vanban.chinhphu.vn`) và kho tệp `datafiles.chinhphu.vn`.
- Gold set hiện có trong repository (`data/gold-sets/development/`) chỉ tham chiếu `tt-24-2024-tt-bgtvt`, `nd-100-2019`, `tt-24-2023` và `tt-79-2024`; không có tài liệu batch-05 nào được gold-reference. Validation set 40 câu và corpus review records cho batch-05 chưa có trong checkout này.
- Vì chưa có corpus review records và gold-reference coverage, batch-05 **chưa evaluation-ready**. Không được dùng trạng thái `PENDING` để phục vụ, và không được tuyên bố đã hoàn tất gate đánh giá.
- Cumulative count đã tính cả batch-01..04: 18 + 5 = 23. Các gold-referenced documents và relation candidates vẫn cần corpus review records xác nhận trước evaluation-ready gate.
