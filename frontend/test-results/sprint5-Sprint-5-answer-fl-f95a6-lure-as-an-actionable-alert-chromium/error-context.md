# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: sprint5.spec.ts >> Sprint 5 answer flow >> renders an API failure as an actionable alert
- Location: e2e/sprint5.spec.ts:27:7

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: locator.click: Test timeout of 30000ms exceeded.
Call log:
  - waiting for getByRole('button', { name: 'Gửi', exact: true })
    - locator resolved to <button disabled type="submit" aria-label="Gửi">…</button>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is not enabled
    - retrying click action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and stable
      - element is not enabled
    - retrying click action
      - waiting 100ms
    56 × waiting for element to be visible, enabled and stable
       - element is not enabled
     - retrying click action
       - waiting 500ms
    - waiting for element to be visible, enabled and stable

```

# Page snapshot

```yaml
- generic [ref=e1]:
  - main [ref=e2]:
    - complementary "Lịch sử trò chuyện" [ref=e3]:
      - generic [ref=e4]:
        - link "Trợ lý Luật Giao thông" [ref=e5] [cursor=pointer]:
          - /url: "#"
          - generic [ref=e7]: §
          - generic [ref=e8]: Luật Giao thông
        - button "Thu gọn thanh bên" [ref=e9] [cursor=pointer]
      - button "Cuộc trò chuyện mới" [ref=e12] [cursor=pointer]
      - navigation "Điều hướng" [ref=e16]:
        - button "Tìm kiếm" [ref=e17] [cursor=pointer]
        - button "Nguồn pháp luật" [ref=e22] [cursor=pointer]
      - generic [ref=e26]:
        - paragraph [ref=e27]: Gần đây
        - button "Cuộc trò chuyện mới" [ref=e28] [cursor=pointer]
        - button "Mức phạt khi vượt đèn đỏ là bao nhiêu?" [ref=e29] [cursor=pointer]
        - button "Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?" [ref=e30] [cursor=pointer]
      - generic [ref=e31]:
        - generic [aria-hidden] [ref=e32]: ND
        - generic [ref=e33]:
          - generic [ref=e34]: Người dùng
          - generic [ref=e35]: Trợ lý pháp luật
        - button "Cài đặt" [ref=e36] [cursor=pointer]: •••
    - region "Khu vực tra cứu" [ref=e37]:
      - generic [ref=e38]:
        - button "Trợ lý Luật Giao thông" [ref=e39] [cursor=pointer]
        - group "Giao diện" [ref=e42]:
          - generic [ref=e44]:
            - radio "Tự động" [checked] [ref=e45]
            - generic [ref=e46]: Tự động
          - generic [ref=e47]:
            - radio "Sáng" [ref=e48]
            - generic [ref=e49]: Sáng
          - generic [ref=e50]:
            - radio "Tối" [ref=e51]
            - generic [ref=e52]: Tối
      - generic [ref=e54]:
        - generic [ref=e56]: §
        - heading "Hỏi đáp pháp luật giao thông" [level=1] [ref=e57]
        - paragraph [ref=e58]: Hỏi rõ điều bạn cần biết. Mỗi câu trả lời đều kèm căn cứ để kiểm tra.
        - generic [ref=e59]:
          - generic [ref=e60]: Câu hỏi
          - textbox "Câu hỏi" [active] [ref=e61]:
            - /placeholder: Bạn muốn hỏi điều gì?
            - text: Câu hỏi kiểm tra lỗi
          - generic [ref=e62]:
            - generic [ref=e63]: Luật giao thông
            - button "Gửi" [disabled] [ref=e64]
        - generic "Gợi ý" [ref=e67]:
          - button "Mức phạt khi vượt đèn đỏ là bao nhiêu?" [ref=e68] [cursor=pointer]
          - button "Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?" [ref=e69] [cursor=pointer]
          - button "Có được dùng điện thoại khi đang lái xe không?" [ref=e70] [cursor=pointer]
  - button "Open Next.js Dev Tools" [ref=e76] [cursor=pointer]
