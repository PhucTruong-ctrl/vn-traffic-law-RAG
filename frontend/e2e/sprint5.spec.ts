import { expect, test } from "@playwright/test";

test.describe("Sprint 5 answer flow", () => {
  test.describe.configure({ mode: "serial" });

  test("renders the chat-only home form and validates a blank question", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Hỏi đáp pháp luật giao thông" })).toBeVisible();
    await expect(page.getByLabel("Câu hỏi")).toBeVisible();
    await expect(page.getByText("Phạm vi tra cứu")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Gửi", exact: true })).toBeDisabled();
  });

  test("submits only the chat question and renders a verified response", async ({ page }) => {
    await page.route("**/api/v1/chat/events**", async (route) => {
      expect(new URL(route.request().url()).searchParams.get("question")).toBe(
        "Vượt đèn đỏ bị phạt thế nào?",
      );
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: result\ndata: ${JSON.stringify({
          status: "VERIFIED",
          answer: "Mức phạt được xác định theo quy định hiện hành.",
          claims: [{ claim: "Có căn cứ pháp lý", claim_type: "RULE" }],
          citations: [
            {
              provision_id: "nd-100-2019:article-6",
              document_number: "Nghị định 100/2019/NĐ-CP",
              article: "Điều 6",
            },
          ],
          disclaimer: "This response is informational and not legal advice.",
          trace_id: "trace-smoke-verified",
        })}\n\n`,
      });
    });
    await page.goto("/");
    await page.getByLabel("Câu hỏi").fill("Vượt đèn đỏ bị phạt thế nào?");
    await page.getByRole("button", { name: "Gửi", exact: true }).click();
    await expect(page.getByText("Đã đối chiếu nguồn pháp luật")).toBeVisible();
    await expect(page.getByText("Mức phạt được xác định theo quy định hiện hành.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Nghị định 100/2019/NĐ-CP" })).toBeVisible();
  });

  test("renders an API failure as an actionable alert", async ({ page }) => {
    await page.route("**/api/v1/chat/events**", async (route) =>
      route.fulfill({
        status: 500,
        contentType: "text/event-stream",
        body: "",
      }),
    );
    await page.route("**/api/v1/chat", async (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error: { message: "Dịch vụ tạm thời không khả dụng" },
        }),
      }),
    );
    await page.goto("/");
    await page.getByLabel("Câu hỏi").fill("Câu hỏi kiểm tra lỗi");
    await page.getByRole("button", { name: "Gửi", exact: true }).click();
    await expect(page.locator("p.error-message")).toContainText("Dịch vụ tạm thời không khả dụng");
  });

  test("renders an abstention from the mock API boundary", async ({ page }) => {
    await page.route("**/api/v1/chat/events**", async (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: result\ndata: ${JSON.stringify({
          status: "ABSTAINED",
          answer: null,
          claims: [],
          citations: [],
          abstention: { reason_code: "INSUFFICIENT_EVIDENCE" },
          trace_id: "trace-smoke-abstained",
        })}\n\n`,
      }),
    );
    await page.goto("/");
    await page.getByLabel("Câu hỏi").fill("Một tình huống chưa có đủ dữ kiện?");
    await page.getByRole("button", { name: "Gửi", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Chưa đủ căn cứ để kết luận" })).toBeVisible();
    await expect(page.getByText("Mã lý do:")).toBeVisible();
    await expect(page.getByText("INSUFFICIENT_EVIDENCE")).toBeVisible();
    await expect(
      page.getByText("Không thể đưa ra kết luận chắc chắn cho câu hỏi này."),
    ).toBeVisible();
  });

  test("shows the submitted question in the chat loading bubble", async ({ page }) => {
    let releaseResponse!: () => void;
    const responseReady = new Promise<void>((resolve) => {
      releaseResponse = resolve;
    });
    await page.route("**/api/v1/chat/events**", async (route) => {
      await responseReady;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: result\ndata: ${JSON.stringify({
          status: "VERIFIED",
          answer: "Đã xong.",
          claims: [{ claim: "Có căn cứ pháp lý" }],
          citations: [{ provision_id: "loading-fixture" }],
        })}\n\n`,
      });
    });
    await page.goto("/");
    await page.getByLabel("Câu hỏi").fill("Không đội mũ bảo hiểm bị phạt thế nào?");
    await page.getByRole("button", { name: "Gửi", exact: true }).click();
    await expect(page.locator('.loading-state[role="status"]')).toContainText(
      "Không đội mũ bảo hiểm bị phạt thế nào?",
    );
    await expect(page.locator(".loading-bar")).toHaveCount(1);
    releaseResponse();
  });
});

test.describe("Delayed response accessibility", () => {
  test("shows neutral in-flight status while a chat response is pending", async ({ page }) => {
    let releaseResponse!: () => void;
    const responseReady = new Promise<void>((resolve) => {
      releaseResponse = resolve;
    });
    await page.route("**/api/v1/chat/events**", async (route) => {
      await responseReady;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `event: result\ndata: ${JSON.stringify({
          status: "VERIFIED",
          answer: "Kết quả sau khi chờ.",
          claims: [{ claim: "Có căn cứ pháp lý" }],
          citations: [{ provision_id: "delayed-fixture" }],
          trace_id: "trace-delayed",
        })}\n\n`,
      });
    });
    await page.goto("/");
    await page.getByLabel("Câu hỏi").fill("Tra cứu khi phản hồi chậm");
    await page.getByRole("button", { name: "Gửi", exact: true }).click();
    const status = page.locator('.loading-state[role="status"]');
    await expect(status).toContainText("Tra cứu khi phản hồi chậm");
    await expect(status).toHaveAttribute("aria-live", "polite");
    await expect(page.getByRole("button", { name: "Dừng tra cứu", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Gửi", exact: true })).toHaveCount(0);
    await expect(page.locator(".loading-bar")).toHaveCount(1);
    releaseResponse();
    await expect(page.getByText("Kết quả sau khi chờ.")).toBeVisible();
  });
});
