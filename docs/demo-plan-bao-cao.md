# Kế hoạch demo khi báo cáo

## 1. Mục tiêu

Demo một flow liên tục từ khởi động hệ thống, xác thực người dùng, hỏi đáp pháp luật, kiểm tra căn cứ, mở citation, tra cứu nguồn độc lập, lưu lịch sử, gửi phản hồi, lưu câu trả lời và kiểm tra các endpoint vận hành.

Flow chính dùng một câu hỏi xuyên suốt:

> Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?

Flow phụ dùng cùng phiên chat để chứng minh các nhánh xử lý:

- Câu hỏi nhiều ý: `Tôi vượt đèn đỏ bằng xe máy và không đội mũ bảo hiểm; bị phạt bao nhiêu?`
- Câu hỏi ngoài phạm vi: `Thời tiết Hà Nội ngày mai thế nào?`
- Tìm nguồn: `vượt đèn đỏ`

Không trình bày phần target architecture chưa có runtime như Parser Router, Canonical IR, LangGraph, Redis, MinIO hoặc PostgreSQL legal source-of-truth.

## 2. Phạm vi đã audit

### Chức năng người dùng

| Nhóm | Chức năng | Cách demo |
|---|---|---|
| Xác thực | Đăng ký, đăng nhập, lấy phiên | Mở `/login`, đăng nhập bằng tài khoản demo; không chiếu mật khẩu hoặc token |
| Hỏi đáp | Gửi câu hỏi pháp luật | Gửi câu hỏi chính trong `/chat` |
| Hiểu câu hỏi | Phân tích intent, loại phương tiện, câu hỏi nhiều ý | Gửi câu hỏi nhiều ý ở bước nhánh |
| Truy hồi | Exact reference, dense/sparse hybrid, RRF-like merge, bounded expansion | Giải thích ngắn khi câu trả lời hiển thị; không gọi chi tiết nội bộ là giao diện người dùng |
| Evidence gate | Chỉ sinh câu trả lời khi đủ căn cứ | Dùng câu hỏi ngoài phạm vi để cho thấy trạng thái từ chối/ngoài phạm vi |
| Citation | Hiển thị nguồn, Điều/Khoản/Điểm và mở passage | Bấm citation trong câu trả lời |
| Nguồn pháp luật | Danh sách văn bản | Mở `/legal-sources` |
| Tìm kiếm nguồn | Tìm theo nội dung, số văn bản, Điều/Khoản/Điểm | Nhập `vượt đèn đỏ`, sau đó dùng bộ lọc nếu cần |
| Viewer Markdown | Mở văn bản Markdown và provision | Mở một kết quả loại Markdown |
| Viewer PDF | Mở PDF, chuyển trang, zoom, highlight nếu citation có bbox | Chỉ demo nếu kết quả có `pdf_url` và metadata trang |
| Lịch sử | Danh sách và mở lại phiên chat | Reload cùng conversation hoặc chọn phiên trong sidebar |
| Đổi tên/xóa phiên | Quản lý session | Chỉ demo nếu còn thời gian; xác nhận trước khi xóa |
| Feedback | LIKE/DISLIKE | Bấm một lựa chọn trên câu trả lời |
| Bookmark | Lưu câu trả lời | Bấm `Lưu câu trả lời` |
| Saved items | Tìm, mở citation, xóa câu trả lời đã lưu | Mở `/saved`, tìm lại, mở nguồn, xóa |

### Chức năng vận hành và đánh giá

| Nhóm | Bằng chứng | Cách demo |
|---|---|---|
| Health | `/api/v1/health`, `/live`, `/ready` | Mở endpoint hoặc chuẩn bị output terminal đã redact |
| Swagger | `/docs` | Mở danh sách route FastAPI |
| Backend checks | Ruff, format, mypy, 161 tests | Trình bày report đã commit, không chạy dài trong lúc báo cáo |
| Frontend checks | lint, typecheck, build, Prettier | Trình bày report đã commit |
| Evaluation | 40 cases, 8 nhóm, metrics | Trình bày `docs/evaluation/release-candidate-20260914.md` |

## 3. Chuẩn bị trước buổi demo

### 3.1. Khởi động

Từ thư mục gốc:

```bash
./dev.sh
```

Mở:

```text
http://127.0.0.1:3000/chat
```

Backend endpoint:

```text
http://127.0.0.1:8000/api/v1/health
http://127.0.0.1:8000/api/v1/health/live
http://127.0.0.1:8000/api/v1/health/ready
http://127.0.0.1:8000/docs
```

### 3.2. Điều kiện cần

