# Kịch bản báo cáo khóa luận (12–15 phút)

Đề tài: **Hệ thống RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam**
SVTH: Quách Trường Phúc — 227060168 · GVHD: ThS. Nguyễn Chí Cường

Nguyên tắc nói: không đọc lại chữ trên slide; mỗi slide nói 1 phút; số liệu nói chính xác như trong quyển.
Tổng thời lượng mục tiêu: 12 phút nói + 5 phút demo + 5 phút câu hỏi.

---

## Slide 1 — Bìa (0:30)

Kính chào quý Thầy, Cô. Em là Quách Trường Phúc, lớp Công nghệ thông tin, thực hiện khóa luận với đề tài "Hệ thống RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam", dưới sự hướng dẫn của Thầy Nguyễn Chí Cường. Nội dung báo cáo gồm lý do chọn đề tài, cách hệ thống xử lý một câu hỏi, kết quả đo và hạn chế còn lại.

---

## Slide 2 — Vì sao cần hệ thống này (1:00)

Người dùng thường biết hành vi vi phạm nhưng không biết văn bản nào chứa quy định đó. Tra cứu trên web thì kết quả lẫn bài giải thích, bản sao và văn bản gốc, nên không biết đâu là nguồn chính thức và bản nào còn hiệu lực.

Với các trợ lý hội thoại phổ biến, ba hạn chế rõ nhất: mô hình trả lời từ dữ liệu đã huấn luyện nên có mốc kiến thức; chức năng tìm kiếm trên web không cho biết văn bản nào đang có hiệu lực; và cách dán văn bản luật vào từng lần hỏi thì lặp lại thao tác cho mỗi câu hỏi, lại vướng giới hạn số tệp đính kèm và độ dài ngữ cảnh của nền tảng.

Đề tài chọn cách giữ sẵn một kho văn bản đã chuẩn hóa, truy xuất theo câu hỏi rồi mới sinh câu trả lời, kèm vị trí pháp lý để người dùng mở lại kiểm tra.

---

## Slide 3 — Mục tiêu và phạm vi (0:50)

Mục tiêu là xây dựng hệ thống hỏi đáp tiếng Việt trên dữ liệu pháp luật giao thông cục bộ, câu trả lời đi kèm trích dẫn kiểm tra được, và từ chối khi không đủ căn cứ.

Phạm vi dữ liệu là 17 văn bản khai báo trong danh mục nguồn, sau khi chuẩn hóa thành 10.529 đoạn có vị trí Điều, Khoản, Điểm. Bộ đánh giá gồm 40 trường hợp chia thành 8 nhóm câu hỏi.

Em xin nói rõ: tập dữ liệu này phục vụ phạm vi thử nghiệm của đề tài, không đại diện cho toàn bộ pháp luật giao thông Việt Nam.

---

## Slide 4 — Kiến trúc xử lý một câu hỏi (1:30)

Đây là slide quan trọng nhất. Một câu hỏi đi qua năm bước.

Bước một, bộ phân tích dùng mô hình ngôn ngữ để tạo một câu hỏi độc lập đã tách khỏi ngữ cảnh, cùng tối đa ba truy vấn mở rộng. Lịch sử hội thoại chỉ dùng để giải nghĩa các từ thay thế.

Bước hai, mỗi truy vấn được tìm kiếm kết hợp trên Qdrant theo hai hướng: vector ngữ nghĩa và từ khóa BM25.

Bước ba, các danh sách kết quả được gộp bằng RRF, rồi bổ sung các đoạn cùng Điều hoặc tham chiếu liên quan.

Bước bốn, hệ thống kiểm tra căn cứ trước khi gọi mô hình sinh câu trả lời.

Bước năm, sau khi sinh, bước hậu kiểm đối chiếu trích dẫn với các đoạn đã truy xuất rồi mới trả kết quả về giao diện.

---

## Slide 5 — Dữ liệu và chỉ mục (1:00)

Dữ liệu đi theo một đường ống cố định: danh mục nguồn dạng JSON, rồi các tệp Markdown, rồi sinh ra các đoạn dạng JSONL, cuối cùng nạp vào Qdrant.

Điểm đáng chú ý: bộ tách văn bản nhận diện Điều, Khoản, Điểm và giữ nguyên số hiệu văn bản, nên mỗi đoạn đều biết mình thuộc văn bản nào, ở vị trí nào. Mỗi đoạn còn lưu tệp nguồn và mã băm SHA-256 của nội dung để phát hiện dữ liệu thay đổi.

