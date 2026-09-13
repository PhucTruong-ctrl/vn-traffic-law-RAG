# Báo cáo đánh giá API subset 32 case — 2026-09-13

## Phạm vi

Chạy 32/40 case (4 case đầu mỗi category trong 8 category) trực tiếp qua `POST /api/v1/chat`, không qua giao diện. Đây là subset đại diện theo category, không phải full thesis evaluation.

| Thuộc tính          | Giá trị                                      |
| ------------------- | -------------------------------------------- |
| Dataset nguồn       | `data/evaluation/thesis-gold-40.json`        |
| Số case             | 32/40                                        |
| Endpoint            | `http://127.0.0.1:8000/api/v1/chat`          |
| Qdrant collection   | `traffic_law_enriched_20260913_v3`           |
| top-k               | 5                                            |
| Backend readiness   | Supabase và Qdrant đều `true` trước khi chạy |
| API errors/timeouts | 3 case lỗi                                   |
| Semantic review     | Chưa thực hiện                               |

## Kết quả

| Metric                      |      Kết quả |
| --------------------------- | -----------: |
| `retrieval_hit_at_k`        |       0.1905 |
| `document_accuracy`         |       0.2381 |
| `article_accuracy`          |       0.2381 |
| `clause_accuracy`           |       0.2500 |
| `point_accuracy`            |       0.1429 |
| `citation_validity`         |       0.6552 |
| `abstention_accuracy`       |       0.4483 |
| `answer_correctness_manual` |         null |
| Latency mean                | 29,002.83 ms |
| Latency P50                 | 26,925.06 ms |
| Latency P95                 | 84,036.78 ms |

## Theo category

| Category                |   n | Retrieval hit | Citation validity | Abstention accuracy |
| ----------------------- | --: | ------------: | ----------------: | ------------------: |
| `cross_reference`       |   4 |          0.00 |              0.00 |                0.00 |
| `exact_reference`       |   4 |          0.25 |              0.50 |                0.50 |
| `follow_up`             |   4 |          0.00 |              1.00 |                1.00 |
| `insufficient_evidence` |   4 |          null |              1.00 |                0.00 |
| `multi_intent`          |   4 |          0.00 |              0.00 |                0.00 |
| `natural_language`      |   4 |          0.00 |              1.00 |                1.00 |
| `out_of_scope`          |   4 |          null |              1.00 |                0.50 |
| `penalty`               |   4 |          1.00 |              1.00 |                1.00 |

## API errors

- `thesis-gold-40-27`
- `thesis-gold-40-06`
- `thesis-gold-40-12`

Các case lỗi có `prediction = null`; không suy diễn trạng thái hay correctness.

## Disposition

**UNVERIFIED / NOT RELEASE-READY.** Subset đạt mục tiêu phạm vi chạy 70–80% case nhưng không đạt release-quality threshold:

- 3/32 API calls lỗi;
- citation validity 65.52%;
- abstention accuracy 44.83%;
- semantic correctness chưa review;
- P95 latency 84 giây.

Không dùng subset này để tuyên bố full 40-case pass hoặc release-ready. Raw subset được giữ ngoài Git artifact output của one-off run; report này chỉ ghi kết quả console đã quan sát.