- Supabase Auth hoạt động.
- Tài khoản demo đăng nhập được.
- Qdrant có collection `traffic_law`.
- OpenRouter/embedding provider đã cấu hình nếu flow cần sinh câu trả lời.
- Frontend gọi đúng `NEXT_PUBLIC_API_URL`.
- Không để token, mật khẩu, API key hoặc raw session ID xuất hiện trên màn hình ghi hình.

### 3.3. Kiểm tra nhanh

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS http://127.0.0.1:8000/api/v1/health/ready
```

Kết quả lỗi, timeout hoặc provider unavailable phải ghi là lỗi kiểm tra. Không đổi thành trạng thái pass.

## 4. Flow demo chính

### Bước 1 — Giới thiệu phạm vi

Nói ngắn:

> Hệ thống chỉ trả lời dựa trên corpus pháp luật đã lập chỉ mục. Khi thiếu căn cứ hoặc câu hỏi ngoài phạm vi, hệ thống từ chối thay vì tự suy đoán.

Chỉ vào ba vùng giao diện:

1. Khu vực chat.
2. Nguồn pháp luật.
3. Lịch sử và nội dung đã lưu.

### Bước 2 — Đăng nhập

1. Mở trang đăng nhập.
2. Nhập tài khoản demo.
3. Đăng nhập.
4. Cho thấy giao diện đã có user session.
5. Không mở DevTools, không chiếu bearer token.

Điểm cần nói:

- Supabase Auth xác thực người dùng.
- Backend dùng bearer token cho API cần đăng nhập.
- Session, message, feedback và bookmark gắn theo user.

### Bước 3 — Tạo phiên chat

1. Chọn `Cuộc trò chuyện mới`.
2. Nhập:

   ```text
   Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?
   ```

3. Bấm `Gửi`.
4. Chờ trạng thái loading kết thúc.
5. Cho thấy câu trả lời, citation và disclaimer.

Cần chỉ ra:

- Câu hỏi được lưu vào session.
- Hệ thống truy hồi căn cứ trước.
- Evidence gate chạy trước bước sinh câu trả lời.
- Citation được dựng từ metadata nguồn.

Không nói model tự tạo số Điều hoặc tên nguồn.

### Bước 4 — Mở citation

1. Chọn một citation cụ thể.
2. Mở Source Drawer.
3. Chỉ ra tên văn bản, số hiệu, Điều/Khoản/Điểm và đoạn nguồn.
4. Nếu nguồn là Markdown, mở viewer Markdown.
5. Nếu citation có PDF và trang/bbox, mở PDF viewer, chuyển trang hoặc zoom.

Nếu không có PDF hợp lệ:

> Citation này chỉ có nguồn Markdown trong corpus hiện tại; PDF viewer không được trình bày như đã kiểm chứng.

### Bước 5 — Tra cứu nguồn độc lập

1. Mở `Nguồn pháp luật`.
2. Cho thấy danh sách văn bản.
3. Nhập vào ô tìm kiếm:

   ```text
   vượt đèn đỏ
   ```

4. Cho thấy danh sách kết quả lọc.
5. Nếu phù hợp, dùng thêm số văn bản, Điều, Khoản hoặc Điểm.
6. Mở một văn bản và xem provision.

Điểm cần nói:

- Legal explorer là read-only.
- Search chỉ chạy trên corpus nội bộ.
- Không có query-time web search hoặc web fallback.

### Bước 6 — Quay lại session và chứng minh persistence

1. Trở lại sidebar lịch sử.
2. Chọn session vừa tạo.
3. Reload trang conversation.
4. Cho thấy câu hỏi, câu trả lời và citation vẫn còn.

Đây là bằng chứng persistence. Không chỉ dựa vào việc UI đổi route.

### Bước 7 — Feedback và bookmark

1. Trên câu trả lời, bấm `LIKE` hoặc `DISLIKE`.
2. Chờ trạng thái thành công.
3. Bấm `Lưu câu trả lời`.
4. Mở `Đã lưu`.
5. Tìm theo một phần câu hỏi hoặc câu trả lời.
6. Mở saved item.
7. Mở citation từ saved item.
8. Xóa saved item và xác nhận item biến mất.

Điểm cần nói:

- Feedback chỉ là LIKE/DISLIKE tối thiểu.
- Feedback không phải release gate.
- Bookmark là snapshot câu hỏi, câu trả lời và citation.

### Bước 8 — Nhánh câu hỏi nhiều ý

Trong phiên mới, gửi:

```text
Tôi vượt đèn đỏ bằng xe máy và không đội mũ bảo hiểm; bị phạt bao nhiêu?
```

Quan sát:

- Hệ thống trả lời đủ các ý hoặc yêu cầu làm rõ.
- Không được chấp nhận câu trả lời chỉ giải quyết một ý nhưng trình bày như đã đủ.
- Citation phải gắn được với căn cứ trả lời.

Nếu hệ thống yêu cầu làm rõ, ghi nhận đó là kết quả quan sát hợp lệ.

### Bước 9 — Nhánh ngoài phạm vi hoặc thiếu căn cứ

Trong phiên mới, gửi:

```text
Thời tiết Hà Nội ngày mai thế nào?
```

Quan sát:

- Status ngoài phạm vi hoặc thiếu căn cứ.
- Không có citation pháp luật giả.
- Không có câu trả lời suy đoán.

Một API error, timeout hoặc 5xx không được gọi là abstention thành công. Nếu lỗi, ghi nguyên văn lỗi và dừng flow tại đó.

### Bước 10 — Kiểm tra vận hành

Mở lần lượt:

```text
/api/v1/health
/api/v1/health/live
/api/v1/health/ready
/docs
```

Nói:

- `health` trả trạng thái backend.
- `live` kiểm tra process.
- `ready` phản ánh dependency state theo implementation.
- Swagger hiển thị API contract.

Không dùng health xanh để kết luận answer quality, citation quality hoặc full evaluation đã đạt.

### Bước 11 — Trình bày kiểm thử và đánh giá

Không chạy full evaluation trong lúc báo cáo nếu chưa chuẩn bị trước artifact. Mở report đã kiểm tra:

```text
docs/evaluation/release-candidate-20260914.md
```

Trình bày:

- Backend: Ruff, format, mypy, 161 tests passed.
- Frontend: lint 0 errors, typecheck, build, Prettier pass.
- API smoke: HTTP 200 có citation.
- Evaluation: 40 cases, 34 covered, 6 `CORPUS_NOT_COVERED`.
- Citation validity: 1.0, invalid citation rate: 0%.
- Abstention accuracy: 0.9118.
- Manual semantic correctness: N/A.

Cách nói chính xác:

> Kết quả áp dụng cho covered corpus và MVP runtime hiện tại. Đây không phải bằng chứng bao phủ toàn bộ pháp luật giao thông hoặc chứng nhận đầy đủ chất lượng ngữ nghĩa.

## 5. Thứ tự rút gọn nếu thiếu thời gian

Không bỏ flow chính. Rút theo thứ tự:

1. Bỏ đăng ký mới nếu đã có tài khoản demo.
2. Chỉ mở một citation Markdown.
3. Bỏ thao tác đổi tên/xóa session.
4. Giữ lại bookmark search/delete vì đây là persistence độc lập.
5. Giữ nhánh ngoài phạm vi vì đây là bằng chứng verified-or-abstain.
6. Chuyển health/Swagger/evaluation sang slide bằng chứng đã chuẩn bị.

Tối thiểu vẫn phải đi qua:

```text
auth → chat → citation → legal search → reload history → feedback/bookmark → abstention
```

## 6. Bảng ghi nhận trong lúc demo

| Bước | Input / route | Kết quả quan sát | HTTP/status | Citation | Latency ghi nhận | Ghi chú |
|---|---|---|---|---|---|---|
| Đăng nhập | `/login` |  |  |  |  |  |
| Câu hỏi chính | `/chat` |  |  |  |  |  |
| Mở citation | Source Drawer |  |  |  |  |  |
| Tìm nguồn | `/legal-sources?q=vượt đèn đỏ` |  |  |  |  |  |
| Reload session | `/chat/{conversation_id}` |  |  |  |  |  |
| Feedback | message feedback |  |  |  |  |  |
| Bookmark | `/saved` |  |  |  |  |  |
| Ngoài phạm vi | `/chat` |  |  |  |  |  |
| Health | `/api/v1/health*` |  |  |  |  |  |

## 7. Tiêu chí kết thúc demo

Demo chỉ được gọi là hoàn tất khi đã quan sát hoặc trình bày rõ trạng thái của:

- Đăng nhập.
- Câu hỏi pháp luật có căn cứ.
- Citation và source viewer.
- Legal source search có từ khóa đã nhập.
- Reload và persistence của conversation.
- Feedback.
- Bookmark, tìm kiếm và xóa saved item.
- Câu hỏi nhiều ý hoặc clarification.
- Câu hỏi ngoài phạm vi/thiếu căn cứ.
- Health/live/ready và Swagger.
- Test report và evaluation report.

Mọi chức năng không thể chạy vì thiếu credential, provider, corpus hoặc route phải ghi `UNAVAILABLE`, kèm nguyên nhân. Không thay bằng ảnh placeholder và không chuyển lỗi vận hành thành kết quả nghiệp vụ đạt.
