# Manual Release Checklist

Record date, browser, result, and evidence path beside every item. Leave unchecked until observed in a real browser.

## Auth

- [ ] Register — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Confirmation-required message — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Login — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Logout — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Reload restores session — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Expired-token state — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Protected chat gate/redirect — Date: ____ Browser: ____ Result: ____ Evidence: ____

## Chat

- [ ] Five demo queries — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Follow-up/history — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Rename/delete — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Feedback — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Chat retry/failure state — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Saved Q&A — from a completed answer, save it, verify **Đã lưu** shows question/answer/citations, search finds it, reload preserves it, and delete removes it — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Chat timeout exits loading with answer or explicit failure within configured limit (default 120 seconds; `NEXT_PUBLIC_CHAT_TIMEOUT_MS` override) — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Chat session visibility after submit/reload — conversation remains in history and the question plus final answer/clarification are visible after reopening — Date: ____ Browser: ____ Result: ____ Evidence: ____

## Citation

- [ ] Citation opens source drawer — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Markdown highlight/navigation — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] PDF page navigation — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Missing page omits page label/jump — Date: ____ Browser: ____ Result: ____ Evidence: ____

## Legal Explorer

- [ ] Document detail/provisions load — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Exact hierarchy search — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Provision selection highlights content — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Detail/search retry and empty states — Date: ____ Browser: ____ Result: ____ Evidence: ____

## Failure states

- [ ] Qdrant unavailable returns readiness failure — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Supabase unavailable returns readiness failure — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Generation failure returns safe 503 — Date: ____ Browser: ____ Result: ____ Evidence: ____
- [ ] Unauthorized resource returns concealed 404 — Date: ____ Browser: ____ Result: ____ Evidence: ____
