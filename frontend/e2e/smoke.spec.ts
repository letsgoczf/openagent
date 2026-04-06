import { expect, test } from "@playwright/test";

test("home page loads and links to chat", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /本地智能体助手/ })).toBeVisible();
  await page.getByRole("link", { name: "进入对话" }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("heading", { name: "Chat" })).toBeVisible();
});