```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  | 
  3  | test.describe("Sprint 5 answer flow", () => {
  4  |   test.describe.configure({ mode: "serial" });
  5  | 
  6  |   test("renders the chat-only home form and validates a blank question", async ({ page }) => {
  7  |     await page.goto("/");
  8  |     await expect(page.getByRole("heading", { name: "Hỏi đáp pháp luật giao thông" })).toBeVisible();
  9  |     await expect(page.getByLabel("Câu hỏi")).toBeVisible();
  10 |     await expect(page.getByText("Phạm vi tra cứu")).toHaveCount(0);
  11 |     await expect(page.getByRole("button", { name: "Gửi", exact: true })).toBeDisabled();
  12 |   });
  13 | 
  14 |   test("submits only the chat question and renders a verified response", async ({ page }) => {
  15 |     await page.route("**/api/v1/chat", async (route) => {
  16 |       expect(route.request().postDataJSON()).toEqual({ question: "Vượt đèn đỏ bị phạt thế nào?" });
  17 |       await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "VERIFIED", answer: "Mức phạt được xác định theo quy định hiện hành.", claims: [{ claim: "Có căn cứ pháp lý", claim_type: "RULE" }], citations: [{ provision_id: "nd-100-2019:article-6", document_number: "Nghị định 100/2019/NĐ-CP", article: "Điều 6" }], disclaimer: "This response is informational and not legal advice.", trace_id: "trace-smoke-verified" }) });
  18 |     });
  19 |     await page.goto("/");
  20 |     await page.getByLabel("Câu hỏi").fill("Vượt đèn đỏ bị phạt thế nào?");
  21 |     await page.getByRole("button", { name: "Gửi", exact: true }).click();
  22 |     await expect(page.getByText("Đã kiểm chứng")).toBeVisible();
  23 |     await expect(page.getByText("Mức phạt được xác định theo quy định hiện hành.")).toBeVisible();
  24 |     await expect(page.getByText("Nghị định 100/2019/NĐ-CP")).toBeVisible();
  25 |   });
  26 | 
  27 |   test("renders an API failure as an actionable alert", async ({ page }) => {
  28 |     await page.route("**/api/v1/chat", async (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { message: "Dịch vụ tạm thời không khả dụng" } }) }));
  29 |     await page.goto("/");
  30 |     await page.getByLabel("Câu hỏi").fill("Câu hỏi kiểm tra lỗi");
> 31 |     await page.getByRole("button", { name: "Gửi", exact: true }).click();
     |                                                                  ^ Error: locator.click: Test timeout of 30000ms exceeded.
  32 |     await expect(page.getByRole("alert", { name: "Lỗi truy vấn" })).toContainText("Dịch vụ tạm thời không khả dụng");
  33 |   });
  34 | 
  35 |   test("renders an abstention from the mock API boundary", async ({ page }) => {
  36 |     await page.route("**/api/v1/chat", async (route) => {
  37 |       await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ABSTAINED", answer: null, claims: [], citations: [], abstention: { reason_code: "INSUFFICIENT_EVIDENCE" }, trace_id: "trace-smoke-abstained" }) });
  38 |     });
  39 |     await page.goto("/");
  40 |     await page.getByLabel("Câu hỏi").fill("Một tình huống chưa có đủ dữ kiện?");
  41 |     await page.getByRole("button", { name: "Gửi", exact: true }).click();
  42 |     await expect(page.getByText("Chưa đủ căn cứ")).toBeVisible();
  43 |     await expect(page.getByText("Mã lý do:")).toBeVisible();
  44 |     await expect(page.getByText("INSUFFICIENT_EVIDENCE")).toBeVisible();
  45 |     await expect(page.getByText("Không thể đưa ra kết luận chắc chắn cho câu hỏi này.")).toBeVisible();
  46 |   });
  47 | 
  48 |   test("shows the submitted question in the chat loading bubble", async ({ page }) => {
  49 |     let releaseResponse!: () => void;
  50 |     const responseReady = new Promise<void>((resolve) => { releaseResponse = resolve; });
  51 |     await page.route("**/api/v1/chat", async (route) => { await responseReady; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "VERIFIED", answer: "Đã xong.", claims: [], citations: [] }) }); });
  52 |     await page.goto("/");
  53 |     await page.getByLabel("Câu hỏi").fill("Không đội mũ bảo hiểm bị phạt thế nào?");
  54 |     await page.getByRole("button", { name: "Gửi", exact: true }).click();
  55 |     await expect(page.getByRole("status")).toContainText("Không đội mũ bảo hiểm bị phạt thế nào?");
  56 |     await expect(page.locator(".loading-bar")).toBeVisible();
  57 |     releaseResponse();
  58 |   });
  59 | });
  60 | 
  61 | test.describe("Delayed response accessibility", () => {
  62 |   test("shows neutral in-flight status while a chat response is pending", async ({ page }) => {
  63 |     let releaseResponse!: () => void;
  64 |     const responseReady = new Promise<void>((resolve) => { releaseResponse = resolve; });
  65 |     await page.route("**/api/v1/chat", async (route) => { await responseReady; await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "VERIFIED", answer: "Kết quả sau khi chờ.", claims: [], citations: [], trace_id: "trace-delayed" }) }); });
  66 |     await page.goto("/");
  67 |     await page.getByLabel("Câu hỏi").fill("Tra cứu khi phản hồi chậm");
  68 |     await page.getByRole("button", { name: "Gửi", exact: true }).click();
  69 |     const status = page.getByRole("status");
  70 |     await expect(status).toContainText("Đang chuẩn bị tra cứu");
  71 |     await expect(status).toHaveAttribute("aria-live", "polite");
  72 |     await expect(page.getByRole("button", { name: "Đang tra cứu..." })).toBeDisabled();
  73 |     releaseResponse();
  74 |     await expect(page.getByText("Kết quả sau khi chờ.")).toBeVisible();
  75 |   });
  76 | });
  77 | 
```