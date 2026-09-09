import { expect, test } from "@playwright/test";
test("long responses keep the conversation scrollable above the composer", async ({ page }) => {
  const longAnswer = Array.from(
    { length: 48 },
    (_, index) => `Đoạn giải thích pháp luật ${index + 1}. Nội dung đủ dài để tạo vùng cuộn.`,
  ).join("\n\n");
  await page.route("**/api/v1/chat", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "VERIFIED",
        answer: longAnswer,
        claims: [{ claim: "Có căn cứ pháp lý" }],
        citations: [
          {
            provision_id: "scroll-source",
            document_title: "Nghị định kiểm thử",
            article: "Điều 5",
            page_number: 14,
            source_text: "Đoạn trích kiểm thử",
          },
        ],
        trace_id: "trace-scroll",
      }),
    });
  });
  await page.goto("/");
  await page.getByLabel("Câu hỏi").fill("Kiểm tra câu trả lời dài");
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  await expect(page.getByText("Đoạn giải thích pháp luật 24.", { exact: false })).toBeVisible();
  const metrics = await page.locator(".thread").evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }));
  expect(metrics.scrollHeight).toBeGreaterThanOrEqual(metrics.clientHeight);
  expect(["auto", "visible"]).toContain(metrics.overflowY);
  await page.locator(".thread").evaluate((element) => element.scrollTo(0, element.scrollHeight));
  const scrollTop = await page.locator(".thread").evaluate((element) => element.scrollTop);
  expect(scrollTop).toBeGreaterThanOrEqual(0);
  await expect(page.getByRole("button", { name: "Xem đoạn trích" })).toBeVisible();
});
