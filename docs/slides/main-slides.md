# Slide báo cáo khóa luận — 12 slide

Đề tài: **Hệ thống RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam**
Quách Trường Phúc — 227060168 · GVHD: ThS. Nguyễn Chí Cường

Mỗi slide một ý, tối đa 5 dòng chữ, chữ tối thiểu 20pt. Không đọc lại chữ trên slide.
Slide 4, 6, 7 khi dựng thật thì thay khung chữ bằng hình vẽ lấy từ quyển báo cáo.

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
│  Người dân biết hành vi, không biết quy định ở văn bản nào │
│  Tra web: lẫn bài giải thích, bản sao và văn bản gốc       │
│  Trợ lý chung: có mốc kiến thức; tìm web không xác thực    │
│  Dán tài liệu mỗi câu hỏi: lặp thao tác, vướng giới hạn    │
│                                                            │
│  Kho văn bản cố định + truy xuất trước khi trả lời         │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 3 — Mục tiêu và phạm vi

```
┌────────────────────────────────────────────────────────────┐
│  MỤC TIÊU VÀ PHẠM VI                                       │
│                                                            │
│  Hỏi đáp tiếng Việt trên dữ liệu pháp luật cục bộ          │
│  Trả lời kèm trích dẫn kiểm tra lại được                   │
│  Từ chối khi không đủ căn cứ                               │
│                                                            │
│  17 văn bản · 10.529 đoạn · 40 trường hợp / 8 nhóm         │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 4 — Kiến trúc xử lý một câu hỏi

```
┌────────────────────────────────────────────────────────────┐
│  KIẾN TRÚC XỬ LÝ MỘT CÂU HỎI                               │
│                                                            │
│  Câu hỏi ──▶ Phân tích: câu hỏi độc lập                    │
│              + tối đa 3 truy vấn mở rộng                   │
│              ▼                                             │
│            Tìm kiếm kết hợp: ngữ nghĩa + BM25              │
│              ▼                                             │
│            Gộp RRF ──▶ bổ sung Điều liên quan              │
│              ▼                                             │
│            Kiểm tra căn cứ ──▶ Sinh câu trả lời            │
│              ▼                                             │
│            Hậu kiểm trích dẫn ──▶ Trả lời / Từ chối        │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 5 — Dữ liệu và chỉ mục

```
┌────────────────────────────────────────────────────────────┐
│  DỮ LIỆU VÀ CHỈ MỤC                                        │
│                                                            │
│  Danh mục nguồn ──▶ Markdown ──▶ JSONL ──▶ Qdrant          │
│                                                            │
│  Tách theo Điều / Khoản / Điểm, giữ nguyên số hiệu         │
│  Mỗi đoạn lưu vị trí pháp lý, tệp nguồn, mã SHA-256        │
│  Chỉ mục gồm vector ngữ nghĩa và vector từ khóa            │
│                                                            │
│  Cập nhật kho = xây lại chỉ mục, không huấn luyện lại      │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 6 — Truy xuất

```
┌────────────────────────────────────────────────────────────┐
│  TRUY XUẤT                                                 │
│                                                            │
│  Ngữ nghĩa: câu hỏi diễn đạt đời thường                    │
│  BM25: số hiệu văn bản, cụm từ pháp lý                     │
│  Gộp RRF với k = 60                                        │
│  Giữ 12–25 đoạn, tối đa 3 đoạn cho mỗi Điều/Khoản          │
│                                                            │
│  "Điều 7 Nghị định 168/2024" → lọc theo vị trí pháp lý     │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 7 — Kiểm soát căn cứ

