# 10: Minimal anonymous LIKE/DISLIKE feedback

**What to build:** Người dùng đánh giá answer bằng like/dislike; hệ thống lưu tín hiệu tối thiểu theo trace mà không thu thập comment/PII.

**Blocked by:** 01-query-status/issue.md.

**Status:** ready-for-agent

- [ ] UI exposes accessible LIKE and DISLIKE controls per answer.
- [ ] API accepts only the two rating values plus trace/message reference.
- [ ] Persistence stores minimal anonymous metadata and no raw prompt/answer, comment, category, identity, IP, device or PII.
- [ ] Feedback failure never affects answer delivery or verification.
- [ ] Feedback cannot mutate corpus, index, prompt, model, gold set or release state.
- [ ] Existing feedback tests cover valid ratings, unknown traces and extra-field rejection.
