# 08. Bảo Trì & Phát Triển Sau Khóa Luận

> **Giai đoạn SDLC**: 7 — Bảo trì
> **Ngày tạo**: 16/06/2026

---

## 8.1. Kế hoạch bảo trì

### 8.1.1. Tần suất bảo trì

| Tần suất | Hoạt động | Người thực hiện |
|----------|-----------|-----------------|
| **Hàng tuần** | Kiểm tra uptime, logs, cập nhật văn bản mới | Dev (tự động) |
| **Hàng tháng** | Chạy lại evaluation, so sánh với baseline | Dev |
| **Hàng quý** | Review prompt, cập nhật LLM mới, mở rộng corpus | Dev |
| **Khi có văn bản mới** | Crawl + parse + ingest | Auto + manual verify |

### 8.1.2. Cập nhật văn bản mới (Quan trọng nhất)

> Pháp luật VN thay đổi liên tục. Cần pipeline tự động cập nhật.

```bash
# scripts/update_corpus.sh
#!/bin/bash

# 1. Crawl PDF mới từ thuvienphapluat.vn
poetry run python scripts/crawl_pdfs.py --since 2026-06-01

# 2. Parse + chunk
poetry run python scripts/parse_pdfs.py --input data/pdfs/new/

# 3. Embed + index (KHÔNG xóa chunks cũ)
poetry run python scripts/ingest_corpus.py \
    --json data/corpus/new/*.json \
    --mode append  # QUAN TRỌNG: append, không replace

# 4. Chạy regression test
poetry run pytest tests/test_retrieval_regression.py -v

# 5. Nếu pass → commit
git add data/
git commit -m "feat(corpus): add 3 new legal documents (June 2026)"
git push
```

### 8.1.3. Theo dõi văn bản hết hiệu lực

```python
# scripts/check_expired.py
"""
Check corpus có văn bản nào hết hiệu lực không.
"""
import json
from pathlib import Path
from datetime import date

def main():
    corpus_dir = Path("data/corpus")
    expired = []
    expired_soon = []  # Sắp hết hiệu lực trong 30 ngày
    
    for json_file in corpus_dir.glob("*.json"):
        with open(json_file) as f:
            doc = json.load(f)
        expiry = doc.get("expiry_date")
        if expiry:
            expiry_date = date.fromisoformat(expiry)
            today = date.today()
            days_left = (expiry_date - today).days
            
            if days_left < 0:
                expired.append((doc["title"], expiry))
            elif days_left < 30:
                expired_soon.append((doc["title"], days_left))
    
    if expired:
        print(f"⚠️  {len(expired)} văn bản đã hết hiệu lực:")
        for title, expiry in expired:
            print(f"  - {title} (hết từ {expiry})")
    
    if expired_soon:
        print(f"\n⏰ {len(expired_soon)} văn bản sắp hết hiệu lực:")
        for title, days in expired_soon:
            print(f"  - {title} (còn {days} ngày)")

if __name__ == "__main__":
    main()
```

---

## 8.2. Monitoring thường trực

### 8.2.1. Các metric cần theo dõi

| Metric | Công cụ đo | Ngưỡng cảnh báo |
|--------|-----------|-----------------|
| Uptime | Health check mỗi 5 phút | < 99% |
| Latency P95 | Logging + stats | > 20s |
| Error rate | Logs | > 5% |
| LLM API quota | Manual check dashboard | > 80% |
| Disk usage | `df -h` | > 80% |
| Memory usage | `docker stats` | > 80% |
| Corpus freshness | `check_expired.py` | Có VB hết hiệu lực |

### 8.2.2. Alerting (Optional)

```bash
# scripts/health_check.sh - chạy bằng cron mỗi 5 phút
#!/bin/bash

HEALTH_URL="https://vnlaw.example.com/api/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ "$RESPONSE" != "200" ]; then
    # Gửi email hoặc Telegram alert
    curl -s "https://api.telegram.org/bot<TOKEN>/sendMessage" \
        -d "chat_id=<CHAT_ID>" \
        -d "text=🚨 vnlaw-agentic-rag DOWN! HTTP $RESPONSE"
fi
```

---

## 8.3. Versioning & Changelog

### 8.3.1. Semantic Versioning

```
MAJOR.MINOR.PATCH
  │     │     │
  │     │     └── Bug fix
  │     └──────── Feature mới
  └────────────── Breaking change
```

Ví dụ: `1.2.0` = Major 1, Minor 2 (thêm feature), Patch 0.

### 8.3.2. CHANGELOG.md

```markdown
# Changelog

## [1.1.0] - 2026-09-01
### Added
- Hỗ trợ streaming response
- 5 văn bản pháp luật mới

### Changed
- Nâng cấp Gemini 2.5 → 3 Flash

### Fixed
- Fix bug parse PDF NĐ 100/2019

## [1.0.0] - 2026-08-03
### Added
- Initial release cho khóa luận
```

