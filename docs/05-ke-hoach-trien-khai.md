> **MVP đã phê duyệt, 10/09/2026**: Hệ thống single-user chạy localhost/mạng riêng, không có auth/admin/reviewer role/API/UI. Corpus MVP cố định **14 PDF local**, deduplicate theo document/hash, chỉ cho phép nguồn chính xác `datafiles.chinhphu.vn`; ingestion chạy background hoặc CLI, snapshot bất biến và tự động quality/provenance/temporal gates. Query-time chỉ phục vụ corpus, không gọi web. Gold set gồm **200 câu**, đủ **17 nhóm rủi ro**, chạy toàn bộ trước release. Feedback chỉ là telemetry LIKE/DISLIKE tối thiểu, không gating.
>
> **Model policy**: Không khóa tên model hoặc ngưỡng số trong tài liệu này trước khi có benchmark; embedding local được benchmark nhỏ, cache candidate và chỉ rebuild index sau khi chọn cấu hình.
# 05. Kế hoạch triển khai (Implementation Plan)