```
┌────────────────────────────────────────────────────────────┐
│  KIỂM SOÁT CĂN CỨ                                          │
│                                                            │
│  Trước khi sinh                                            │
│    Ngoài phạm vi, không có căn cứ  →  từ chối              │
│    Hỏi mức phạt, chưa nêu hành vi  →  yêu cầu làm rõ       │
│                                                            │
│  Sau khi sinh                                              │
│    Đối chiếu định danh nguồn, đoạn trích, hiệu lực,        │
│    mức tiền với các đoạn đã truy xuất                      │
│    Trích dẫn hoặc claim không khớp  →  loại                │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 8 — Sản phẩm

```
┌────────────────────────────────────────────────────────────┐
│  SẢN PHẨM                                                  │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Hỏi đáp     │  │ Nguồn pháp   │  │ Lịch sử và   │      │
│  │  có trích dẫn│  │ luật         │  │ nội dung lưu │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                            │
│  Mở lại đúng Điều/Khoản/Điểm từ trích dẫn                  │
│  Phản hồi, lưu câu trả lời; dữ liệu giới hạn theo tài khoản│
│  FastAPI · Qdrant · Supabase · Next.js · React · TypeScript│
└────────────────────────────────────────────────────────────┘
```

---

## Slide 9 — Cách đánh giá

```
┌────────────────────────────────────────────────────────────┐
│  CÁCH ĐÁNH GIÁ                                             │
│                                                            │
│  40 trường hợp, 8 nhóm: tham chiếu rõ, diễn đạt tự nhiên,  │
│  mức phạt, nhiều ý, tham chiếu chéo, hỏi nối tiếp,         │
│  thiếu căn cứ, ngoài phạm vi                               │
│                                                            │
│  Chỉ số: tìm đúng căn cứ, tọa độ văn bản/Điều/Khoản/Điểm,  │
│  trích dẫn hợp lệ, quyết định từ chối, độ trễ              │
│                                                            │
│  Tìm đúng căn cứ: đối sánh phân cấp và khớp chính xác      │
│  Từ chối: đọc theo nhãn vàng và nhãn hiệu dụng             │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 10 — Kết quả đo

```
┌────────────────────────────────────────────────────────────┐
│  KẾT QUẢ — lần chạy 20260915T155418Z                       │
│                                                            │
│  Tìm đúng căn cứ trong top 5                               │
│    phân cấp 0,8182  ·  khớp chính xác 0,4091  (n = 22)     │
│  Tọa độ: văn bản 0,9091 · Điều 0,8182 · Khoản 0,7500       │
│  Trích dẫn hợp lệ 1,0000  (n = 32)                         │
│  Từ chối: F1 hiệu dụng 0,9412 · F1 nhãn vàng 0,7692        │
│  Độ trễ: trung bình 8,70 s · p95 13,61 s                   │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 11 — Hạn chế và hướng phát triển

```
┌────────────────────────────────────────────────────────────┐
│  HẠN CHẾ VÀ HƯỚNG PHÁT TRIỂN                               │
│                                                            │
│  17 văn bản, chưa bao phủ toàn bộ pháp luật giao thông     │
│  Chỉ số mức Điểm chỉ có 3 trường hợp                       │
│  2 câu ngoài kho dữ liệu vẫn được trả lời                  │
│  Độ trễ còn cao với câu hỏi nhiều ý                        │
│                                                            │
│  Thêm xếp hạng lại và lọc theo Điều/Khoản                  │
│  Mở rộng kho dữ liệu, cập nhật theo hiệu lực               │
│  Tác tử nhiều bước, đồ thị quan hệ văn bản                 │
└────────────────────────────────────────────────────────────┘
```

---

## Slide 12 — Kết luận

```
┌────────────────────────────────────────────────────────────┐
│  KẾT LUẬN                                                  │
│                                                            │
│  Trả lời từ kho văn bản đã chuẩn hóa, kèm vị trí pháp lý   │
│  Từ chối hoặc yêu cầu làm rõ khi thiếu căn cứ              │
│  Cập nhật dữ liệu bằng cách xây lại chỉ mục                │
│                                                            │
│  XIN CẢM ƠN — SẴN SÀNG DEMO VÀ TRẢ LỜI CÂU HỎI             │
└────────────────────────────────────────────────────────────┘
```
