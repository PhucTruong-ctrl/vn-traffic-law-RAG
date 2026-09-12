# Conversation Session Specification

> **Implementation status:** This document describes the active authenticated
> chat/session contract. The original React-only, non-persistent behavior
> described below is historical and has been superseded.

## Problem Statement

Người dùng trước đây chỉ có một chat stateful trong thời gian trang còn mở.
Mỗi request chỉ gửi `question`; lịch sử chỉ tồn tại trong React state, không có
conversation identifier, persistence, hoặc sidebar history.

Vì vậy người dùng không thể:

- tiếp tục một đoạn chat sau khi reload;
- chuyển đổi giữa nhiều đoạn chat độc lập;
- để hệ thống dùng context của đúng đoạn chat;
- tìm kiếm, đổi tên hoặc xóa đoạn chat;
## Solution

Server-side Conversation and Message records are owned by the authenticated Supabase user and stored through the existing `chat_sessions` table. On the first submit, the frontend renders the user message, creates the conversation through `POST /api/v1/chats`, and updates the route to `/chat/:conversation_id` with Next.js client navigation. It then sends `POST /api/v1/chat` with that `session_id`; later requests reuse the active identifier. The chat endpoint persists user and assistant messages through Supabase REST, including the response, citations, and metadata JSON fields used for reload and audit.

Frontend uses `/chat` for a new chat and `/chat/:conversation_id` for an open conversation. The first submit updates the browser URL with `history.pushState` after session creation, preserving the mounted React tree, optimistic user message, and assistant loading state while `POST /api/v1/chat` runs. Sidebar selection and explicit new-chat actions still use Next.js client routing.

The backend currently exposes these API routes: `POST /api/v1/chat`, `GET|POST /api/v1/chats`, `GET|PATCH|DELETE /api/v1/chats/{session_id}`, and `POST /api/v1/chats/{session_id}/messages`; saved Q&A uses `/api/v1/bookmarks`. Chat responses return the same identifier as `session_id`, `conversation_id`, and `chat_id` for client compatibility. Hydration reads the persisted transcript and does not call the model. An unmatched persisted user message is an interrupted turn, not legal `INSUFFICIENT_EVIDENCE`; the frontend restores its text for retry instead of rendering a false legal abstention.


The answer pipeline retrieves hybrid dense/BM25 candidates from Qdrant, applies the deterministic Evidence Completeness Gate and verified-or-abstain contract, and uses one OpenRouter generator only for evidence-backed answers. Failed or unverified assistant results must not become context.

> **Historical design note:** The following earlier proposal used anonymous
> HttpOnly-cookie ownership. The active implementation instead requires a
> Supabase Auth bearer token and scopes all chat/session reads and writes by
> authenticated user id. Keep the cookie proposal only as historical
> provenance; it is not an active contract.

Khi gửi câu hỏi mới, workflow sử dụng các message gần nhất trong conversation trong giới hạn token. Answer chỉ được hiển thị theo contract verified-or-abstain hiện tại; message chưa qua verification không được trở thành context hợp lệ.

## User Stories

