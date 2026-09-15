# Kịch bản demo (khoảng 5 phút)

Đi theo đúng luồng sử dụng của giao diện: trang đầu → đăng nhập → hỏi đáp → mở nguồn trích dẫn
→ lịch sử và nội dung đã lưu → phản hồi. Cuối cùng là kiểm tra dịch vụ nếu hội đồng hỏi thêm.

Số liệu trong bảng dưới đây là kết quả chạy thật trên hệ thống đang chạy, không phải số dự kiến.
Thời gian mỗi câu từ 2,5 đến 14 giây, nên khi hệ thống đang xử lý thì nói tiếp phần đang chạy
(thanh tiến trình hiện ba bước: đang tìm căn cứ, đang đối chiếu nguồn, đang soạn câu trả lời).

---

## Chuẩn bị trước khi vào phòng

- Dịch vụ máy chủ đang chạy, giao diện mở sẵn ở tab đầu tiên, đã đăng nhập bằng tài khoản demo.
- Mở sẵn tab thứ hai ở trang nguồn pháp luật để chuyển qua lại nhanh.
- Cỡ chữ trình duyệt tăng lên 110–125% để hội đồng đọc được trích dẫn.
- Kiểm tra mạng và thử trước một câu hỏi để chắc mô hình phản hồi.

---

## Bước 1 — Trang đầu (0:20)

Mở trang chủ, chỉ vào phần giới thiệu và ô hỏi đáp.

Lời nói: "Đây là trang đầu của hệ thống. Người dùng đăng nhập, rồi đặt câu hỏi
ở ô nhập. Hệ thống trả lời dựa trên kho văn bản pháp luật đã chuẩn hóa, không tra web."

---

## Bước 2 — Đăng ký và đăng nhập (0:20)

Nếu đã đăng nhập sẵn thì chỉ nói qua: tài khoản tạo bằng Supabase Auth, dữ liệu hội thoại
và nội dung lưu gắn với tài khoản đó, mỗi người chỉ đọc được dữ liệu của mình.

Nếu muốn demo đăng ký thì đăng ký một tài khoản mới bằng email tạm, rồi đăng nhập lại.

---

## Bước 3 — Hỏi đáp có trích dẫn (1:30)

Vào trang chat, hỏi lần lượt ba câu đầu trong bảng. Ba câu này đi theo một mạch:
câu mức phạt, câu nêu số Điều, rồi câu hỏi nối tiếp.

| # | Câu hỏi | Trạng thái | Trích dẫn | Thời gian |
|---|---|---|---|---|
| 1 | Đi xe máy không đội mũ bảo hiểm bị phạt thế nào? | VERIFIED | 7 | 10,6 s |
| 2 | Ô tô vượt đèn đỏ bị phạt bao nhiêu? | VERIFIED | 2 | 8,6 s |
| 3 | Còn xe máy thì sao? (hỏi tiếp trong cùng phiên) | VERIFIED | 11 | 13,4 s |
| 4 | Điều 7 Khoản 3 Nghị định 168/2024 quy định gì? | VERIFIED | 3 | 6,2 s |
| 5 | Xe máy vừa vượt đèn đỏ vừa chở 3 người thì bị phạt sao? | VERIFIED | 1 | 14,0 s |
| 6 | Thời tiết Hà Nội ngày mai thế nào? | OUT_OF_SCOPE | 0 | 2,7 s |
| 7 | Mức phạt là bao nhiêu? | INSUFFICIENT_EVIDENCE, lý do `clarification_required` | 0 | 2,5 s |

Lời nói khi câu 1 đang chạy: "Hệ thống đang phân tích câu hỏi, tìm căn cứ theo hai hướng
là ngữ nghĩa và từ khóa, rồi mới gọi mô hình viết câu trả lời."

Sau khi có kết quả, chỉ vào phần trích dẫn: "Mỗi trích dẫn ghi văn bản, Điều, Khoản, Điểm
và đoạn trích ngắn. Phần này lấy từ dữ liệu đã lưu, không để mô hình tự viết."

Với câu 2 và câu 3: nhấn mạnh đây là hỏi nối tiếp trong cùng một phiên, nên hệ thống hiểu
"còn xe máy thì sao" là đang so với ô tô ở câu trước.

---

## Bước 4 — Hai trường hợp đáng chú ý (0:50)

Câu 6: hỏi câu ngoài phạm vi. Hệ thống trả về trạng thái ngoài phạm vi, không trích dẫn,
xử lý trong 2,7 giây vì không gọi mô hình.

