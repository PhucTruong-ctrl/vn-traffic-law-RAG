import { expect, test } from "@playwright/test";

test.describe("Sprint 5 answer flow", () => {
  test("renders the home form and validates a blank question", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Hỏi đáp pháp luật giao thông" })).toBeVisible();
    await expect(page.getByLabel("Câu hỏi")).toBeVisible();
    await expect(page.getByLabel("Ngày áp dụng")).toBeVisible();
    await expect(page.getByLabel("Loại phương tiện")).toBeVisible();
    await expect(page.getByRole("button", { name: "Gửi câu hỏi" })).toBeDisabled();
  });

  test("renders a verified response from the mock API boundary", async ({ page }) => {
    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "VERIFIED",
          answer: "Mức phạt được xác định theo quy định hiện hành.",
          claims: [{ claim: "Có căn cứ pháp lý", claim_type: "RULE" }],
          citations: [{ provision_id: "nd-100-2019:article-6", document_number: "Nghị định 100/2019/NĐ-CP", article: "Điều 6" }],
          disclaimer: "This response is informational and not legal advice.",
          trace_id: "trace-smoke-verified",
        }),
      });
    });
    await page.goto("/");
    await page.getByLabel("Câu hỏi").fill("Vượt đèn đỏ bị phạt thế nào?");
    await page.getByRole("button", { name: "Gửi câu hỏi" }).click();
    await expect(page.getByText("Đã kiểm chứng")).toBeVisible();
    await expect(page.getByText("Mức phạt được xác định theo quy định hiện hành.")).toBeVisible();
    await expect(page.getByText("Nghị định 100/2019/NĐ-CP")).toBeVisible();
  });

  test("renders an abstention from the mock API boundary", async ({ page }) => {
    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ABSTAINED",
          answer: null,
          claims: [],
          citations: [],
          abstention: { reason_code: "INSUFFICIENT_EVIDENCE" },
          trace_id: "trace-smoke-abstained",
        }),
      });
    });
    await page.goto("/");
    await page.getByLabel("Câu hỏi").fill("Một tình huống chưa có đủ dữ kiện?");
    await page.getByRole("button", { name: "Gửi câu hỏi" }).click();
    await expect(page.getByText("Chưa đủ căn cứ")).toBeVisible();
    await expect(page.getByText("Mã lý do:")).toBeVisible();
    await expect(page.getByText("INSUFFICIENT_EVIDENCE")).toBeVisible();
    await expect(page.getByText("Không thể đưa ra kết luận chắc chắn cho câu hỏi này.")).toBeVisible();
  });
});