1. As a người dùng cuối, I want to bắt đầu một chat mới, so that câu hỏi mới không dùng nhầm lịch sử conversation cũ.
2. As a người dùng cuối, I want to có conversation mới chỉ khi gửi câu hỏi đầu tiên, so that sidebar không chứa các chat rỗng.
3. As a người dùng cuối, I want to tiếp tục conversation đang mở, so that hệ thống hiểu context các lượt trước.
4. As a người dùng cuối, I want to reload conversation, so that transcript không bị mất khi refresh trang.
5. As a người dùng cuối, I want to mở conversation bằng deep link, so that tôi có thể quay lại đúng chat.
6. As a người dùng cuối, I want to dùng nút “Cuộc trò chuyện mới”, so that UI trở về composer rỗng.
7. As a người dùng cuối, I want to chọn conversation từ sidebar, so that tôi chuyển chat mà không trộn transcript.
8. As a người dùng cuối, I want to thấy title của từng conversation, so that tôi nhận biết chat cần mở.
9. As a người dùng cuối, I want to title ban đầu lấy từ message đầu tiên, so that chat có tên hữu ích ngay mà không phát sinh model call.
10. As a người dùng cuối, I want to title được normalize và giới hạn độ dài, so that sidebar giữ layout ổn định.
11. As a người dùng cuối, I want to đổi tên conversation, so that title phản ánh mục đích chat tốt hơn.
12. As a người dùng cuối, I want to title thủ công không bị tự động ghi đè, so that rename của tôi được giữ nguyên.
13. As a người dùng cuối, I want to tìm kiếm theo title hoặc câu hỏi đã gửi, so that tôi tìm lại conversation nhanh.
14. As a người dùng cuối, I want to search không trả conversation đã xóa, so that kết quả phản ánh dữ liệu đang khả dụng.
15. As a người dùng cuối, I want to xóa conversation, so that tôi loại bỏ chat không còn cần.
16. As a người dùng cuối, I want to delete có xác nhận, so that thao tác nhầm khó xảy ra.
17. As a người dùng cuối, I want to conversation đã xóa biến mất khỏi list/search/context ngay, so that dữ liệu bị xóa không tiếp tục xuất hiện.
18. As a người dùng cuối, I want to không có mục restore trong MVP, so that giao diện giữ đơn giản.
19. As a người dùng cuối, I want to conversation được sort theo hoạt động message mới nhất, so that chat đang sử dụng nằm trên đầu.
22. As a người dùng cuối, I want to scroll sidebar để tải thêm conversation, so that lịch sử dài vẫn truy cập được.
23. As a người dùng cuối, I want to thấy trạng thái assistant đang xử lý, so that tôi biết request chưa hoàn tất.
24. As a người dùng cuối, I want to request lỗi vẫn giữ câu hỏi của tôi, so that tôi có thể retry thay vì mất dữ liệu.
25. As a người dùng cuối, I want to answer failed không được đưa vào context, so that câu trả lời lỗi không làm nhiễu lượt sau.
26. As a người dùng cuối, I want to chỉ thấy answer sau evidence verification, so that conversation giữ đúng verified-or-abstain.
27. As a người dùng cuối, I want to xem citation và abstention như chat hiện tại, so that session feature không làm mất an toàn pháp lý.
28. As a người dùng cuối, I want to context dùng message gần nhất trong token budget, so that chat dài vẫn hoạt động ổn định.
29. As a người dùng cuối, I want to mở chat không tự gọi model, so that chỉ hành động gửi message mới tạo chi phí và answer.
30. As a người dùng cuối, I want to hai client anonymous không đọc lẫn conversation, so that dữ liệu chat được cô lập theo owner.
31. As a người dùng cuối, I want to owner identity được duy trì qua request, so that conversation vẫn thuộc cùng client sau reload.
32. As a người dùng cuối, I want to API trả conversation identifier khi lazy-create, so that frontend có thể cập nhật URL và sidebar.
33. As a người dùng cuối, I want to SSE và POST fallback dùng cùng conversation identifier, so that retry không tạo nhầm chat khác.
34. As a người dùng cuối, I want to gửi message vào conversation không thuộc owner bị từ chối, so that authorization isolation được bảo vệ.
35. As a người dùng cuối, I want to mở conversation không tồn tại hoặc đã xóa nhận lỗi rõ ràng, so that UI không hiển thị transcript sai.
- Supabase REST là nguồn chân lý cho `chat_sessions`, `messages`, feedback và
  bookmarks; không dùng localStorage làm persistence chính. PostgreSQL ở đây
  là hạ tầng do Supabase quản lý, không phải PostgreSQL app-owned runtime.
39. As a người dùng cuối, I want to assistant trace liên kết đúng lượt trả lời, so that citation và verification có thể audit theo message.
40. As a người dùng cuối, I want to các conversation cũ không bị reorder khi chỉ hydrate, so that việc xem lịch sử không tạo hoạt động giả.

## Implementation Decisions

- Canonical domain term là **Conversation**, không dùng `session` để tránh nhầm với browser/auth session.
- Thêm hai aggregate chính: Conversation và Message. Conversation có owner, title, timestamps hoạt động và soft-delete marker. Message thuộc đúng một Conversation, có role user/assistant, content, status và timestamp.
- Ownership dùng user id từ Supabase Auth bearer token; mọi read/write
  conversation đều lọc theo user id. Client mới tạo lazy conversation bằng
  `POST /api/v1/chat` khi request không có `session_id`; request có id append
  vào conversation hiện hữu. Runtime không có SSE endpoint.
- API phải hỗ trợ list conversations, lấy transcript một conversation, gửi message vào conversation, đổi title và soft-delete. Các read operation loại conversation đã soft-delete; write operation kiểm tra ownership và trạng thái tồn tại.
- `/chat` là new-chat surface; `/chat/:conversation_id` là active conversation surface. Hydration chỉ đọc transcript, không tự khởi chạy workflow.
- Title mặc định lấy từ user message đầu tiên, trim và normalize whitespace, sau đó truncate theo giới hạn hiển thị khoảng 60–80 ký tự. Title do user rename được đánh dấu/giữ riêng và không bị tự động cập nhật.
- Rename nhận title 1–200 ký tự sau trim; blank và input vượt giới hạn bị reject.
- `last_activity_at` chỉ cập nhật khi user message hoặc assistant result được persist. Open, hydrate, search và rename không cập nhật activity. List sort activity giảm dần với tie-break deterministic.
- Message persistence state machine là `PENDING -> COMPLETED | FAILED`. User message được persist trước workflow; assistant message pending được tạo cho request đang chạy. Chỉ result đã đi qua verification mới được coi là assistant context hợp lệ.
- QueryTrace vẫn là audit/evidence record theo request. Trace liên kết với assistant message; citations, verification summary và provenance không bị duplicate thành nguồn dữ liệu pháp lý thứ hai trong transcript.
- Context builder nhận ordered, non-deleted, usable messages gần nhất trong token budget. Canonical date policy, temporal filtering, Evidence Completeness Gate, verification sáu tầng và verified-or-abstain vẫn áp dụng độc lập cho mỗi lượt.
- Search MVP tìm case-insensitive trong title và user messages; loại soft-deleted conversation và failed assistant content khỏi kết quả. Kết quả sort theo activity mới nhất.
- Delete là soft-delete. Conversation bị loại ngay khỏi list, search, transcript access và context. MVP không có Recently Deleted hoặc restore UI.
- Đăng nhập, đăng ký và session Supabase Auth là một phần của runtime hiện tại;
  account profile/multi-device synchronization vẫn ngoài phạm vi Conversation.
