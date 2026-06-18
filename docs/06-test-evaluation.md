# 06. Kiểm Thử & Đánh Giá Hệ Thống

> **Giai đoạn SDLC**: 5 — Kiểm thử
> **Ngày tạo**: 16/06/2026
> **CẬP NHẬT SAU FALSIFICATION REVIEW (A1, A2, A3, A4, B5)**

> ## ⚠️ THAY ĐỔI QUAN TRỌNG
> 
> 4 findings defense-blocking trong review đã được fix trong doc này:
> - **A1**: Eval pipeline **PHẢI chạy generation**, không hardcode `answer: None`
> - **A2**: Thêm **Citation Correctness** làm headline metric
> - **A3**: Force **judge = GPT-4o-mini** bất kể variant
> - **A4**: Robust regex parsing cho LLM scores
> - **B5**: Drop V4 (reranker) — không khả thi trên MX330

---

## 6.1. Chiến lược kiểm thử tổng thể

| Loại | Mục tiêu | Tool | Mức bao phủ | Người thực hiện |
|------|----------|------|-------------|-----------------|
| **Unit Test** | Test function/class riêng lẻ | pytest | ≥ 70% core | Auto |
| **Integration Test** | Test tương tác giữa services | pytest + httpx | ≥ 80% API | Auto |
| **Retrieval Regression** | Đảm bảo retrieval không thoái hóa | pytest custom | 100% | Auto (CI) |
| **End-to-End Test** | Test toàn bộ flow | Playwright | 5 scenarios | Auto + Manual |
| **Manual Test (UX)** | Test UI + chất lượng câu trả lời | Bảng đánh giá | 50 câu | Manual |
| **Performance Test** | Latency, throughput | locust / ab | 100% | Auto |

---

## 6.2. Unit Test

### 6.2.1. Cấu trúc

```
backend/tests/
├── conftest.py                    # Fixtures chung
├── test_parsers.py                # PDF parser
├── test_chunkers.py               # Custom chunker PLVN
├── test_embedding.py              # Embedding service
├── test_retrieval.py              # Hybrid retrieval
├── test_llm_service.py            # LLM wrapper
├── test_agents.py                 # LangGraph nodes
├── test_api.py                    # FastAPI endpoints
├── test_evaluation.py             # RAGAS-lite
└── test_retrieval_regression.py   # BẮT BUỘC
```

### 6.2.2. Ví dụ Unit Test

```python
# tests/test_chunkers.py
import pytest
from app.parsers.law_chunker import LawChunker
from app.parsers.cleaners.clean_nghi_dinh import clean_nghi_dinh_text

class TestNghiDinhChunker:
    def test_chunks_have_hierarchy(self):
        raw_text = """
        Điều 6. Xử phạt hành vi vi phạm quy tắc giao thông
        1. Phạt tiền từ 200.000 đồng...
        2. Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với:
        a) Không chấp hành tín hiệu đèn điều khiển giao thông;
        b) Đi ngược chiều...
        """
        chunker = LawChunker(doc_type="NGHI_DINH")
        chunks = chunker.chunk(raw_text)
        
        assert len(chunks) > 0
        assert all("dieu" in c["metadata"] for c in chunks)
        assert chunks[0]["metadata"]["dieu"] == 6
    
    def test_citation_extraction(self):
        chunk = {
            "content": "Phạt tiền 4-6 triệu đối với vượt đèn đỏ",
            "metadata": {"dieu": 6, "khoan": 2, "diem": "a"}
        }
        citation = extract_citation(chunk)
        assert citation == "[Nghị định, Điều 6, Khoản 2, Điểm a]"
```

---

## 6.3. Retrieval Regression Test (BẮT BUỘC)

> File này chạy trong CI, đảm bảo khi thay đổi model/threshold không làm giảm chất lượng.

