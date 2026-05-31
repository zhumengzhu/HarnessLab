import { expect, test } from "@playwright/test";

test.describe("HarnessLab Web UI smoke", () => {
  test("loads shell and health-backed sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".app-sidebar-title")).toHaveText("HarnessLab");
    await expect(page.getByRole("button", { name: /聊天|Chat/, exact: true })).toBeVisible();
  });

  test("chat view exposes session tabs", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("tab", { name: /对话|Chat/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Trace" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Activity" })).toBeVisible();
  });

  test("trace tab shows Jaeger-style span tree by default", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: /Trace|追踪/ }).click();
    await expect(page.locator(".trace-jaeger-panel")).toBeVisible();
    await expect(page.getByRole("tab", { name: /Timeline|时间线/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await page.getByRole("tab", { name: /^Events$/ }).click();
    await expect(page.getByRole("heading", { name: /Span list|Span 列表/ })).toBeVisible();
  });

  test("settings page holds UI preferences", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /设置|Settings/ }).click();
    await expect(page.getByRole("heading", { name: /设置|Settings/ })).toBeVisible();
    await expect(page.getByText(/界面偏好|UI preferences/)).toBeVisible();
  });
});
