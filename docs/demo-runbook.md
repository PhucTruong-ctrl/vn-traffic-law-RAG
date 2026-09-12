# VNLAW demo runbook

This runbook records five fixed, reproducible checks against the local development stack. Run the API and web app with the repository's normal `dev.sh`, open `http://127.0.0.1:3000/chat`, and use a clean conversation for each scenario. Do not include account tokens, passwords, API keys, or raw session identifiers in captures.

## Fixed scenarios

| ID | Question | Expected observable behavior | Observed status |
| --- | --- | --- | --- |
| G | `Xin chào` | A greeting is handled conversationally without inventing a legal citation. | The current server returned `Phản hồi từ máy chủ không hợp lệ. Vui lòng thử lại.`; retain this as a visible failure until the stack is healthy. |
| R | `Mức phạt khi vượt đèn đỏ là bao nhiêu?` | The assistant requests vehicle class before selecting the applicable legal rule; the conversation remains in the same session. | The current UI displayed `Bạn đang hỏi về loại phương tiện nào?` with choices `ô tô`, `xe mô tô, xe gắn máy`, and `xe thô sơ` (successful clarification). |
| P | `Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?` | A natural-language penalty question returns a grounded answer with an applicable citation. | Run after the stack is healthy; record whether an answer and citation are shown, and note qualitative latency (`immediate`, `a few seconds`, or `did not complete`). |
| M | `Tôi vượt đèn đỏ bằng xe máy và không đội mũ bảo hiểm; bị phạt bao nhiêu?` | Multiple intents are separated or clarified rather than collapsed into one unsupported penalty. | Run after the stack is healthy; record the observed clarification/answer and qualitative latency. |
| A | `Thời tiết Hà Nội ngày mai thế nào?` | The system abstains or states that the request is outside traffic-law scope; it must not fabricate a legal answer. | Run after the stack is healthy; record the abstention wording and qualitative latency. |

## Capture workflow

1. Start the normal development stack and verify both the chat route and legal-sources route load.
2. For each row, start a new conversation, paste the exact question, submit, and wait for the final rendered state.
3. Capture the rendered legal answer/clarification and any visible citation or source panel. Use the browser's full-page screenshot; crop only if cropping does not remove the question, answer state, or citation.
4. Open **Nguồn pháp luật** and capture the explorer/source list as a separate evidence image. Then return to the chat and reload the same conversation to show persistence; capture that state too.
5. Save non-empty image files under `docs/assets/`. Current evidence: [`demo-greeting.webp`](assets/demo-greeting.webp) shows the live greeting error state, and [`demo-exact-reference.webp`](assets/demo-exact-reference.webp) shows the live red-light clarification state. These are actual UI captures, not placeholders.
6. In the evaluation notes, report statuses and latency qualitatively only. Do not infer or publish numeric timing from screenshots.
7. Verify durable saved Q&A separately: on a completed assistant response, click **Lưu câu trả lời**, open **Đã lưu**, confirm the question, answer, and citations are present, use the search field, then remove the item and confirm it disappears. Reload the page (and, where applicable, the source conversation) to confirm the saved snapshot remains available independently of chat history. Record failures; do not treat a bookmark icon changing state alone as persistence.
8. For chat timeout/session visibility, submit a question and wait up to the configured client timeout (default 120 seconds; `NEXT_PUBLIC_CHAT_TIMEOUT_MS` may override it). Confirm the UI leaves loading and shows either the answer or an explicit failure state. During and after submission, confirm the conversation remains visible in history and reload the same conversation to verify the question and final response/clarification are still shown. Capture browser console/network and backend evidence for any `NetworkError`, timeout, or missing session, with tokens and session identifiers redacted.

## Reproducibility notes

- The exact strings above are the evaluation inputs; preserve Vietnamese diacritics.
- A server/API error is a failed observation, not a passing abstention. Record it verbatim and rerun after recovery.
- A valid citation must be visibly tied to the answer (document/rule reference and source action), not merely a generic “sources available” label.
- Persistence is demonstrated only when the same conversation can be reopened or reloaded and its question plus response/clarification remain visible.