Vì dữ liệu pháp luật nằm ngoài mô hình, khi cập nhật kho chỉ cần xây lại chỉ mục, không phải huấn luyện lại mô hình.

---

## Slide 6 — Truy xuất (1:00)

Vì sao phải kết hợp hai kiểu tìm kiếm: câu hỏi pháp luật có nhiều dạng. Có câu chỉ mô tả hành vi bằng ngôn ngữ đời thường, tìm kiếm ngữ nghĩa xử lý tốt. Có câu nêu thẳng số hiệu văn bản hoặc ký hiệu như "168/2024/NĐ-CP", trường hợp này BM25 bắt chính xác hơn.

Hai danh sách kết quả được gộp bằng RRF với k bằng 60, sau đó hệ thống giữ khoảng 12 đến 25 đoạn, tối đa 3 đoạn cho mỗi Điều hoặc Khoản để một vị trí không chiếm hết phần căn cứ.

Riêng câu hỏi có tham chiếu rõ ràng như "Điều 7 Khoản 3 Nghị định 168/2024", hệ thống nhận diện tham chiếu rồi lọc theo vị trí pháp lý, tránh trường hợp tìm được đoạn gần nghĩa nhưng sai Điều.

---

## Slide 7 — Kiểm soát căn cứ và hành vi từ chối (1:20)

Đây là phần em muốn nhấn mạnh vì nó quyết định độ an toàn của câu trả lời.

Trước khi sinh: câu hỏi ngoài phạm vi hoặc không có tài liệu phù hợp thì hệ thống từ chối, không gọi mô hình. Câu hỏi hỏi mức xử phạt nhưng chưa nêu hành vi thì hệ thống trả trạng thái yêu cầu làm rõ, thay vì đoán.

Sau khi sinh: bước hậu kiểm đối chiếu định danh nguồn, đoạn trích, hiệu lực theo thời điểm và cả mức tiền trong câu trả lời với các đoạn đã truy xuất; trích dẫn hoặc thông tin claim không khớp sẽ bị loại.

Với câu hỏi nhiều ý, hệ thống giữ lại phần trả lời có căn cứ và chỉ loại phần không khớp. Em cũng xin lưu ý bước hậu kiểm này kiểm tra dữ liệu gắn với câu trả lời, không thay thế việc đánh giá ngữ nghĩa toàn bộ nội dung.

---

## Slide 8 — Sản phẩm (0:50)

Sản phẩm gồm ba phần chính trên giao diện: hỏi đáp có trích dẫn, tra cứu nguồn pháp luật, và lịch sử hội thoại kèm nội dung đã lưu.

Từ mỗi trích dẫn, người dùng mở lại đúng Điều, Khoản, Điểm của văn bản nguồn để đối chiếu. Ngoài ra có gửi phản hồi và lưu câu trả lời; dữ liệu này gắn với tài khoản và được giới hạn theo người dùng.

Về công nghệ: FastAPI cho dịch vụ phía máy chủ, Qdrant cho chỉ mục, Supabase cho xác thực và dữ liệu ứng dụng, Next.js cùng React và TypeScript cho giao diện.

---

## Slide 9 — Cách đánh giá (1:00)

Bộ đánh giá gồm 40 trường hợp chia thành 8 nhóm: tham chiếu rõ ràng, diễn đạt tự nhiên, câu hỏi về mức phạt, câu hỏi nhiều ý, tham chiếu chéo, hỏi nối tiếp, thiếu căn cứ và ngoài phạm vi.

Chỉ số gồm: tìm đúng căn cứ trong top 5, độ chính xác ở mức văn bản, Điều, Khoản, Điểm, tỉ lệ trích dẫn hợp lệ, quyết định từ chối và độ trễ.

Hai điểm cần nói rõ về phương pháp. Thứ nhất, em dùng hai cách đối sánh: khớp chính xác và phân cấp — phân cấp cho phép một Khoản thuộc đúng Điều kỳ vọng được tính là tìm thấy căn cứ. Thứ hai, quyết định từ chối được đọc theo hai nhãn: nhãn vàng là kỳ vọng gốc, còn nhãn hiệu dụng xem việc từ chối là đúng khi điều khoản kỳ vọng không có trong kho dữ liệu.

---

## Slide 10 — Kết quả đo (1:20)

Lần chạy này dùng chung mô hình gemini-2.5-flash-lite cho bộ phân tích và bộ sinh, mô hình embedding qwen3-embedding-8b, chạy qua API với top_k bằng 5.

