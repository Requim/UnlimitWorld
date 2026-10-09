import { expect, test } from "@playwright/test";

test("全部 27 张正式位图由真实浏览器成功解码", async ({ page, request }) => {
  const response = await request.get("/assets/manifest.json");
  const manifest = await response.json();
  expect(manifest.status).toBe("ready");
  const urls = ["characters", "enemies", "backgrounds", "cards"]
    .flatMap((group) => Object.values(manifest[group]) as string[]);
  expect(new Set(urls).size).toBe(27);
  await page.goto("/");
  const dimensions = await page.evaluate(async (paths) => Promise.all(paths.map(async (src) => {
    const image = new Image();
    image.src = src;
    await image.decode();
    return { src, width: image.naturalWidth, height: image.naturalHeight };
  })), urls);
  expect(dimensions.every((image) => image.width >= 256 && image.height >= 192)).toBe(true);
});

for (const viewport of [
  { width: 1440, height: 900 }, { width: 390, height: 844 },
  { width: 430, height: 932 }, { width: 360, height: 740 },
]) {
  test(`${viewport.width}x${viewport.height} 正式开局及手牌主体完整可见`, async ({ page }, info) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.locator(".archetype-art img")).toHaveCount(3);
    await expect.poll(() => page.locator(".archetype-art img").evaluateAll((images) =>
      images.every((image) => (image as HTMLImageElement).complete &&
        (image as HTMLImageElement).naturalWidth > 100))).toBe(true);
    await page.screenshot({ path: info.outputPath("opening.png"), fullPage: true });
    await page.getByTestId("create-sword").click();
    await page.locator('[data-testid^="map-node-"]:not([disabled])').first().click();
    await expect(page.locator("canvas")).toBeVisible();
    await expect(page.locator(".hand-zone .card-art")).toHaveCount(5);
    const artwork = page.locator(".hand-zone .card-art").first();
    await expect.poll(() => artwork.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBe(768);
    expect(await artwork.evaluate((image) => getComputedStyle(image).objectFit)).toBe("contain");
    expect((await artwork.boundingBox())!.height).toBeGreaterThan(60);
    const tiles = await page.locator(".hand-zone .card-tile").all();
    for (const tile of tiles) {
      const box = (await tile.boundingBox())!;
      for (const child of await tile.locator("img, strong, small").all()) {
        const bounds = (await child.boundingBox())!;
        expect(bounds.y).toBeGreaterThanOrEqual(box.y);
        expect(bounds.y + bounds.height).toBeLessThanOrEqual(box.y + box.height + 1);
      }
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath("combat.png"), fullPage: true });
  });
}