Lời nói: "Câu này không thuộc phạm vi pháp luật giao thông, nên hệ thống từ chối ngay
thay vì trả lời theo suy đoán."

Câu 7: hỏi mức phạt mà không nêu hành vi. Hệ thống trả về trạng thái thiếu căn cứ
với lý do yêu cầu làm rõ.

Lời nói: "Câu hỏi thiếu hành vi vi phạm nên hệ thống yêu cầu làm rõ, không tự chọn một hành vi
để trả lời."

---

## Bước 5 — Mở nguồn từ trích dẫn (0:40)

Bấm vào một trích dẫn ở câu 1, để hệ thống mở đúng văn bản và đúng vị trí Điều, Khoản, Điểm
trong trang nguồn pháp luật.

Lời nói: "Từ trích dẫn, người dùng mở lại được văn bản gốc để tự đối chiếu.
Đây là phần em muốn hội đồng kiểm tra trực tiếp."

---

## Bước 6 — Trang nguồn pháp luật (0:40)

Chuyển sang tab nguồn pháp luật. Làm hai thao tác: xem danh sách văn bản, rồi gõ một từ khóa
hoặc số hiệu vào ô tìm kiếm; sau đó mở chi tiết một văn bản để thấy nội dung đã chuẩn hóa
theo Điều, Khoản, Điểm.

Lời nói: "Kho dữ liệu hiện có 17 văn bản, chuẩn hóa thành 10.529 đoạn. Trang này cho phép
tra cứu độc lập, không cần hỏi đáp."

---

## Bước 7 — Lịch sử hội thoại (0:30)

Mở thanh bên, chỉ vào danh sách phiên hội thoại. Đổi tên phiên vừa chat để thấy thao tác lưu tên.
Nếu muốn, xóa mềm một phiên cũ để thấy phiên biến khỏi danh sách nhưng dữ liệu vẫn còn.

Lời nói: "Mỗi phiên lưu lại câu hỏi, câu trả lời và trích dẫn, nên người dùng xem lại được
toàn bộ quá trình tra cứu."

---

## Bước 8 — Lưu câu trả lời và trang nội dung đã lưu (0:30)

Ở câu trả lời của câu 1, bấm nút lưu. Sau đó mở mục nội dung đã lưu ở thanh bên để thấy
câu hỏi và câu trả lời được giữ nguyên, kèm trích dẫn.

Lời nói: "Nội dung lưu giữ cả câu hỏi, câu trả lời và trích dẫn, nên vẫn xem được
kể cả khi phiên hội thoại gốc đã bị xóa."

---

## Bước 9 — Phản hồi (0:20)

Bấm nút thích hoặc không thích ở câu trả lời. Nói rằng đánh giá được lưu theo tin nhắn
và theo tài khoản, dùng làm dữ liệu cho vòng cải thiện sau này.

---

## Bước 10 — Kiểm tra dịch vụ và tài liệu API (0:20, chỉ khi hội đồng hỏi)

Mở địa chỉ kiểm tra trạng thái dịch vụ, cho thấy Supabase và Qdrant đều kết nối được.
Nếu cần, mở trang tài liệu API do FastAPI sinh tự động để chỉ danh sách điểm cuối dịch vụ.

---

## Khi có sự cố

| Tình huống | Cách xử lý |
|---|---|
| Câu hỏi chạy quá 20 giây | Nói: "câu này đang chờ dịch vụ mô hình, em xin chuyển sang câu khác" rồi hỏi câu 4 hoặc câu 6 (nhanh hơn). |
| Mô hình trả lỗi hoặc hết hạn mức | Hỏi lại câu 6 để cho thấy phần từ chối vẫn chạy, vì nhánh này không gọi mô hình. |
| Mất mạng | Dùng ảnh chụp màn hình đã chuẩn bị sẵn cho các bước 3 đến 8, nói theo kịch bản. |
| Hội đồng hỏi số liệu chi tiết | Mở slide 10 và quyển báo cáo, mục Đánh giá khả năng tra cứu và trả lời. |

---

## Checklist trước khi demo

- [ ] Dịch vụ máy chủ và giao diện đang chạy, đã đăng nhập.
- [ ] Hai tab mở sẵn: trang chat và trang nguồn pháp luật.
- [ ] Đã thử câu 1 để chắc mô hình phản hồi.
- [ ] Ảnh chụp màn hình dự phòng cho các bước 3 đến 8.
- [ ] Thử bấm giờ một lượt demo, giữ trong khoảng 5 phút.
