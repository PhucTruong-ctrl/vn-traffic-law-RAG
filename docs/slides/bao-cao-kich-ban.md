# Kịch bản báo cáo khóa luận (12 phút nói + 5 phút demo + 5 phút hỏi đáp)

Đề tài: **Hệ thống RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam**
SVTH: Quách Trường Phúc — 227060168 · GVHD: ThS. Nguyễn Chí Cường

---

## Slide 1 — Bìa (0:30)

Dạ em chào các Thầy. Em là Quách Trường Phúc, sinh viên ngành Công nghệ thông tin.  
Khóa luận của em là "Hệ thống RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam",  
thực hiện dưới sự hướng dẫn của Thầy Nguyễn Chí Cường.

Báo cáo của em gồm bốn phần: lý do chọn đề tài, cách hệ thống xử lý một câu hỏi,
kết quả đo được, và những phần còn hạn chế. Sau đó em xin phép demo chương trình.

---

## Slide 2 — Vì sao cần hệ thống này (1:00)

Bài toán bắt đầu từ một tình huống quen thuộc: người dân biết về hành vi vi phạm của mình,
nhưng không biết quy định nằm ở văn bản nào. Tra trên web thì kết quả trộn lẫn với các bài giải thích,
bản sao và văn bản gốc, nên rất khó biết đâu là nguồn chính thức, và bản đó còn hiệu lực hay đã bị sửa.

Còn các công cụ AI phổ biến cũng không giải quyết được chuyện này. Mô hình trả lời
từ dữ liệu đã huấn luyện, nên có mốc kiến thức bị cắt và không theo kịp văn bản mới.
Khi bật tìm kiếm trên web, kết quả vẫn không cho biết văn bản nào đang có hiệu lực.
Cách cuối là dán văn bản luật vào mỗi câu hỏi, nhưng phải lặp lại thao tác,
mà các nền tảng đều giới hạn số tệp đính kèm và độ dài ngữ cảnh.

Hướng của đề tài này là giữ sẵn một kho văn bản đã chuẩn hóa. Hệ thống tìm trong kho đó trước,
rồi mới sinh câu trả lời, và luôn đính kèm vị trí Điều, Khoản, Điểm để người dùng mở lại kiểm tra.

---

## Slide 3 — Mục tiêu và phạm vi (0:50)

Mục tiêu của bài này là: hỏi đáp bằng tiếng Việt trên dữ liệu pháp luật cục bộ;
câu trả lời kèm trích dẫn; và từ chối khi không đủ căn cứ.

Về phạm vi, em dùng 17 văn bản luật lấy từ website chính phủ, và chuẩn hóa chúng thành 10.529 đoạn.
Bộ đánh giá có 40 trường hợp, chia thành 8 nhóm câu hỏi. Đây là phạm vi thử nghiệm,
không đại diện cho toàn bộ pháp luật giao thông.

---

## Slide 4 — Kiến trúc xử lý một câu hỏi (1:30)

Đầu tiên, mô hình ngôn ngữ đọc câu hỏi cùng ngữ cảnh hội thoại, rồi viết lại thành
một câu hỏi độc lập, kèm tối đa ba truy vấn mở rộng. Lịch sử hội thoại chỉ dùng để hiểu
các từ thay thế, ví dụ câu "còn xe máy thì sao" phải hiểu là đang hỏi tiếp câu trước.

Tiếp theo, mỗi truy vấn được tìm trên Qdrant theo hai hướng: vector ngữ nghĩa và từ khóa BM25.

Các danh sách kết quả sau đó được gộp lại bằng RRF, rồi bổ sung thêm các đoạn cùng Điều
và các tham chiếu liên quan.

Trước khi gọi mô hình để sinh ra câu trả lời, hệ thống kiểm tra xem có căn cứ phù hợp hay không.

Cuối cùng, sau khi mô hình viết xong, bước hậu kiểm đối chiếu trích dẫn với các đoạn
đã tìm được, rồi mới trả kết quả về giao diện.

---

## Slide 5 — Dữ liệu và chỉ mục (1:00)

Dữ liệu đi theo một đường cố định: từ danh mục nguồn dạng JSON, sang các tệp Markdown,
sinh ra các đoạn JSONL, rồi nạp vào Qdrant.

Bộ tách văn bản nhận diện Điều, Khoản, Điểm và giữ nguyên số hiệu văn bản, nên mỗi đoạn
đều biết mình thuộc văn bản nào và ở vị trí nào. Mỗi đoạn cũng lưu tệp nguồn và mã băm SHA-256
để phát hiện khi nội dung thay đổi.

Vì dữ liệu pháp luật nằm ngoài mô hình, khi cập nhật kho em chỉ cần chạy lại bước tạo đoạn
và xây lại chỉ mục, không phải huấn luyện lại mô hình.

---

## Slide 6 — Truy xuất (1:00)

