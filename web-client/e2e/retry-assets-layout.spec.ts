import { expect, test } from "@playwright/test";
import { installPendingAssets } from "./assetFixtures";

for (const width of [360, 390, 430]) {
  test(`${width}px 资源重试按钮包含原尺寸图标且无原生内溢出`, async ({ page }) => {
    await page.setViewportSize({ width, height: 740 });
    await installPendingAssets(page);
    await page.goto("/");
    await page.getByTestId("create-sword").click();
    await page.locator('[data-testid^="map-node-"]:not([disabled])').first().click();
    const button = page.getByTestId("retry-assets");
    await expect(button).toBeVisible();
    expect(await button.evaluate((element) => element.scrollWidth <= element.clientWidth + 2)).toBe(true);
    const box = (await button.boundingBox())!;
    const icon = (await button.locator("svg").boundingBox())!;
    expect(icon.width).toBe(24);
    expect(icon.height).toBe(24);
    expect(icon.x).toBeGreaterThanOrEqual(box.x);
    expect(icon.y).toBeGreaterThanOrEqual(box.y);
    expect(icon.x + icon.width).toBeLessThanOrEqual(box.x + box.width);
    expect(icon.y + icon.height).toBeLessThanOrEqual(box.y + box.height);
  });
}
