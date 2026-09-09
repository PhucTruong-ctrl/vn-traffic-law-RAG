# Conversation Session Specification

## Problem Statement

Người dùng hiện chỉ có một chat stateful trong thời gian trang còn mở. Mỗi request gửi duy nhất `question`; lịch sử câu hỏi và câu trả lời chỉ tồn tại trong React state, không có conversation identifier, không có persistence, và sidebar chưa hiển thị lịch sử thật.

Vì vậy người dùng không thể:

- tiếp tục một đoạn chat sau khi reload;
- chuyển đổi giữa nhiều đoạn chat độc lập;
- để hệ thống dùng context của đúng đoạn chat;
- tìm kiếm, đổi tên hoặc xóa đoạn chat;
- giữ thứ tự conversation theo hoạt động mới nhất.

Feature này vẫn thuộc nhóm P1 conversation history trong kế hoạch hiện tại; không thay đổi phạm vi P0, verified-or-abstain, canonical date policy, Evidence Completeness Gate hoặc citation invariants.

## Solution

Thêm domain Conversation và Message phía server, với anonymous ownership được xác định bằng HttpOnly cookie. Một conversation chỉ được tạo khi người dùng gửi message đầu tiên. Mỗi lượt chat được lưu thành user message và assistant message có trạng thái; QueryTrace hiện tại liên kết với assistant message để giữ audit, citation và verification metadata tách khỏi transcript.

Frontend dùng `/chat` làm màn hình chat mới và `/chat/:conversation_id` làm deep link cho conversation đang mở. Sidebar tải danh sách theo kích thước viewport, sắp xếp `last_activity_at` giảm dần, hỗ trợ chọn, tìm kiếm, đổi tên và soft-delete conversation.

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
20. As a người dùng cuối, I want to rename hoặc mở chat không làm thay đổi thứ tự activity, so that thứ tự phản ánh nội dung chứ không phải thao tác quản lý.
21. As a người dùng cuối, I want to sidebar lazy-load vừa đủ theo viewport, so that initial load không tải toàn bộ lịch sử.
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
36. As a người dùng cuối, I want to rename blank hoặc quá dài bị từ chối, so that dữ liệu title luôn hợp lệ.
37. As a người dùng cuối, I want to tìm kiếm không phân biệt hoa thường, so that kết quả phù hợp cách tôi nhập.
38. As a người dùng cuối, I want to search result vẫn sort theo activity mới nhất, so that tìm kiếm giữ hành vi sidebar nhất quán.
39. As a người dùng cuối, I want to assistant trace liên kết đúng lượt trả lời, so that citation và verification có thể audit theo message.
40. As a người dùng cuối, I want to các conversation cũ không bị reorder khi chỉ hydrate, so that việc xem lịch sử không tạo hoạt động giả.

## Implementation Decisions

- Canonical domain term là **Conversation**, không dùng `session` để tránh nhầm với browser/auth session.
- Thêm hai aggregate chính: Conversation và Message. Conversation có owner, title, timestamps hoạt động và soft-delete marker. Message thuộc đúng một Conversation, có role user/assistant, content, status và timestamp.
- Anonymous ownership dùng owner key do server cấp qua HttpOnly cookie. Mọi read/write conversation phải lọc theo owner key; không có global shared history.
- Conversation lifecycle là lazy-create. Request không có conversation identifier tạo Conversation khi user message đầu tiên được chấp nhận. Request có identifier append vào Conversation hiện hữu.
- Existing chat request contract được mở rộng bằng optional conversation identifier; client cũ không có identifier vẫn hoạt động theo lazy-create. SSE và POST fallback phải truyền cùng identifier.
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
- Sidebar tải trang đầu theo số conversation vừa đủ viewport và tải thêm khi cần; API pagination dùng cursor để không khóa thiết kế khi lịch sử tăng.
- UI dùng kebab/action menu cho rename và delete; delete có confirmation. Mobile dùng drawer/sidebar responsive; desktop dùng sidebar hiện hữu.
- Không thêm small-model title generation trong MVP. Không thêm auth account model nếu hệ thống chưa có identity provider; owner key giữ boundary để thay thế sau này.
- PostgreSQL là nguồn chân lý cho Conversation, Message và liên kết trace. Không dùng localStorage làm nguồn persistence chính.
- Migration phải bảo đảm foreign keys, ownership filtering, soft-delete semantics, timestamp ordering và cascade behavior không làm mất audit trace ngoài ý muốn.