---

## 8.4. Hướng phát triển sau khóa luận

### 8.4.1. Ngắn hạn (1-3 tháng sau)

| Cải tiến | Độ khó | Lợi ích |
|----------|--------|---------|
| **Mở rộng corpus lên 100+ văn bản** | Dễ | Độ phủ cao hơn |
| **Thêm multi-turn conversation** | Trung bình | UX tốt hơn |
| **Tối ưu prompt Legal Reasoning** | Dễ | Quality tăng |
| **Thêm chế độ "summary" tự động** | Trung bình | Có giá trị thêm |
| **Export PDF/Word câu trả lời** | Dễ | Tiện cho user |

### 8.4.2. Trung hạn (3-6 tháng)

| Cải tiến | Độ khó | Lợi ích |
|----------|--------|---------|
| **GraphRAG** (Knowledge Graph) | Khó | Trả lời quan hệ phức tạp |
| **Multi-modal**: Trích xuất từ ảnh BBGT | Khó | User upload ảnh phạt nguội |
| **Voice input/output** | Trung bình | UX tốt hơn |
| **Authentication** (OAuth) | Trung bình | Multi-user |
| **Mobile app** (React Native) | Khó | Tiếp cận rộng hơn |

### 8.4.3. Dài hạn (6-12 tháng)

| Cải tiến | Độ khó | Lợi ích |
|----------|--------|---------|
| **Fine-tune embedding cho PLVN** | Khó (cần GPU) | Quality retrieval tăng mạnh |
| **Fine-tune LLM với corpus PLVN** | Rất khó | Model chuyên PLVN |
| **Tích hợp CSDL QPPL chính thức** | Trung bình | Dữ liệu chuẩn |
| **Cộng đồng đóng góp corpus** | Khó | Mở rộng nhanh |
| **Public API + Pricing** | Trung bình | Có thể thương mại hóa |

---

## 8.5. Tài liệu cần duy trì

| File | Cập nhật khi |
|------|--------------|
| `README.md` | Thay đổi setup, API mới |
| `CHANGELOG.md` | Mỗi release |
| `docs/01-08-*.md` | Thay đổi kiến trúc lớn |
| `data/gold_set.json` | Thêm câu mới, cập nhật expected answer |
| `data/eval_results/` | Mỗi lần chạy eval |
| `docs/architecture.md` | Mỗi khi đổi tech stack |

---

## 8.6. Đóng góp cho cộng đồng

### 8.6.1. Mở source code

```bash
# Tạo LICENSE (MIT hoặc Apache 2.0)
# Cập nhật README với hướng dẫn contributing
# Tạo CONTRIBUTING.md
# Tạo GitHub Issues templates
```

### 8.6.2. Chia sẻ tham khảo

- **Bài viết Viblo** chia sẻ kinh nghiệm RAG
- **Repo VN-Law-Advisor** tham khảo kiến trúc
- **GitHub repo** mới có thể được star bởi cộng đồng AI VN

---

## 8.7. Bài học rút ra (cho báo cáo)

> Các bài học này nên viết vào phần "Kết luận & Bài học" trong báo cáo khóa luận.

1. **Tầm quan trọng của citation validation** — LLM rất giỏi "nói" nhưng dễ bịa. Bắt buộc phải validate citation có trong context.
2. **Hybrid retrieval > Single retrieval** — Kết hợp dense + sparse cho tiếng Việt hiệu quả hơn nhiều.
3. **Reranker rất tốn tài nguyên** — Trên CPU, latency x30-80 lần. Cần GPU hoặc tắt.
4. **Free tier API vẫn đủ dùng cho research** — Gemini free 250 RPD dư sức cho project 7 tuần.
5. **HITL giải quyết vấn đề hallucination** — Khi web search, admin duyệt trước khi trả user.
6. **Custom evaluation quan trọng hơn RAGAS gốc** — Tự viết prompt giúp tiết kiệm 60× LLM calls.
7. **Incremental development với AI Agent** — Dùng Claude Code/OpenCode tăng tốc 3-5× nhưng phải review kỹ.
8. **Corpus quality > Quantity** — 30 văn bản clean tốt hơn 100 văn bản parse lỗi.

---

## 8.8. Kết thúc khóa luận

> **Checklist cuối cùng trước bảo vệ**:
> - [ ] Tất cả code đã commit lên GitHub
> - [ ] README đầy đủ hướng dẫn cài đặt
> - [ ] Báo cáo PDF 30-50 trang
> - [ ] Slide thuyết trình 20-25 slides
> - [ ] Demo live trên VPS (hoặc video quay sẵn)
> - [ ] Tài liệu thiết kế (8 file Markdown này) đầy đủ
> - [ ] Gold set 50 câu + kết quả ablation
> - [ ] CI pass (lint, test)
> - [ ] **Sẵn sàng bảo vệ** 🎓

**Chúc bạn thành công!** 🚀
