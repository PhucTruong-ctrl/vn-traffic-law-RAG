import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const pdfFixture = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 3/Kids[3 0 R 4 0 R 5 0 R]>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 6 0 R>>endobj\n4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 6 0 R>>endobj\n5 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 6 0 R>>endobj\n6 0 obj<</Length 44>>stream\nBT /F1 20 Tf 80 650 Td (Citation fixture) Tj ET\nendstream\nendobj\ntrailer<</Root 1 0 R>>\n%%EOF",
  "binary",
);

const citation = {
  provision_id: "fixture-provision",
  document_id: "fixture-document",
  document_number: "Fixture 1/2026",
  document_title: "Bản án kiểm thử PDF",
  article: "5",
  page_number: 2,
  bbox: [0.2, 0.25, 0.75, 0.38],
  source_text: "Đoạn trích trong bản PDF kiểm thử.",
};

async function openDrawer(page: Page, withBbox = true) {
  await page.route("**/api/v1/chat", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      status: "VERIFIED",
      answer: "Câu trả lời kiểm thử.",
      claims: [],
      citations: [{ ...citation, ...(withBbox ? {} : { bbox: undefined, page_number: 1 }) }],
      trace_id: "trace-pdf-fixture",
    }),
  }));
  await page.route("**/api/v1/documents/fixture-document/source", (route) =>
    route.fulfill({ status: 200, contentType: "application/pdf", body: pdfFixture }),
  );
  await page.goto("/");
  await page.getByLabel("Câu hỏi").first().fill("Mở nguồn PDF kiểm thử");
  await page.getByRole("button", { name: "Gửi", exact: true }).first().click();
  await page.getByRole("button", { name: "Xem đoạn trích" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test("opens a large PDF citation drawer with a rendered canvas and bbox highlight", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await openDrawer(page);
  const dialog = page.getByRole("dialog");
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  const dialogBox = await dialog.boundingBox();
  expect(dialogBox?.width ?? 0).toBeGreaterThan(600);
  const canvas = dialog.locator("canvas");
  await expect(canvas).toBeVisible();
  await expect.poll(() => canvas.evaluate((node) => {
    const element = node as HTMLCanvasElement;
    const context = element.getContext("2d");
    if (!context || !element.width || !element.height) return false;
    const pixels = context.getImageData(0, 0, element.width, element.height).data;
    for (let index = 0; index < pixels.length; index += 64) {
      if (pixels[index] < 245 || pixels[index + 1] < 245 || pixels[index + 2] < 245) return true;
    }
    return false;
  })).toBe(true);
  const highlight = dialog.getByLabel("Đoạn trích được tô sáng");
  await expect(highlight).toBeVisible();
  expect((await highlight.boundingBox())?.width).toBeGreaterThan(0);
  expect((await highlight.boundingBox())?.height).toBeGreaterThan(0);
});

test("zooms the canvas, enforces page boundaries, and accepts page input", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await openDrawer(page);
  const dialog = page.getByRole("dialog");
  const canvas = dialog.locator("canvas");
  await expect(canvas).toBeVisible();
  const initialWidth = await canvas.evaluate((node) => node.getBoundingClientRect().width);
  await dialog.getByRole("button", { name: "Phóng to" }).click();
  await expect.poll(() => canvas.evaluate((node) => node.getBoundingClientRect().width)).toBeGreaterThan(initialWidth);

  const previous = dialog.getByRole("button", { name: "Trang trước" });
  const next = dialog.getByRole("button", { name: "Trang sau" });
  const input = dialog.locator('input[type="number"]');
  await expect(input).toHaveValue("2");
  await expect(previous).toBeEnabled();
  await expect(next).toBeEnabled();
  await previous.click();
  await expect(input).toHaveValue("1");
  await expect(previous).toBeDisabled();
  await next.click();
  await expect(input).toHaveValue("2");
  await input.fill("3");
  await input.press("Enter");
  await expect(input).toHaveValue("3");
  await expect(next).toBeDisabled();
  await input.fill("99");
  await input.press("Enter");
  await expect(input).toHaveValue("99");
});

test("reports missing bbox explicitly and restores focus after Escape", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await openDrawer(page, false);
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Trích dẫn chưa có tọa độ OCR; đang hiển thị đúng trang nguồn.")).toBeVisible();
  await expect(dialog.getByLabel("Đoạn trích được tô sáng")).toHaveCount(0);
  await expect(dialog.locator("canvas")).toBeVisible();
  const close = dialog.getByRole("button", { name: "Đóng trình xem PDF" });
  await expect(close).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "Xem đoạn trích" })).toBeFocused();
});