## Testing Decisions

- Test observable behavior, không test implementation details, private helpers, ORM field copying hoặc component internals.
- Backend seam chính là HTTP API/workflow boundary hiện có. Tests phải chứng minh owner isolation, lazy-create, append, transcript hydration, context continuity, ID correlation giữa SSE/fallback, message state transitions, trace linkage, title generation/rename validation, search ordering và soft-delete visibility.
- Giữ các regression tests hiện tại của chat cho validation `question`, citation safety, verified response, abstention, disclaimer và feedback trace correlation.
- Bổ sung API behavior tests theo prior art trong bộ test chat hiện tại; mỗi test nên thất bại nếu thay đổi làm lẫn conversation, bỏ ownership check, trả answer pending, hoặc đưa deleted/failed content vào context.
- Frontend seam chính là Playwright user flow trên page thật. Tests phải thao tác như người dùng và kiểm tra transcript/sidebar/URL hiển thị: new chat, chọn chat, reload/deep-link, lazy loading, search, rename, delete confirmation, loading/failure và verified/abstained rendering.
- Mocks trong E2E chỉ mô phỏng network boundary; không assert implementation state hoặc số lần gọi helper. Response fixtures phải bao gồm conversation identifiers, timestamps, message roles và status để bắt lỗi mapping.
- Test boundaries gồm: anonymous owner khác nhau, conversation không tồn tại, conversation đã xóa, title blank/200/201 ký tự, first message dài, empty sidebar, duplicate retry, pending assistant, failed assistant, equal activity timestamps và search không match.
- Migration/integration check phải chạy trên database test thật hoặc fixture tương đương repository convention, chứng minh foreign key/soft-delete/query ordering qua API behavior thay vì chỉ kiểm tra schema text.
- Không cần test small-model title generation vì quyết định MVP không dùng model title.
- Verification focused trước; sau đó chạy repository-required backend và frontend checks trên merged phase theo quy định dự án.

## Out of Scope

- Đăng nhập, đăng ký, account profile, multi-device account sync và user management.
- Khôi phục conversation đã xóa hoặc Recently Deleted UI.
- Hard-delete, retention scheduler, data export và account erasure workflow.
- Small model hoặc LLM tự động sinh title.
- Full-text search ranking, semantic search, assistant-message search và search analytics.
- Conversation sharing, public links, collaboration và permissions ngoài owner isolation.
- Conversation folders, pin, archive riêng biệt, tags, projects và bulk actions.
- Message edit, message delete từng message, regenerate, branching conversation và response versioning.
- Summary model cho conversation dài; chỉ dùng recent messages trong token budget.
- Voice, mobile app và thay đổi phạm vi UI chat-only đã được docs xác định.
- Thay đổi legal corpus, retrieval algorithm, canonical date policy, citation rendering, verifier, Evidence Completeness Gate hoặc RAGFlow baseline.
- Admin review UI và các P1/P0 khác không cần cho conversation history.

## Further Notes

- Local design docs hiện đánh dấu conversation history là P1; triển khai chỉ nên tiến hành khi các P0 acceptance criteria theo kế hoạch đã đạt hoặc có quyết định scope riêng.
- Frontend hiện có SSE-first và POST fallback; cả hai đường phải tạo cùng observable conversation behavior, không để fallback sinh transcript duplicate.
- QueryTrace hiện có giá trị audit và feedback correlation. Liên kết trace với assistant message phải giữ nguyên khả năng feedback theo trace identifier.
- Cookie ownership cần cấu hình đúng khi frontend/backend khác origin: HttpOnly, Secure trong deployment phù hợp, SameSite theo topology, CORS credentials giới hạn origin tin cậy. Đây là security boundary, không phải UI detail.
- Không ghi raw conversation content vào logs hoặc telemetry ngoài dữ liệu cần cho workflow/audit hiện tại.
- Spec này là synthesis từ glossary `CONTEXT.md`, thiết kế hệ thống, yêu cầu hệ thống và codebase hiện tại; không tạo Jira issue và không thay đổi các tài liệu scope freeze.