Kết quả chính: tỉ lệ tìm đúng căn cứ trong top 5 là 0,8182 theo đối sánh phân cấp và 0,4091 theo khớp chính xác, trên 22 trường hợp có căn cứ kỳ vọng. Độ chính xác ở mức văn bản 0,9091, mức Điều 0,8182, mức Khoản 0,7500. Tỉ lệ trích dẫn hợp lệ 1,0000 trên 32 trường hợp.

Về quyết định từ chối: F1 theo nhãn hiệu dụng là 0,9412 và theo nhãn vàng là 0,7692. Điểm đáng nói là trên 5 câu hỏi thiếu căn cứ, baseline trả lời cả 5, còn bản hiện tại từ chối đủ 5.

Độ trễ trung bình 8,70 giây và phân vị 95 là 13,61 giây, đã nằm dưới mục tiêu 15 giây.

---

## Slide 11 — Hạn chế và hướng phát triển (1:00)

Em xin nói thẳng các hạn chế. Thứ nhất, kho dữ liệu chỉ có 17 văn bản nên chưa bao phủ toàn bộ pháp luật giao thông. Thứ hai, chỉ số ở mức Điểm chỉ tính trên 3 trường hợp, quá ít để kết luận. Thứ ba, còn 2 câu hỏi nằm ngoài kho dữ liệu nhưng hệ thống vẫn trả lời từ các quy định liên quan, đây là điểm cần siết lại. Thứ tư, độ trễ với câu hỏi nhiều ý còn cao.

Hướng phát triển: thêm bộ xếp hạng lại và bộ lọc theo Điều, Khoản để nâng tỉ lệ tìm đúng căn cứ; mở rộng kho dữ liệu và cập nhật theo hiệu lực văn bản; và đi theo hướng tác tử nhiều bước cùng đồ thị quan hệ giữa các văn bản để xử lý tham chiếu liên văn bản.

---

## Slide 12 — Kết luận và demo (0:40)

Tóm lại, khóa luận đã xây dựng được một hệ thống hỏi đáp pháp luật giao thông trả lời từ kho văn bản đã chuẩn hóa, kèm vị trí pháp lý để người dùng kiểm tra lại; từ chối hoặc yêu cầu làm rõ khi thiếu căn cứ; và cập nhật dữ liệu bằng cách xây lại chỉ mục thay vì huấn luyện lại mô hình.

Em xin cảm ơn quý Thầy, Cô đã lắng nghe. Em sẵn sàng demo chương trình và trả lời câu hỏi.

---

## Chuẩn bị cho phần hỏi đáp

| Câu hỏi dễ gặp | Trả lời ngắn |
|---|---|
| Vì sao không dùng ChatGPT? | Mốc kiến thức, không xác thực được văn bản còn hiệu lực, và giới hạn tệp/ngữ cảnh khi dán tài liệu mỗi lần hỏi. |
| Vì sao cần hai cách đối sánh Hit@5? | Vì tọa độ kỳ vọng có cấp bậc: một Khoản thuộc đúng Điều vẫn là tìm thấy căn cứ. Hai cách cho hai con số khác nhau nên phải nói rõ cách nào. |
| Vì sao từ chối theo nhãn hiệu dụng cao hơn nhãn vàng? | 8 trường hợp ngoài kho dữ liệu vẫn giữ nhãn gốc yêu cầu trả lời; xét theo hiệu dụng thì từ chối mới đúng, nên F1 tăng. |
| Hệ thống có bịa không? | Trích dẫn dựng từ metadata nguồn, không do mô hình viết; hậu kiểm loại trích dẫn và claim không khớp; thiếu căn cứ thì từ chối. |
| Cập nhật văn bản mới thế nào? | Thêm vào danh mục nguồn, chạy lại bước tạo đoạn và xây lại chỉ mục; không huấn luyện lại mô hình. |
| Điểm mạnh so với tìm kiếm thường? | Trả lời kèm vị trí pháp lý, xử lý câu hỏi nhiều ý, và có quyết định từ chối thay vì đoán. |

## Checklist trước khi báo cáo

- [ ] Mở sẵn demo: backend và giao diện chạy, tài khoản đã đăng nhập.
- [ ] Chuẩn bị 3 câu hỏi demo: một câu mức phạt, một câu nêu Điều cụ thể, một câu ngoài phạm vi (để thấy từ chối).
- [ ] Kiểm tra lại số liệu trên slide 10 khớp với quyển (lần chạy 20260915T155418Z).
- [ ] Mở sẵn trang nguồn pháp luật để demo thao tác mở lại Điều/Khoản từ trích dẫn.
