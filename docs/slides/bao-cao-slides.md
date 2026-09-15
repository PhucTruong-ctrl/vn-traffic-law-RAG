# Slide báo cáo khóa luận — 12 slide

Đề tài: **Hệ thống RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam**
Người thực hiện: Quách Trường Phúc — 227060168 · GVHD: ThS. Nguyễn Chí Cường

Nguyên tắc trình bày: mỗi slide một ý, tối đa 5 dòng chữ, không đọc nguyên văn slide.
Chữ tối thiểu 20pt; mỗi slide chỉ nên có 1 sơ đồ hoặc 1 bảng nhỏ.

---

## Slide 1 — Bìa

```
┌────────────────────────────────────────────────────────────┐
│  TRƯỜNG ĐẠI HỌC TÂY ĐÔ — KHOA KỸ THUẬT CÔNG NGHỆ           │
│                                                            │
│        HỆ THỐNG RAG HỖ TRỢ TRA CỨU                         │
│        PHÁP LUẬT GIAO THÔNG VIỆT NAM                       │
│                                                            │
│        SVTH : Quách Trường Phúc — 227060168                │
│        GVHD : ThS. Nguyễn Chí Cường                        │
│        Cần Thơ, tháng 09 năm 2026                          │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 2 — Vì sao cần hệ thống này

```
┌────────────────────────────────────────────────────────────┐
│  VÌ SAO CẦN HỆ THỐNG NÀY                                   │
│                                                            │
│  ✗ Trợ lý hội thoại chung: có mốc kiến thức, không xác     │
│    thực được văn bản nào còn hiệu lực                      │
│  ✗ Dán văn bản luật vào từng câu hỏi: lặp lại, vướng giới  │
│    hạn tệp đính kèm và độ dài ngữ cảnh                     │
│  ✓ Kho văn bản cố định + truy xuất trước khi trả lời       │
│  ✓ Mỗi câu trả lời kèm Điều/Khoản/Điểm để mở lại kiểm tra  │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 3 — Mục tiêu và phạm vi

```
┌────────────────────────────────────────────────────────────┐
│  MỤC TIÊU VÀ PHẠM VI                                       │
│                                                            │
│  Mục tiêu                                                  │
│   • Hỏi đáp tiếng Việt trên dữ liệu pháp luật cục bộ       │
│   • Trả lời kèm trích dẫn kiểm tra lại được                │
│   • Từ chối khi không đủ căn cứ                            │
│                                                            │
│  Phạm vi                                                   │
│   • 17 văn bản, 10.529 đoạn đã chuẩn hóa                   │
│   • Bộ đánh giá 40 trường hợp / 8 nhóm câu hỏi             │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 4 — Kiến trúc xử lý một câu hỏi

```
┌─────────────────────────────────────────────────────────────┐
│  KIẾN TRÚC XỬ LÝ MỘT CÂU HỎI                                │
│                                                             │
│  Câu hỏi ──▶ Phân tích (LLM)                                │
│              │  câu hỏi độc lập + tối đa 3 truy vấn mở rộng │
│              ▼                                              │
│            Tìm kiếm kết hợp (Qdrant: ngữ nghĩa + BM25)      │
│              ▼                                              │
│            Gộp thứ hạng RRF  ──▶  bổ sung Điều liên quan    │
│              ▼                                              │
│            Kiểm tra căn cứ  ──▶  Sinh câu trả lời           │
│              ▼                                              │
│            Hậu kiểm trích dẫn ──▶ Câu trả lời / Từ chối     │
└─────────────────────────────────────────────────────────────┘
```

---

## Slide 5 — Dữ liệu và chỉ mục

```
┌────────────────────────────────────────────────────────────┐
│  DỮ LIỆU VÀ CHỈ MỤC                                        │
│                                                            │
│  Danh mục nguồn (JSON) ──▶ Markdown ──▶ JSONL ──▶ Qdrant   │
│                                                            │
│   • Tách theo Điều / Khoản / Điểm, giữ nguyên số hiệu      │
│   • Mỗi đoạn lưu vị trí pháp lý + tệp nguồn + mã SHA-256   │
│   • Chỉ mục gồm vector ngữ nghĩa và vector từ khóa (BM25)  │
│   • Cập nhật kho = xây lại chỉ mục, không huấn luyện lại   │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 6 — Truy xuất: kết hợp và tra cứu chính xác

```
┌────────────────────────────────────────────────────────────┐
│  TRUY XUẤT                                                 │
│                                                            │
│  Hai kiểu tìm kiếm chạy song song                          │
│   • Ngữ nghĩa: câu hỏi diễn đạt đời thường                 │
│   • Từ khóa (BM25): số hiệu văn bản, cụm từ pháp lý        │
│                                                            │
│  Gộp bằng RRF, k = 60; giữ 12–25 đoạn, tối đa 3 đoạn/Điều  │
│                                                            │
│  Câu hỏi nêu thẳng "Điều 7 Nghị định 168/2024"             │
│   → nhận diện tham chiếu và lọc theo vị trí pháp lý        │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 7 — Kiểm soát căn cứ và hành vi từ chối

```
┌────────────────────────────────────────────────────────────┐
│  KIỂM SOÁT CĂN CỨ                                          │
│                                                            │
│  Trước khi sinh câu trả lời                                │
│   • Ngoài phạm vi / không có căn cứ  → từ chối             │
│   • Hỏi mức phạt nhưng chưa nêu hành vi → yêu cầu làm rõ   │
│                                                            │
│  Sau khi sinh                                              │
│   • Đối chiếu định danh nguồn, đoạn trích, hiệu lực,       │
│     mức tiền với các đoạn đã truy xuất                     │
│   • Trích dẫn hoặc claim không khớp bị loại                │
│   • Câu hỏi nhiều ý: giữ phần có căn cứ, loại phần còn lại │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 8 — Sản phẩm: giao diện và chức năng

