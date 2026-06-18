# Tài Liệu Tham Khảo

## A. Code tham khảo chính

### 1. CTU-LinguTechies/VN-Law-Advisor (91⭐)
- **URL**: https://github.com/CTU-LinguTechies/VN-Law-Advisor
- **Mô tả**: Ứng dụng hỗ trợ tra cứu, hỏi đáp tri thức pháp luật dựa trên Bộ pháp điển và CSDL văn bản QPPL Việt Nam
- **Công nghệ**: NextJS 14, Kong API Gateway, ExpressJS, SpringBoot, Flask, LangChain, MySQL, Redis, ChromaDB, RabbitMQ, Docker, Prometheus, Grafana
- **Áp dụng cho project**:
  - Tham khảo cấu trúc thư mục microservices (rồi đơn giản hóa thành monolith)
  - Schema CSDL QPPL
  - PDF crawler từ thuvienphapluat.vn
  - Docker Compose setup
  - CI/CD với GitHub Actions

### 2. Viblo - Xây dựng hệ thống RAG - Pháp luật Giao thông Việt Nam
- **URL**: https://viblo.asia/p/xay-dung-he-thong-agentic-rag-phap-luat-giao-thong-viet-nam-tu-pdf-van-ban-luat-den-he-thong-agentic-rag-ZjJYWNWOVOE
- **Tác giả**: Huy Quốc (@quochuy247)
- **Công nghệ**: LangGraph, Qdrant 1.7, intfloat/multilingual-e5-small, BM25 với pyvi, Gemini 3.1 Flash, Tavily API, FastAPI, Next.js 14, LangSmith, RAGAS-lite
- **Áp dụng cho project**:
  - LangGraph state machine pattern
  - Hybrid Retrieval với RRF (Reciprocal Rank Fusion)
  - HITL với `interrupt_before` + SQLite checkpointer
  - Custom RAGAS-lite (1 call/metric/sample thay vì 60)
  - Legal Reasoning Prompt với 14 quy tắc
  - Ablation test methodology
  - 6 bài học xương máu khi làm RAG tiếng Việt

---

## B. Frameworks & Tools

### 3. LangGraph Documentation
- **URL**: https://langchain-ai.github.io/langgraph/
- **Áp dụng**: State machine, HITL, checkpointers

### 4. LangChain RAG Tutorial
- **URL**: https://python.langchain.com/docs/tutorials/rag/
- **Áp dụng**: Retrieval patterns, document loaders

### 5. FastAPI Documentation
- **URL**: https://fastapi.tiangolo.com/
- **Áp dụng**: Async API, streaming, validation

### 6. Next.js 14 Documentation
- **URL**: https://nextjs.org/docs
- **Áp dụng**: App Router, SSR, streaming

### 7. ChromaDB
- **URL**: https://docs.trychroma.com/
- **Áp dụng**: Vector store local

### 8. Ollama (nếu dùng local LLM)
- **URL**: https://ollama.com/
- **Áp dụng**: Local LLM cho testing

### 9. pyvi
- **URL**: https://github.com/trungtv/pyvi
- **Áp dụng**: Tokenize tiếng Việt cho BM25

---

## C. Models

### 10. intfloat/multilingual-e5-small
- **URL**: https://huggingface.co/intfloat/multilingual-e5-small
- **Mô tả**: Embedding model 384-dim, hỗ trợ 100+ ngôn ngữ
- **Size**: 471MB
- **Áp dụng**: Embedding chính cho retrieval

### 11. keepitreal/vietnamese-sbert
- **URL**: https://huggingface.co/keepitreal/vietnamese-sbert
- **Mô tả**: Vietnamese-specific SBERT
- **Áp dụng**: Alternative embedding trong ablation

### 12. BAAI/bge-reranker-v2-m3
- **URL**: https://huggingface.co/BAAI/bge-reranker-v2-m3
- **Mô tả**: Cross-encoder reranker
- **Áp dụng**: Reranker (optional, cần GPU)

### 13. Qwen2.5 (nếu dùng local)
- **URL**: https://qwenlm.github.io/
- **Áp dụng**: Local LLM via Ollama

### 14. VinAI PhoGPT (tham khảo)
- **URL**: https://github.com/VinAIResearch/PhoGPT
- **Áp dụng**: Reference cho Vietnamese LLM (không dùng vì cần GPU)

---

## D. Dữ liệu pháp luật

### 15. Bộ pháp điển Việt Nam
- **URL**: https://phapdien.moj.gov.vn/
- **Áp dụng**: Crawl văn bản PL

### 16. CSDL QPPL Việt Nam
- **URL**: https://thuvienphapluat.vn/
- **Áp dụng**: Crawl văn bản QPPL

### 17. Cổng thông tin điện tử Quốc hội
- **URL**: https://quochoi.vn/
- **Áp dụng**: Văn bản chính thức

### 18. Dữ liệu mở về PLVN
- **URL**: https://data.gov.vn/
- **Áp dụng**: Nguồn dữ liệu mở

---

## E. Evaluation

### 19. RAGAS Framework
- **URL**: https://docs.ragas.io/
- **Mô tả**: Framework đánh giá RAG
- **Áp dụng**: Tham khảo concepts, tự viết lite version

### 20. Reciprocal Rank Fusion (RRF) Paper
- **URL**: https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf
- **Áp dụng**: Algorithm fusion dense + sparse retrieval

