# 01: Status taxonomy và response contract

**What to build:** Chat API và UI phân biệt greeting, ngoài phạm vi, thiếu corpus, thiếu evidence, lỗi vận hành và verified result; không còn gán mọi non-verified response thành `INSUFFICIENT_EVIDENCE`.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Greeting như `Hello gemini` trả trạng thái/UX greeting riêng và không chạy retrieval.
- [ ] Câu hỏi ngoài domain trả `OUT_OF_SCOPE`.
- [ ] Câu hỏi giao thông ngoài 14-PDF corpus trả `CORPUS_NOT_COVERED`.
- [ ] Thiếu evidence trả `INSUFFICIENT_EVIDENCE` kèm evidence gap.
- [ ] Workflow/provider failure trả error code riêng, không giả thành legal abstention.
- [ ] Verified response tiếp tục yêu cầu citation hợp lệ.
- [ ] Existing chat API behavior tests cover every public status.