Câu hỏi pháp luật có nhiều dạng, nên em dùng hai kiểu tìm kiếm. Câu hỏi diễn đạt đời thường
thì tìm kiếm ngữ nghĩa xử lý tốt. Câu hỏi nêu số hiệu văn bản hoặc ký hiệu như 168/2024/NĐ-CP
thì BM25 bắt chính xác hơn.

Hai danh sách kết quả được gộp bằng RRF với k bằng 60. Sau đó hệ thống giữ khoảng 12 đến 25 đoạn,
tối đa 3 đoạn cho mỗi Điều hoặc Khoản, để một vị trí không chiếm hết phần căn cứ.

Với câu hỏi có tham chiếu rõ như "Điều 7 Khoản 3 Nghị định 168/2024", hệ thống nhận diện
tham chiếu rồi lọc theo vị trí pháp lý. Cách này tránh trường hợp tìm được đoạn gần nghĩa
nhưng sai Điều.

---

## Slide 7 — Kiểm soát căn cứ (1:20)

Phần này quyết định câu trả lời có an toàn hay không, nên em chia làm hai giai đoạn.

Trước khi sinh câu trả lời: nếu câu hỏi nằm ngoài phạm vi, hoặc không có tài liệu phù hợp,
hệ thống từ chối và không gọi mô hình. Nếu câu hỏi hỏi mức xử phạt mà chưa nêu hành vi,
hệ thống trả về trạng thái yêu cầu làm rõ, chứ không đoán.

Sau khi sinh: bước hậu kiểm so lại định danh nguồn, đoạn trích, hiệu lực theo thời điểm
và cả mức tiền xuất hiện trong câu trả lời. Trích dẫn hoặc thông tin claim nào không khớp
thì bị loại.

Với câu hỏi nhiều ý, hệ thống giữ phần trả lời có căn cứ và bỏ phần không khớp.
Bước hậu kiểm kiểm tra dữ liệu gắn với câu trả lời; nó không thay thế việc đánh giá
ngữ nghĩa toàn bộ nội dung.

---

## Slide 8 — Sản phẩm (0:50)

Giao diện có ba phần: hỏi đáp, tra cứu nguồn pháp luật, và lịch sử hội thoại kèm nội dung đã lưu.

Từ một trích dẫn, người dùng mở lại đúng Điều, Khoản, Điểm của văn bản nguồn để đối chiếu.
Người dùng cũng gửi được phản hồi và lưu câu trả lời; dữ liệu này gắn với tài khoản
và chỉ người đó đọc được.

Công nghệ dùng trong hệ thống: FastAPI cho dịch vụ máy chủ, Qdrant cho chỉ mục,
Supabase cho xác thực và dữ liệu ứng dụng, Next.js với React và TypeScript cho giao diện.

---

## Slide 9 — Cách đánh giá (1:00)

Bộ đánh giá có 40 trường hợp, chia thành 8 nhóm: câu hỏi nêu tham chiếu rõ, câu hỏi diễn đạt
tự nhiên, câu hỏi về mức phạt, câu hỏi nhiều ý, câu hỏi cần tham chiếu chéo, câu hỏi nối tiếp,
trường hợp thiếu căn cứ và trường hợp ngoài phạm vi.

Hệ thống được đo bằng các chỉ số: tìm đúng căn cứ trong top 5, độ chính xác ở mức văn bản,
Điều, Khoản, Điểm, tỉ lệ trích dẫn hợp lệ, quyết định từ chối và độ trễ.

Có hai điểm về cách đo mà em muốn nói trước, vì phần kết quả sẽ nhắc lại.
Thứ nhất, tìm đúng căn cứ được đối sánh theo hai cách: khớp chính xác và phân cấp.
Cách phân cấp cho phép một Khoản nằm đúng trong Điều kỳ vọng vẫn được tính là tìm thấy căn cứ.
Thứ hai, quyết định từ chối được đọc theo hai bộ nhãn: nhãn vàng là kỳ vọng gốc,
còn nhãn hiệu dụng xem việc từ chối là đúng khi điều khoản kỳ vọng không có trong kho dữ liệu.

---

## Slide 10 — Kết quả đo (1:20)

Kết quả em trình bày ở đây là lần chạy ngày 15 tháng 9, dùng chung mô hình gemini-2.5-flash-lite
cho bộ phân tích và bộ sinh, mô hình embedding qwen3-embedding-8b, chạy qua API với top_k bằng 5.

Tỉ lệ tìm đúng căn cứ trong top 5 là 0,8182 theo đối sánh phân cấp, và 0,4091 theo khớp chính xác,
trên 22 trường hợp có căn cứ kỳ vọng. *(dừng)* Độ chính xác ở mức văn bản là 0,9091,
mức Điều 0,8182, mức Khoản 0,7500. Tỉ lệ trích dẫn hợp lệ là 1,0000 trên 32 trường hợp.

