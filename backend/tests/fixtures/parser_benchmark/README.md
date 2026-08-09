# Parser Benchmark Fixtures — Suite A (VNLRAG-24)

Bộ fixture cho Suite A parser benchmark và Legal Structure Extractor, theo
`docs/05-ke-hoach-trien-khai.md` W1 24-25/07 và `docs/06-test-evaluation.md`.

## Cấu trúc

```
tests/fixtures/parser_benchmark/
├── README.md                              # Tài liệu này
├── documents/                             # Fixture văn bản gốc (PDF born-digital + text extract)
│   ├── luat/  luat-traffic-2024-fixture.pdf(.txt)   # Luật Trật tự ATGTĐB 2024 (trích đoạn)
│   ├── nd/    nd-168-2024-fixture.pdf(.txt)         # NĐ 168/2024/NĐ-CP (trích đoạn)
│   └── tt/    tt-traffic-2024-fixture.pdf(.txt)     # TT 24/2024/TT-BGTVT (trích đoạn)
├── gold/                                  # Gold annotation cấu trúc
│   ├── luat-gold.json
│   ├── nd-gold.json
│   ├── tt-gold.json
│   ├── point_label_d_dd.json              # Nhãn Điểm d) vs đ) phân biệt
│   ├── short_point_annotation.json        # Short-Point retention
│   └── parent_context_annotation.json     # Parent-context expectations
└── golden-stable-id/
    └── stable_id_diem_d_dd.json           # Golden fixture stable-ID d/đ
```

## Ghi chú

- **Fixture là PDF born-digital thật** (có text layer, sinh từ nội dung `.pdf.txt`
  bằng reportlab — parser chạy được trên PDF này, thỏa Suite A P1-P3). File
  `.pdf.txt` giữ vai trò expected-text/extractor fixture để so sánh nhanh.
  Nội dung là trích đoạn hợp lý, **không phải** văn bản chính thức đầy đủ.
- **Yêu cầu gold** (docs/03 §3.8.5:1039-1054):
  - Phân cấp Điều → Khoản → Điểm;
  - Nhãn Điểm tiếng Việt đầy đủ `a) b) c) d) đ) e)` — **d) và đ) là hai nhãn
    riêng biệt**, ánh xạ `diem-d` / `diem-đ` (không va chạm, FR-03);
  - Short-Point hợp lệ phải được **giữ** (retained), không có ngưỡng độ dài;
  - `source_text` bất biến; `retrieval_text` có thể kế thừa ngữ cảnh cha.
- **provision_id** tuân theo regex schema đã commit
  (`templates/legal-provision.schema.json`).
- Dùng cho: Suite A (VNLRAG-97), Legal Structure Extractor (VNLRAG-26),
  IR adapters (VNLRAG-128/129/130 — W2).

## Kiểm tra

```bash
cd backend && uv run pytest tests/test_golden_fixture.py --no-cov -q
```