- UI dùng kebab/action menu cho rename và delete; delete có confirmation. Mobile dùng drawer/sidebar responsive; desktop dùng sidebar hiện hữu.
- Không thêm small-model title generation trong MVP. Supabase Auth cung cấp
  identity hiện tại; không thêm auth account model riêng cho Conversation.
- Migration/schema Supabase phải bảo đảm foreign keys, ownership filtering,
  soft-delete semantics, timestamp ordering và cascade behavior không làm mất
  audit trace ngoài ý muốn.

## Testing Decisions

- Test observable behavior, không test implementation details, private helpers, ORM field copying hoặc component internals.
- Các API hiện tại dùng bearer token Supabase Auth; mọi retry phải giữ
  `session_id` để không tạo conversation trùng. Frontend có timeout mặc định
  120 giây qua `NEXT_PUBLIC_CHAT_TIMEOUT_MS`.
- Bổ sung API behavior tests theo prior art trong bộ test chat hiện tại; mỗi test nên thất bại nếu thay đổi làm lẫn conversation, bỏ ownership check, trả answer pending, hoặc đưa deleted/failed content vào context.
- Frontend seam chính là Playwright user flow trên page thật. Tests phải thao tác như người dùng và kiểm tra transcript/sidebar/URL hiển thị: new chat, chọn chat, reload/deep-link, lazy loading, search, rename, delete confirmation, loading/failure và verified/abstained rendering.
- Test boundaries gồm: owner khác nhau qua Supabase Auth, conversation không
  tồn tại, conversation đã xóa, title blank/200/201 ký tự, first message dài,
  empty sidebar, duplicate retry, pending assistant, failed assistant, equal
  activity timestamps và search không match.
- Migration/integration check phải chạy trên database test thật hoặc fixture tương đương repository convention, chứng minh foreign key/soft-delete/query ordering qua API behavior thay vì chỉ kiểm tra schema text.
- Không cần test small-model title generation vì quyết định MVP không dùng model title.
- Verification focused trước; sau đó chạy repository-required backend và frontend checks trên merged phase theo quy định dự án.

## Out of Scope

- Account profile, multi-device account synchronization và user management vẫn
  ngoài phạm vi Conversation; đăng nhập/đăng ký Supabase Auth là runtime
  prerequisite chứ không phải một tính năng Conversation.
- Khôi phục conversation đã xóa hoặc Recently Deleted UI.
- Hard-delete, retention scheduler, data export và account erasure workflow.
- Small model hoặc LLM tự động sinh title.
- Full-text search ranking, semantic search, assistant-message search và search analytics.
- Cookie ownership và SSE được giữ như các hướng thiết kế lịch sử; runtime hiện
  tại dùng bearer-authenticated POST `/api/v1/chat`, không có SSE endpoint.
- Conversation folders, pin, archive riêng biệt, tags, projects và bulk actions.
- Message edit, message delete từng message, regenerate, branching conversation và response versioning.
- Summary model cho conversation dài; chỉ dùng recent messages trong token budget.
- Voice, mobile app và thay đổi phạm vi UI chat-only đã được docs xác định.
- Thay đổi legal corpus, retrieval algorithm, canonical date policy, citation
  rendering, verifier, Evidence Completeness Gate hoặc historical RAGFlow
  baseline.
- Admin review UI và các P1/P0 khác không cần cho conversation history.

## Further Notes

- Frontend hiện dùng POST fallback trực tiếp tới `/api/v1/chat`; không có SSE
  endpoint trong runtime. Retry phải giữ cùng `session_id` để tránh duplicate.
- QueryTrace hiện có giá trị audit và feedback correlation. Liên kết trace với
  assistant message phải giữ nguyên khả năng feedback theo trace identifier.
- Khi frontend/backend khác origin, bearer token Supabase Auth và CORS phải
  được cấu hình đúng theo origin tin cậy. Không ghi raw conversation content
  vào logs hoặc telemetry.
- Spec này là synthesis từ glossary `CONTEXT.md`, thiết kế hệ thống, yêu cầu hệ thống và codebase hiện tại; không tạo Jira issue và không thay đổi các tài liệu scope freeze.