Về quyết định từ chối, F1 theo nhãn hiệu dụng là 0,9412 và theo nhãn vàng là 0,7692.
Bản baseline trả lời cả 5 câu hỏi thiếu căn cứ; bản hiện tại từ chối đủ cả 5.

Độ trễ trung bình là 8,70 giây, phân vị 95 là 13,61 giây, đã thấp hơn mục tiêu 15 giây.

---

## Slide 11 — Hạn chế và hướng phát triển (1:00)

Em nêu bốn hạn chế. Kho dữ liệu chỉ có 17 văn bản nên chưa bao phủ toàn bộ pháp luật giao thông.
Chỉ số ở mức Điểm chỉ tính trên 3 trường hợp, quá ít để kết luận. Còn 2 câu hỏi nằm ngoài kho dữ liệu
mà hệ thống vẫn trả lời từ các quy định liên quan, đây là chỗ cần siết lại.
Và độ trễ với câu hỏi nhiều ý còn cao.

Hướng phát triển gồm ba việc: thêm bộ xếp hạng lại và bộ lọc theo Điều, Khoản để nâng
tỉ lệ tìm đúng căn cứ; mở rộng kho dữ liệu và cập nhật theo hiệu lực văn bản; và đi theo hướng
tác tử nhiều bước cùng đồ thị quan hệ giữa các văn bản để xử lý tham chiếu liên văn bản.

---

## Slide 12 — Kết luận (0:40)

Khóa luận đã hoàn thành ba việc: trả lời từ kho văn bản đã chuẩn hóa và kèm vị trí pháp lý
để người dùng kiểm tra lại; từ chối hoặc yêu cầu làm rõ khi thiếu căn cứ; và cập nhật dữ liệu
bằng cách xây lại chỉ mục, không huấn luyện lại mô hình.

Em xin cảm ơn quý Thầy Cô. Em sẵn sàng demo chương trình và trả lời câu hỏi.

---

## Chuẩn bị cho phần hỏi đáp


| Câu hỏi dễ gặp                                           | Trả lời ngắn                                                                                                                                                                                                         |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Vì sao không dùng ChatGPT?                               | Mô hình trả lời từ dữ liệu đã huấn luyện nên có mốc kiến thức; tìm kiếm web không cho biết văn bản nào còn hiệu lực; dán tài liệu mỗi lần hỏi thì lặp thao tác và vướng giới hạn tệp, ngữ cảnh.                      |
| Vì sao cần hai cách đối sánh Hit@5?                      | Vì tọa độ kỳ vọng có cấp bậc. Một Khoản nằm đúng trong Điều kỳ vọng vẫn là tìm thấy căn cứ, nên cách phân cấp tính là đạt, còn khớp chính xác thì không. Hai cách cho hai con số nên phải nói rõ đang dùng cách nào. |
| Vì sao F1 từ chối theo nhãn hiệu dụng cao hơn nhãn vàng? | Tám trường hợp ngoài kho dữ liệu vẫn giữ nhãn gốc yêu cầu trả lời, nên khi hệ thống từ chối thì bị tính là sai. Xét theo hiệu dụng, điều khoản kỳ vọng không có trong kho thì từ chối mới đúng, nên F1 tăng.         |
| Hệ thống có bịa câu trả lời không?                       | Trích dẫn dựng từ metadata của đoạn đã truy xuất, không để mô hình tự viết. Hậu kiểm loại trích dẫn và claim không khớp; không đủ căn cứ thì từ chối.                                                                |
| Cập nhật văn bản mới thế nào?                            | Thêm vào danh mục nguồn, chạy lại bước tạo đoạn rồi xây lại chỉ mục. Không huấn luyện lại mô hình.                                                                                                                   |
| Khác gì so với tìm kiếm thường?                          | Trả lời kèm vị trí pháp lý để mở lại kiểm tra, xử lý được câu hỏi nhiều ý, và có quyết định từ chối thay vì đoán.                                                                                                    |
| Sao không dùng reranker ngay từ đầu?                     | Reranker cần thêm một lượt gọi mô hình cho mỗi truy vấn, làm tăng độ trễ và chi phí; em để lại cho vòng cải thiện sau khi đã có số liệu nền.                                                                         |


## Checklist trước khi báo cáo

- [ ] Mở sẵn demo: dịch vụ máy chủ và giao diện đang chạy, tài khoản đã đăng nhập.
- [ ] Chuẩn bị 3 câu hỏi demo: một câu hỏi mức phạt, một câu nêu số Điều cụ thể,

  một câu ngoài phạm vi để thấy hệ thống từ chối.
- [ ] Mở sẵn trang nguồn pháp luật để demo thao tác mở lại Điều, Khoản từ trích dẫn.
- [ ] Đối chiếu số trên slide 10 với quyển: lần chạy 20260915T155418Z.
- [ ] Thử bấm giờ một lượt, giữ tổng phần nói trong khoảng 12 phút.