```python
# tests/test_retrieval_regression.py
"""
CI Regression Gate cho retrieval quality.
Nếu mean Recall@10 < threshold, CI sẽ FAIL và block merge.
"""
import pytest
from app.services.retrieval import HybridRetriever

# Threshold tối thiểu (điều chỉnh sau khi có baseline)
MIN_RECALL_10 = 0.40

# Test cases: (query, expected_doc_id, expected_dieu)
TEST_CASES = [
    (
        "Vượt đèn đỏ phạt bao nhiêu tiền?",
        "nghi_dinh_168_2024",
        6
    ),
    (
        "Nồng độ cồn cho phép khi lái xe?",
        "luat_36_2024",
        8
    ),
    (
        "Phạt không đội mũ bảo hiểm?",
        "nghi_dinh_168_2024",
        6
    ),
    (
        "Đỗ xe sai quy định?",
        "nghi_dinh_168_2024",
        6
    ),
    (
        "Tốc độ tối đa trong khu đông dân cư?",
        "luat_36_2024",
        10
    ),
    # Thêm 25-45 câu nữa
]

@pytest.fixture(scope="module")
def retriever():
    return HybridRetriever(
        embedding_model="intfloat/multilingual-e5-small",
        use_bm25=True,
        use_reranker=False
    )

@pytest.mark.parametrize("query,expected_doc,expected_dieu", TEST_CASES)
def test_top_10_contains_expected(retriever, query, expected_doc, expected_dieu):
    """Test top-10 kết quả có chứa chunk đúng."""
    results = retriever.retrieve(query, top_k=10)
    
    found = any(
        r["metadata"]["doc_id"] == expected_doc 
        and r["metadata"].get("dieu") == expected_dieu
        for r in results
    )
    
    assert found, f"Query '{query}' không tìm thấy {expected_doc} Điều {expected_dieu}"

def test_mean_recall_at_10(retriever):
    """Test mean Recall@10 >= threshold."""
    recalls = []
    for query, expected_doc, expected_dieu in TEST_CASES:
        results = retriever.retrieve(query, top_k=10)
        # Recall@10 = 1 nếu expected có trong top-10, 0 nếu không
        hit = any(
            r["metadata"]["doc_id"] == expected_doc 
            and r["metadata"].get("dieu") == expected_dieu
            for r in results
        )
        recalls.append(1.0 if hit else 0.0)
    
    mean_recall = sum(recalls) / len(recalls)
    print(f"\nMean Recall@10: {mean_recall:.2f}")
    print(f"Per-query: {recalls}")
    
    assert mean_recall >= MIN_RECALL_10, \
        f"Mean Recall@10 = {mean_recall:.2f} < threshold {MIN_RECALL_10}"
```

### 6.3.1. CI Workflow (POST-REVIEW C11 — consolidated in [07 §7.4.1])