### 21. Hybrid Search Best Practices
- **URL**: https://www.pinecone.io/learn/series/rag/hybrid-search/
- **Áp dụng**: Concepts và implementation

---

## F. LLM API Documentation

### 22. Google Gemini API
- **URL**: https://ai.google.dev/gemini-api/docs
- **Pricing**: https://ai.google.dev/gemini-api/docs/pricing
- **Rate limits**: https://ai.google.dev/gemini-api/docs/rate-limits
- **Áp dụng**: LLM chính (Free tier)

### 23. OpenAI API
- **URL**: https://platform.openai.com/docs
- **Pricing**: https://openai.com/api/pricing/
- **Áp dụng**: LLM phụ (evaluation)

### 24. Google AI Studio
- **URL**: https://aistudio.google.com/
- **Áp dụng**: Test Gemini models, lấy API key

---

## G. Vietnamese NLP

### 25. underthesea
- **URL**: https://underthesea.readthedocs.io/
- **Áp dụng**: Tokenization, NER, sentiment (optional)

### 26. Vietnamese NLP Tools Comparison
- **URL**: https://github.com/VinAIResearch/PhoNLP
- **Áp dụng**: Reference cho Vietnamese tokenization

### 27. Vietnamese Spell Check
- **URL**: https://github.com/tuanpham-vn/vi-spell-check
- **Áp dụng**: Optional - sửa lỗi chính tả câu hỏi

---

## H. Infrastructure & DevOps

### 28. Docker Documentation
- **URL**: https://docs.docker.com/
- **Áp dụng**: Containerization

### 29. GitHub Actions
- **URL**: https://docs.github.com/en/actions
- **Áp dụng**: CI/CD

### 30. Oracle Cloud Free Tier
- **URL**: https://www.oracle.com/cloud/free/
- **Áp dụng**: VPS miễn phí vĩnh viễn

### 31. Nginx Documentation
- **URL**: https://nginx.org/en/docs/
- **Áp dụng**: Reverse proxy

### 32. Let's Encrypt
- **URL**: https://letsencrypt.org/
- **Áp dụng**: SSL miễn phí

---

## I. Tài liệu học thuật

### 33. RAG Survey Paper
- **Title**: "Retrieval-Augmented Generation for Large Language Models: A Survey"
- **URL**: https://arxiv.org/abs/2312.10997
- **Áp dụng**: Background cho khóa luận

### 34. Self-RAG Paper
- **URL**: https://arxiv.org/abs/2310.11511
- **Áp dụng**: Reference cho self-reflective RAG

### 35. CRAG (Corrective RAG)
- **URL**: https://arxiv.org/abs/2401.15884
- **Áp dụng**: Reference cho fallback strategy

### 36. RAG Survey
- **URL**: https://arxiv.org/abs/2501.09136
- **Áp dụng**: Background cho approach

### 37. GraphRAG Paper
- **URL**: https://arxiv.org/abs/2404.16130
- **Áp dụng**: Hướng phát triển tương lai

---

## J. Tools hỗ trợ làm khóa luận

### 38. Overleaf
- **URL**: https://www.overleaf.com/
- **Áp dụng**: Viết báo cáo LaTeX

### 39. Mermaid Live Editor
- **URL**: https://mermaid.live/
- **Áp dụng**: Vẽ diagram (kiến trúc, sequence, class)

### 40. Excalidraw
- **URL**: https://excalidraw.com/
- **Áp dụng**: Vẽ sơ đồ đơn giản

### 41. Canva
- **URL**: https://www.canva.com/
- **Áp dụng**: Làm slide thuyết trình

---

## K. Bài học từ các dự án thất bại (Post-mortem)

### 42. Lessons from RAG Failures
- **URL**: https://github.com/microsoft/kernel-memory
- **Áp dụng**: Tránh các pitfall phổ biến

### 43. LLM Hallucination Survey
- **URL**: https://arxiv.org/abs/2311.05232
- **Áp dụng**: Hiểu về hallucination và cách giảm thiểu

---

## L. Cộng đồng

### 44. Viblo
- **URL**: https://viblo.asia/
- **Áp dụng**: Chia sẻ bài viết, học hỏi

### 45. LangChain Discord
- **URL**: https://discord.gg/langchain
- **Áp dụng**: Hỏi đáp khi gặp lỗi

### 46. r/LocalLLaMA
- **URL**: https://www.reddit.com/r/LocalLLaMA/
- **Áp dụng**: Cập nhật về local LLMs

---

## Tổng kết

Danh sách 46 tài liệu tham khảo trên bao gồm:
- **2 dự án tham khảo chính** (code mẫu)
- **7 framework/tools** (FastAPI, LangGraph, Next.js, ChromaDB, Ollama, pyvi)
- **5 models** (embeddings + LLMs)
- **4 nguồn dữ liệu PLVN**
- **3 tài liệu về evaluation**
- **3 docs về LLM API** (Gemini, OpenAI, AI Studio)
- **3 tài liệu về Vietnamese NLP**
- **5 tài liệu về DevOps/Infra**
- **5 papers học thuật**
- **4 tools làm khóa luận**
- **2 bài học từ failures**
- **3 cộng đồng**

Khi viết báo cáo, **BẮT BUỘC trích dẫn** các nguồn này theo format chuẩn (IEEE/ACM/APA) tùy theo yêu cầu của GVHD.