```
┌────────────────────────────────────────────────────────────┐
│  SẢN PHẨM                                                  │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Hỏi đáp     │  │ Nguồn pháp   │  │ Lịch sử +    │      │
│  │  có trích dẫn│  │ luật         │  │ nội dung lưu │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                            │
│   • Mở lại đúng Điều/Khoản/Điểm từ trích dẫn               │
│   • Phản hồi và lưu câu trả lời; dữ liệu giới hạn theo user│
│   • FastAPI · Qdrant · Supabase · Next.js/React/TypeScript │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 9 — Cách đánh giá

```
┌────────────────────────────────────────────────────────────┐
│  CÁCH ĐÁNH GIÁ                                             │
│                                                            │
│  40 trường hợp / 8 nhóm: tham chiếu rõ, diễn đạt tự nhiên, │
│  mức phạt, nhiều ý, tham chiếu chéo, hỏi nối tiếp,         │
│  thiếu căn cứ, ngoài phạm vi                               │
│                                                            │
│  Chỉ số: tìm đúng căn cứ (2 cách đối sánh), tọa độ pháp lý │
│  (văn bản/Điều/Khoản/Điểm), trích dẫn hợp lệ, quyết định   │
│  từ chối, độ trễ                                           │
│                                                            │
│  Quyết định từ chối đọc theo 2 nhãn: nhãn vàng và nhãn     │
│  hiệu dụng (điều khoản không có trong kho thì nên từ chối) │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 10 — Kết quả đo

```
┌────────────────────────────────────────────────────────────┐
│  KẾT QUẢ (lần chạy 20260915T155418Z)                       │
│                                                            │
│  Tìm đúng căn cứ trong top 5                               │
│    • đối sánh phân cấp     0,8182  (n = 22)                │
│    • khớp chính xác        0,4091  (n = 22)                │
│  Tọa độ pháp lý: văn bản 0,9091 · Điều 0,8182 ·            │
│                  Khoản 0,7500 · Điểm 0,0000 (n = 3)        │
│  Trích dẫn hợp lệ          1,0000  (n = 32)                │
│  Từ chối: F1 hiệu dụng 0,9412 · F1 nhãn vàng 0,7692        │
│  Độ trễ: trung bình 8,70 s · p95 13,61 s (dưới mục tiêu)   │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 11 — Hạn chế và hướng phát triển

```
┌────────────────────────────────────────────────────────────┐
│  HẠN CHẾ VÀ HƯỚNG PHÁT TRIỂN                               │
│                                                            │
│  Hạn chế                                                   │
│   • 17 văn bản: chưa bao phủ toàn bộ pháp luật giao thông  │
│   • Chỉ số mức Điểm tính trên 3 trường hợp                 │
│   • 2 câu ngoài kho dữ liệu vẫn được trả lời               │
│   • Độ trễ còn cao với câu hỏi nhiều ý                     │
│                                                            │
│  Hướng phát triển                                          │
│   • Thêm bộ xếp hạng lại và lọc theo Điều/Khoản            │
│   • Mở rộng kho dữ liệu, cập nhật theo hiệu lực văn bản    │
│   • Tác tử nhiều bước, đồ thị quan hệ văn bản (GraphRAG)   │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 12 — Kết luận và demo

```
┌────────────────────────────────────────────────────────────┐
│  KẾT LUẬN                                                  │
│                                                            │
│   • Hệ thống trả lời từ kho văn bản đã chuẩn hóa, kèm vị   │
│     trí pháp lý để kiểm tra lại                            │
│   • Từ chối hoặc yêu cầu làm rõ khi thiếu căn cứ           │
│   • Cập nhật dữ liệu bằng cách xây lại chỉ mục             │
│                                                            │
│  XIN CẢM ƠN — SẴN SÀNG DEMO VÀ TRẢ LỜI CÂU HỎI             │
└────────────────────────────────────────────────────────────┘
```

---

## Ghi chú khi dựng slide

- 12 slide cho 12–15 phút: khoảng 1 phút/slide, để 3–5 phút demo ở cuối.
- Slide 4, 6, 7 nên vẽ lại thành sơ đồ khối thật (dùng hình trong báo cáo), không cần chữ nhiều.
- Slide 10 chỉ nên có 5 dòng số; chi tiết để phần trả lời câu hỏi.
- Nhất quán với quy định trình bày của Khoa: số thập phân dùng dấu phẩy, tên bảng/hình viết hoa chữ đầu khi nhắc trong bài nói.