> **C11 fix**: CI workflow đã consolidate thành 1 file duy nhất tại [docs/07-deployment.md §7.4.1](../07-deployment.md#741-single-ci-workflow).
> - ChromaDB local persistent (không cần Docker service container)
> - Single job: lint + type-check + test (unit + smoke + regression)
> - Một workflow duy nhất chạy trên push/PR
> 
> Xem chi tiết tại [07-deployment.md](../07-deployment.md).

---

## 6.4. End-to-End Test (Flow)

```python
# tests/test_agents.py
import pytest
from app.agents.graph import create_agent_graph
from app.agents.state import AgentState

class TestAgenticFlow:
    @pytest.mark.asyncio
    async def test_simple_query_in_corpus(self):
        """Câu hỏi đơn giản trong corpus → trả lời có citation."""
        graph = create_agent_graph()
        state: AgentState = {
            "query": "Vượt đèn đỏ phạt bao nhiêu?",
            "thread_id": "test-001",
            "messages": [],
            "iterations": 0
        }
        result = graph.invoke(state)
        
        assert result["answer"] is not None
        assert len(result["citations"]) > 0
        assert "168" in str(result["citations"])  # NĐ 168
    
    @pytest.mark.asyncio
    async def test_low_score_triggers_web_search(self):
        """Score < 0.4 → trigger web search (HITL removed in MVP, returns auto-answer)."""
        graph = create_agent_graph()
        state: AgentState = {
            "query": "Luật xe điện 2026?",  # Không có trong corpus
            "query_id": "test-002",
            "rewrite_count": 0,
            "iterations": 0,
            "regen_count": 0
        }
        result = graph.invoke(state)
        
        # Nếu relevance_score < 0.4 → web_used=True, disclaimer kèm "nguồn web"
        if result.get("answer"):
            assert result["web_used"] is True
            assert "nguồn" in result.get("answer", "").lower()
    
    @pytest.mark.asyncio
    async def test_situation_question_has_disclaimer(self):
        """Câu hỏi tình huống 'lỗi của ai' phải có disclaimer CSGT."""
        graph = create_agent_graph()
        state: AgentState = {
            "query": "Va chạm giữa 2 xe, ai có lỗi?",
            "thread_id": "test-003",
            "messages": [],
            "iterations": 0
        }
        result = graph.invoke(state)
        
        assert "CSGT" in result["answer"]
        assert "% lỗi" in result["answer"] or "tỷ lệ" in result["answer"].lower()
```

---

## 6.5. Đánh giá hệ thống (RAGAS-lite Custom)

> **Tại sao custom?**: RAGAS gốc gọi ~6,000 LLM calls cho 25 câu × 4 metrics → dính rate-limit Gemini. Custom chỉ cần ~100 calls.

### 6.5.1. 4 Metrics

| Metric | Ý nghĩa | Prompt gọn |
|--------|----------|-----------|
| **Faithfulness** | Answer có trung thành với context không? (chống hallucinate) | "Câu trả lời này có thông tin nào KHÔNG có trong context không? Score 0-1, 1 = trung thành" |
| **Answer Relevancy** | Answer có liên quan câu hỏi không? | "Câu trả lời có giải quyết câu hỏi không? Score 0-1" |
| **Context Precision** | Top-k chunks có chứa đáp án + xếp hạng đúng không? | "Trong top-k contexts, cái nào thực sự liên quan? Tính precision@k" |
| **Context Recall** | Có bỏ sót context quan trọng không? | "Có chunk nào bị thiếu mà cần để trả lời? Score 0-1" |

### 6.5.2. Code

```python
# services/evaluation.py
import json
from typing import List, Dict
from app.services.llm import LLMService

class RagasLiteEvaluator:
    """Custom RAGAS evaluator - 1 call/metric/sample."""
    
    def __init__(self, llm: LLMService):
        self.llm = llm
    
    def evaluate(
        self,
        gold_set: List[Dict],   # [{id, question, expected_answer, expected_doc, expected_dieu, expected_khoan, expected_diem}, ...]
        results: List[Dict]     # [{id, answer, contexts, citations, generated_citations, relevance_score}, ...]
    ) -> Dict:
        """Run all 5 metrics trên toàn bộ gold set.
        
        POST-REVIEW (A1, A2, A3): 
        - Generation already ran in caller
        - Judge is fixed to GPT-4o-mini (passed in __init__)
        - Citation Correctness is HEADLINE metric
        - All alignments use gold['id'] == result['id'], not zip (fix C8)
        """
        # NEW (C8 fix): Align by id, not by position
        results_by_id = {r["id"]: r for r in results}
        aligned = []
        for gold in gold_set:
            gid = gold["id"]
            if gid not in results_by_id:
                raise ValueError(f"Missing result for {gid}")
            aligned.append((gold, results_by_id[gid]))
        
        metrics = {
            "citation_correctness": [],   # NEW (A2): headline metric
            "faithfulness": [],
            "answer_relevancy": [],
            "context_precision": [],
            "context_recall": []
        }
        
        for gold, res in aligned:
            # 0. NEW (A2): Citation Correctness — EXACT MATCH
            # N1 fix: key must match gold_set.json schema (expected_doc_id not expected_doc)
            if not gold.get("in_corpus", True):
                # N1 fix: adversarial items — skip citation check (handled by refusal test)
                metrics["citation_correctness"].append(None)
            else:
                metrics["citation_correctness"].append(
                    self._citation_correctness(
                        generated_citations=res.get("generated_citations", []),
                        gold_doc=gold["expected_doc_id"],  # N1 fix: expected_doc_id not expected_doc
                        gold_dieu=gold["expected_dieu"],
                        gold_khoan=gold.get("expected_khoan"),
                        gold_diem=gold.get("expected_diem")
                    )
                )
            # 1. Faithfulness
            metrics["faithfulness"].append(
                self._faithfulness(res["answer"], res["contexts"])
            )
            # 2. Answer Relevancy
            metrics["answer_relevancy"].append(
                self._answer_relevancy(res["question"], res["answer"])
            )
            # 3. Context Precision
            metrics["context_precision"].append(
                self._context_precision(res["question"], res["contexts"])
            )
            # 4. Context Recall
            metrics["context_recall"].append(
                self._context_recall(
                    res["question"], 
                    gold["expected_answer"], 
                    res["contexts"]
                )
            )
        
        # Aggregate
        return {
            metric: {
                "mean": sum(scores) / len(scores) if scores else 0.0,
                "scores": scores,
                "n": len(scores)
            }
            for metric, scores in metrics.items()
        }
    
    def _parse_score(self, raw: str) -> float:
        """NEW (A4 fix): Robust regex extraction for LLM scores.
        
        LLM responses may contain: "Score: 0.8", "0,8", "khoảng 0.7", "0.7/1.0", etc.
        Old code: float(raw.strip()) → crashes on these.
        """
        import re
        if not raw:
            return 0.0
        # Find first decimal number in response
        match = re.search(r"[-+]?\d*\.?\d+", str(raw).replace(",", "."))
        if not match:
            return 0.0
        try:
            val = float(match.group())
            # Clamp to [0, 1]
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.0
    
    def _citation_correctness(
        self, 
        generated_citations: List[Dict], 
        gold_doc: str, 
        gold_dieu: int,
        gold_khoan: int | None = None,
        gold_diem: str | None = None
    ) -> float:
        """NEW (A2): Headline metric — exact match on doc_id + dieu + (khoan) + (diem).
        
        Returns 1.0 if ANY citation in generated_citations matches the gold tuple.
        Returns 0.0 if NO match.
        This is deterministic, no LLM judge needed.
        """
        if not generated_citations:
            return 0.0
        for c in generated_citations:
            if c.get("doc_id") != gold_doc:
                continue
            if c.get("dieu") != gold_dieu:
                continue
            if gold_khoan is not None and c.get("khoan") != gold_khoan:
                continue
            if gold_diem is not None and c.get("diem") != gold_diem:
                continue
            return 1.0
        return 0.0
    
    def _faithfulness(self, answer: str, contexts: List[str]) -> float:
        prompt = f"""Đánh giá xem câu trả lời có trung thành với context không.
Context: {contexts}
Answer: {answer}
Chỉ trả lời 1 số từ 0 đến 1 (1 = hoàn toàn trung thành, 0 = hoàn toàn bịa).
Score: """
        raw = self.llm.generate(prompt, max_tokens=10, response_format={"type": "json"})
        return self._parse_score(raw)
    
    def _answer_relevancy(self, question: str, answer: str) -> float:
        prompt = f"""Đánh giá xem câu trả lời có liên quan đến câu hỏi không.
Question: {question}
Answer: {answer}
Chỉ trả lời 1 số từ 0 đến 1 (1 = trả lời đúng trọng tâm, 0 = lạc đề).
Score: """
        raw = self.llm.generate(prompt, max_tokens=10, response_format={"type": "json"})
        return self._parse_score(raw)
    
    def _context_precision(self, question: str, contexts: List[str]) -> float:
        # C7 fix: implement rank-aware precision (closer to RAGAS definition)
        prompt = f"""Trong các context sau (đã sắp xếp theo rank), context nào THỰC SỰ liên quan đến câu hỏi?
Question: {question}
Contexts (ranked): {contexts}
Liệt kê index (0-based) của các context LIÊN QUAN, cách nhau bởi dấu phẩy. Nếu không có, trả lời "none".
Relevant indices: """
        raw = self.llm.generate(prompt, max_tokens=20, response_format={"type": "json"})
        # Parse indices, compute rank-aware precision
        if not raw or "none" in raw.lower():
            return 0.0
        import re
        indices = [int(x) for x in re.findall(r"\d+", raw)]
        if not indices:
            return 0.0
    # Precision = number of relevant items / total items (standard precision@k)
    # NOT sum(1/rank)/k (that was wrong — H3 fix)
    k = len(contexts)
    return len(indices) / k if k > 0 else 0.0
    
    def _context_recall(self, question: str, expected: str, contexts: List[str]) -> float:
        prompt = f"""Dựa trên expected_answer, các context có đủ thông tin để trả lời không?
Question: {question}
Expected Answer: {expected}
Contexts: {contexts}
Đánh giá xem các context có chứa thông tin cần thiết. Score 0-1.
Score: """
        raw = self.llm.generate(prompt, max_tokens=10, response_format={"type": "json"})
        return self._parse_score(raw)
```

### 6.5.3. Script chạy Evaluation

```python
# scripts/run_eval.py
import json
import argparse
from pathlib import Path
from app.services.retrieval import HybridRetriever
from app.services.llm import LLMService
from app.services.evaluation import RagasLiteEvaluator

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, choices=["V1", "V2", "V3"],
                        help="V1=Dense, V2=BM25, V3=Hybrid (B5 fix: V4 reranker dropped)")
    parser.add_argument("--gold-set", default="data/gold_set.json")
    parser.add_argument("--llm", default="gemini", choices=["gemini", "openai"],
                        help="Generator LLM (judge is always GPT-4o-mini, A3 fix)")
    parser.add_argument("--judge-provider", default="openai", choices=["openai"],
                        help="A3 fix: force judge = GPT-4o-mini regardless of variant")
    args = parser.parse_args()
    
    # Load gold set
    with open(args.gold_set) as f:
        gold_set = json.load(f)
    
    # Init services
    use_bm25 = args.variant in ("V2", "V3")
    retriever = HybridRetriever(
        use_bm25=use_bm25,
        # A1/B5 fix: use_reranker always False (V4 dropped)
        use_reranker=False
    )
    generator_llm = LLMService(provider=args.llm)  # Variant's generator
    judge_llm = LLMService(provider=args.judge_provider)  # A3 fix: ALWAYS GPT-4o-mini
    evaluator = RagasLiteEvaluator(judge_llm)  # A3 fix: judge != generator
    
    # Run retrieval + generation (A1 fix)
    results = []
    for item in gold_set:
        chunks = retriever.retrieve(item["question"], top_k=10)
        # A1 fix: ACTUALLY run generation, don't skip
        answer_obj = generator_llm.generate_with_citations(
            query=item["question"],
            contexts=[c["content"] for c in chunks]
        )
        results.append({
            "id": item["id"],
            "question": item["question"],
            "contexts": [c["content"] for c in chunks],
            "citations": chunks,
            "answer": answer_obj["answer"],
            "generated_citations": answer_obj["citations"],
            "relevance_score": answer_obj.get("relevance_score", 0.0)
        })
    
    # Evaluate
    metrics = evaluator.evaluate(gold_set, results)
    
    # Save
    output = {
        "variant": args.variant,
        "generator_llm": args.llm,
        "judge_llm": args.judge_provider,  # A3 fix: track which model judged
        "num_questions": len(gold_set),
        "metrics": {k: v["mean"] for k, v in metrics.items()},
        "details": {k: v["scores"] for k, v in metrics.items()}
    }
    
    out_path = Path(f"data/eval_results/{args.variant}_{args.llm}.json")
    out_path.parent.mkdir(exist_ok=True, parents=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved: {out_path}")
    print(f"   [HEADLINE] Citation Correctness: {output['metrics']['citation_correctness']:.2f}")
    print(f"   Faithfulness: {output['metrics']['faithfulness']:.2f}")
    print(f"   Answer Relevancy: {output['metrics']['answer_relevancy']:.2f}")
    print(f"   Context Precision: {output['metrics']['context_precision']:.2f}")
    print(f"   Context Recall: {output['metrics']['context_recall']:.2f}")

if __name__ == "__main__":
    main()
```

---

## 6.6. Ablation Test Plan (BẮT BUỘC cho khóa luận)

> **Mục tiêu**: So sánh các biến thể để chứng minh thiết kế tối ưu.

### 6.6.1. Ma trận variants (POST-REVIEW — B5 fix)

> **Thay đổi (A2, B5)**: Đã **DROP V4 (reranker)** vì không khả thi trên MX330 (CPU-only, latency x31-78). Đã **DROP V5/V6 (LLM comparison)** vì retrieval-only contexts giống nhau → LLM axis không có ý nghĩa. **DROP V7 (vietnamese-sbert)** vì chưa test trong MVP.

| Variant | Embedding | BM25 | RRF | Reranker | Generator LLM | Judge LLM |
|---------|-----------|------|-----|----------|---------------|-----------|
| **V1** | e5-small | ❌ | ❌ | ❌ | Gemini 2.5 Flash | GPT-4o-mini (forced) |
| **V2** | ❌ | ✅ | ❌ | ❌ | Gemini 2.5 Flash | GPT-4o-mini (forced) |
| **V3** | e5-small | ✅ | ✅ | ❌ | Gemini 2.5 Flash | GPT-4o-mini (forced) |

> **A2 fix**: Citation Correctness làm headline metric — đo exact match (doc_id + dieu + khoan + diem) với gold, KHÔNG dùng LLM judge (deterministic, không sợ judge bias).

### 6.6.2. Lệnh chạy (POST-REVIEW)

```bash
# V1: Dense only
poetry run python scripts/run_eval.py --variant V1 --llm gemini

# V2: BM25 only
poetry run python scripts/run_eval.py --variant V2 --llm gemini

# V3: Hybrid RRF (baseline recommendation)
poetry run python scripts/run_eval.py --variant V3 --llm gemini

# V3 với OpenAI generator (cho so sánh cost)
poetry run python scripts/run_eval.py --variant V3 --llm openai
```

> Judge luôn là GPT-4o-mini (hardcoded trong code), không truyền tham số.

### 6.6.3. Bảng kết quả mẫu (Template cho báo cáo)

> **[HEADLINE]**: Citation Correctness là số quan trọng nhất. Cột "Headline" đánh dấu.

| Variant | **Citation Correctness** ⭐ | Faithfulness | Answer Relevancy | Context Precision | Context Recall | Latency P95 (s) | Cost/query |
|---------|---------------------------|--------------|------------------|-------------------|----------------|-----------------|------------|
| V1: Dense only | ? | ? | ? | ? | ? | ?s | $0 |
| V2: BM25 only | ? | ? | ? | ? | ? | ?s | $0 |
| V3: Hybrid RRF | ? (target ≥ 0.85) | ? | ? | ? | ? | ?s | $0 |
| V3 + OpenAI gen | ? | ? | ? | ? | ? | ?s | <$0.001 |

> **Kỳ vọng có cơ sở**:
> - V3 > V1, V2 (hybrid cải thiện cả precision và recall)
> - V3 latency ~3-5s (4 LLM calls × ~1s mỗi cái)
> - Citation Correctness của V3 ≥ 0.7 (target, gold set 30 câu)

### 6.6.4. Phân tích kết quả trong báo cáo

Các phần cần phân tích:
1. **Citation Correctness** (headline): Trả lời "FR-01 đạt không?". Nếu < 0.85, phân tích failure cases.
2. **Tại sao V3 > V1, V2?** → Kết hợp semantic + keyword tốt hơn đơn lẻ
3. **Trade-off precision vs recall** → Hybrid tăng cả 2
4. **V3 vs V3+OpenAI**: Cost-quality trade-off
5. **Failure modes** (phân tích 5-10 câu sai): Prompt issue? Retrieval miss? Citation hallucination?

---

## 6.7. Gold Set (30 câu) — POST-REVIEW C6, D1

> **Đã fix (C6, D1)**: 
> - **30 câu** (pin, không 50)
> - **Adversarial questions** (câu ngoài corpus) để test refusal
> - **Frozen independently** (không tune retriever trên gold set)

### 6.7.1. Phân loại câu hỏi

| Loại | Số câu | Ví dụ |
|------|--------|-------|
| Phạt tiền | 8 | "Vượt đèn đỏ phạt bao nhiêu?" |
| Thủ tục | 5 | "Làm GPLX cần giấy tờ gì?" |
| Định nghĩa | 5 | "GPLX là gì?" |
| Tình huống | 4 | "Ai có lỗi khi 2 xe va chạm?" |
| Quy tắc | 3 | "Tốc độ tối đa trong khu đông dân cư?" |
| **Adversarial (ngoài corpus)** | 5 | "Luật xe điện 2026?" (expected: refuse) |
| **Tổng** | **30** | |

### 6.7.2. Format JSON

```json
[
  {
    "id": "q001",
    "question": "Vượt đèn đỏ bị phạt bao nhiêu tiền?",
    "expected_answer": "Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng",
    "expected_doc_id": "nghi_dinh_168_2024",
    "expected_dieu": 6,
    "expected_khoan": 2,
    "expected_diem": "a",
    "type": "PHAT",
    "difficulty": "easy",
    "in_corpus": true
  },
  {
    "id": "q002",
    "question": "Nồng độ cồn cho phép khi lái xe ô tô?",
    "expected_answer": "0 mg/100ml máu hoặc 0 mg/lít khí thở",
    "expected_doc_id": "luat_36_2024",
    "expected_dieu": 8,
    "type": "DINH_NGHIA",
    "difficulty": "medium",
    "in_corpus": true
  },
  {
    "id": "q028",
    "question": "Năm 2026 có luật mới về xe điện tự lái không?",
    "expected_answer": null,
    "expected_doc_id": null,
    "expected_dieu": null,
    "type": "ADVERSARIAL",
    "difficulty": "n/a",
    "in_corpus": false
  }
  // ... 27 câu nữa (D1 fix: 30 tổng, không 50)
]
```

### 6.7.3. Cách tạo gold set (POST-REVIEW C6)

> **C6 fix**: Gold set MUST be frozen before any retriever tuning. Tránh data leakage.

1. **15 câu manual** (trước khi đụng vào code): Bạn tự viết + đối chiếu văn bản
2. **10 câu LLM-gen + manual verify**: Cho Gemini tạo, bạn check expected_answer
3. **5 câu adversarial** (ngoài corpus): Test refusal logic
4. **Freeze** file `data/gold_set.json` với hash
5. **KHÔNG ĐƯỢC sửa gold set sau khi chạy eval** — nếu cần sửa, document lý do và bump version

```python
# scripts/freeze_gold_set.py
import hashlib
import json
from pathlib import Path

def freeze(gold_path: Path):
    with open(gold_path) as f:
        data = json.load(f)
    content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    hash_value = hashlib.sha256(content.encode()).hexdigest()[:16]
    freeze_file = gold_path.with_suffix(f".{hash_value}.frozen.json")
    freeze_file.write_text(content, encoding="utf-8")
    print(f"✅ Frozen: {freeze_file}")
    print(f"   Hash: {hash_value}")
    print(f"   Questions: {len(data)}")

if __name__ == "__main__":
    freeze(Path("data/gold_set.json"))
```

---

## 6.8. Báo cáo đánh giá (Mẫu)

```markdown
# Báo Cáo Đánh Giá Hệ Thống RAG

## 1. Mục tiêu đánh giá
- Đo lường chất lượng retrieval và generation
- So sánh các biến thể (ablation)
- Xác minh hệ thống đáp ứng yêu cầu

## 2. Cấu hình thử nghiệm
- Corpus: 30 văn bản PL giao thông
- Gold set: 50 câu
- LLM judge: OpenAI GPT-4o-mini
- Ngày chạy: ...

## 3. Kết quả

### 3.1. Bảng tổng hợp
[Chèn bảng ablation]

### 3.2. Phân tích
- V3 (Hybrid RRF) đạt Recall@10 = 0.62, vượt baseline 0.40
- LLM Gemini 2.5 Flash đạt Faithfulness 0.75, ngang GPT-4o-mini
- Reranker tăng 14.9% nDCG nhưng latency x31 lần → không khuyến nghị trên CPU

### 3.3. Latency
- P50: 2.8s
- P95: 8.5s (đạt NFR ≤ 15s)

## 4. Kết luận
- Hệ thống đáp ứng yêu cầu FR-01, FR-02, FR-07
- Hybrid retrieval là lựa chọn tối ưu
- Gemini free tier đủ dùng cho production demo

## 5. Hạn chế & Hướng phát triển
- Corpus còn nhỏ (30 VB), cần mở rộng
- Gold set 50 câu có thể chưa đủ đa dạng
- Chưa test với multi-turn conversation
```
