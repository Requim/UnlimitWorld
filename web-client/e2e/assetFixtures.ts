import { expect, type Page } from "@playwright/test";

/** 模拟仅本测试页面的美术待生成状态；不修改磁盘 manifest 或真实正式位图。 */
export async function installPendingAssets(page: Page): Promise<void> {
  const response = await page.request.get("/assets/manifest.json");
  expect(response.ok()).toBe(true);
  const manifest = await response.json();
  await page.route("**/assets/manifest.json?*", (route) => route.fulfill({
    json: { ...manifest, status: "pending-generation", reason: "测试场景：原创位图待生成" },
  }));
}
