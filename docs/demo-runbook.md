# VNLAW demo runbook

This runbook defines five fixed, reproducible checks for the local development stack. Start FastAPI on `127.0.0.1:8000` and Next.js on `127.0.0.1:3000` with the repository's normal development command, then open `http://127.0.0.1:3000/chat`. The frontend calls `${NEXT_PUBLIC_API_URL}/api/v1` (`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` locally unless an intentional deployment override is configured). Supabase Auth must provide a logged-in session, and Qdrant must contain the `traffic_law` collection. Do not include account tokens, passwords, API keys, or raw identifiers in captures.

## Fixed scenarios

| ID | Question | Expected observable behavior | Observed status |
| --- | --- | --- | --- |
| G | `Xin chào` | The assistant returns a conversational greeting with status `GREETING` and no legal citation. | Record the rendered response and status. A malformed/5xx response is a failure, not a greeting. |
| R | `Mức phạt khi vượt đèn đỏ là bao nhiêu?` | The assistant requests vehicle class before selecting the applicable legal rule; the conversation remains in the same conversation identified by the returned `session_id`/`conversation_id`. | Record clarification and identifier correlation. |
| P | `Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?` | A natural-language penalty question returns a grounded answer with an applicable citation. | Run after the stack is healthy. Record whether an answer and citation are shown, and note qualitative latency (`immediate`, `a few seconds`, or `did not complete`). |
| M | `Tôi vượt đèn đỏ bằng xe máy và không đội mũ bảo hiểm; bị phạt bao nhiêu?` | Multiple intents are separated or clarified rather than collapsed into one unsupported penalty. | Run after the stack is healthy. Record the observed clarification/answer and qualitative latency. |
| A | `Thời tiết Hà Nội ngày mai thế nào?` | The system abstains or states that the request is outside traffic-law scope; it must not fabricate a legal answer. | Run after the stack is healthy. Record the abstention wording and qualitative latency. |

## Capture workflow

1. Start the normal development stack and verify that both the chat route and legal-sources route load.
2. For each row, start a new conversation, paste the exact question, submit it, and wait for the final rendered state.
3. Capture the rendered legal answer or clarification and any visible citation or source panel. Use the browser's full-page screenshot. Crop only when the crop still includes the question, answer state, and citation.
4. Open **Nguồn pháp luật** and capture the explorer/source list as a separate evidence image. Return to the chat and reload the same conversation to show persistence, then capture that state too.
5. Save non-empty image files under `docs/assets/`. Current evidence: [`demo-greeting.webp`](assets/demo-greeting.webp) shows the live greeting error state, and [`demo-exact-reference.webp`](assets/demo-exact-reference.webp) shows the live red-light clarification state. These are actual UI captures, not placeholders.
6. In the evaluation notes, report statuses and latency qualitatively only. Do not infer or publish numeric timing from screenshots.
7. Verify durable saved Q&A separately. On a completed assistant response, click **Lưu câu trả lời**, open **Đã lưu**, confirm that the question, answer, and citations are present, use the search field, remove the item, and confirm that it disappears. Reload the page, and where applicable the source conversation, to confirm that the saved snapshot remains available independently of chat history. Record failures. A bookmark icon changing state alone does not demonstrate persistence.
8. For chat timeout and session visibility, submit a question and wait up to the configured client timeout (default 120 seconds; `NEXT_PUBLIC_CHAT_TIMEOUT_MS` may override it). Confirm that the UI leaves loading and shows either the answer or an explicit failure state. During and after submission, confirm that the conversation remains visible in history, then reload the same conversation to verify that the question and final response or clarification are still shown. Capture browser console/network and backend evidence for any `NetworkError`, timeout, or missing session, with tokens and session identifiers redacted.

## Reproducibility notes

- The exact strings above are the evaluation inputs; preserve Vietnamese diacritics.
- A server/API error is a failed observation, not a passing abstention. Record it verbatim and rerun after recovery.
- A valid citation must be visibly tied to the answer through a document or rule reference and a source action, not merely a generic “sources available” label.
- Persistence is demonstrated only when the same conversation can be reopened or reloaded and its question plus response or clarification remain visible.