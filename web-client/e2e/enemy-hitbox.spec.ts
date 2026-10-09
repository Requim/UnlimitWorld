import { expect, test, type Page, type TestInfo } from "@playwright/test";

import type { AssetManifest } from "../src/game/useAssets";
import { REQUIRED_CARD_ASSETS, REQUIRED_ENEMY_ASSETS } from "../src/game/useAssets";
import { installPendingAssets } from "./assetFixtures";

test.use({ hasTouch: true });

const viewports = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 360, height: 740 },
];

for (const viewport of viewports) {
  for (const assets of ["pending", "ready"] as const) {
    test(`${viewport.width}x${viewport.height} ${assets} 点击敌人图像中心提交出牌`, async ({ page }, info) => {
      await page.setViewportSize(viewport);
      if (assets === "ready") await installReadyFixture(page);
      else await installPendingAssets(page);
      await enterBattle(page);
      await selectFlyingSword(page);
      const game = page.getByTestId("game-root");
      const revision = Number(await game.getAttribute("data-revision"));
      const canvas = page.locator(".phaser-host canvas");
      await expect(canvas).toBeVisible();
      const box = (await canvas.boundingBox())!;
      expect(box.width / box.height).toBeCloseTo(2.5, 2);
      const center = { x: box.x + box.width * 710 / 900, y: box.y + box.height * 190 / 360 };
      console.log(JSON.stringify({ viewport, assets, revision, center, target: await page.getByTestId("enemy-target").boundingBox() }));
      await captureBattle(page, info, "before");
      if (viewport.width > 720) await page.mouse.click(center.x, center.y);
      else await page.touchscreen.tap(center.x, center.y);
      await expect.poll(async () => Number(await game.getAttribute("data-revision")), { timeout: 2500 }).toBe(revision + 1);
      await expectHitboxAligned(page);
      await expect(page.locator('[data-card-id="flying_sword"].selected')).toHaveCount(0);
      await expectEnemyTextInside(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await captureBattle(page, info, "after");
    });
  }
}

test("减少动态、manifest 重试和连续 resize 保持图像命中", async ({ page }, info) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await installPendingAssets(page);
  await enterBattle(page);
  await selectFlyingSword(page);
  const game = page.getByTestId("game-root");
  const revision = Number(await game.getAttribute("data-revision"));
  await page.getByTestId("settings-open").click();
  await page.getByRole("button", { name: "减少动态效果" }).click();
  await page.getByTitle("关闭", { exact: true }).click();
  await expect(game).toHaveClass(/reduced-motion/);
  await installReadyFixture(page);
  await page.getByTestId("retry-assets").click();
  await expect(page.getByTestId("retry-assets")).toBeHidden();
  for (const viewport of [...viewports].reverse()) {
    await page.setViewportSize(viewport);
    await expectHitboxAligned(page);
    await expectEnemyTextInside(page);
  }
  const box = (await page.locator(".phaser-host canvas").boundingBox())!;
  await page.mouse.click(box.x + box.width * 710 / 900, box.y + box.height * 190 / 360);
  await expect.poll(async () => Number(await game.getAttribute("data-revision"))).toBe(revision + 1);
  await captureBattle(page, info, "after-resize");
});

async function enterBattle(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByTestId("create-sword").click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "map");
  await page.locator('[data-testid^="map-node-"]:not([disabled])').first().click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "combat");
}

async function selectFlyingSword(page: Page): Promise<void> {
  const card = page.locator('[data-testid^="hand-card-"][data-card-id="flying_sword"]').first();
  for (let turn = 0; turn < 3 && await card.count() === 0; turn += 1) {
    const revision = await page.getByTestId("game-root").getAttribute("data-revision");
    await page.getByTestId("end-turn").click();
    await expect(page.getByTestId("game-root")).not.toHaveAttribute("data-revision", revision!);
  }
  await expect(card).toBeVisible();
  await card.click();
  await expect(page.getByTestId("enemy-target")).toBeEnabled();
}

async function expectEnemyTextInside(page: Page): Promise<void> {
  const frame = (await page.locator(".battle-frame").boundingBox())!;
  const labels = page.locator(".enemy-info .intent, .enemy-info > strong, .enemy-info > span");
  await expect(labels).toHaveCount(3);
  for (const label of await labels.all()) {
    const box = (await label.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(frame.x);
    expect(box.x + box.width).toBeLessThanOrEqual(frame.x + frame.width);
    expect(box.y).toBeGreaterThanOrEqual(frame.y);
    expect(box.y + box.height).toBeLessThanOrEqual(frame.y + frame.height);
  }
}

async function expectHitboxAligned(page: Page): Promise<void> {
  await expect.poll(async () => {
    const canvas = (await page.locator(".phaser-host canvas").boundingBox())!;
    const target = (await page.getByTestId("enemy-target").boundingBox())!;
    return Math.max(
      Math.abs(target.x - (canvas.x + canvas.width * 605 / 900)),
      Math.abs(target.y - (canvas.y + canvas.height * 40 / 360)),
      Math.abs(target.width - canvas.width * 210 / 900),
      Math.abs(target.height - canvas.height * 300 / 360),
    );
  }).toBeLessThan(0.1);
}

async function captureBattle(page: Page, info: TestInfo, name: string): Promise<void> {
  await page.screenshot({ path: info.outputPath(`${name}.png`) });
  await page.locator(".phaser-host canvas").screenshot({ path: info.outputPath(`${name}-canvas.png`) });
}

async function installReadyFixture(page: Page): Promise<void> {
  const images = await page.evaluate(() => {
    const make = (width: number, height: number, color: string) => {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d")!;
      context.fillStyle = color;
      context.fillRect(0, 0, width, height);
      context.strokeStyle = "#202424";
      context.lineWidth = 4;
      context.strokeRect(4, 4, width - 8, height - 8);
      context.fillRect(width / 2 - 8, height / 2 - 8, 16, 16);
      return canvas.toDataURL("image/png");
    };
    return { background: make(900, 360, "#f3f4f0"), cultivator: make(190, 280, "#18796f"),
      enemy: make(210, 300, "#bf2c24"), card: make(100, 60, "#f0bc30") };
  });
  const manifest: AssetManifest = {
    version: 1, status: "ready", characters: { cultivator: images.cultivator },
    enemies: Object.fromEntries(REQUIRED_ENEMY_ASSETS.map((key) => [key, images.enemy])),
    backgrounds: { battle: images.background, boss: images.background },
    cards: Object.fromEntries(REQUIRED_CARD_ASSETS.map((key) => [key, images.card])),
  };
  await page.route("**/assets/manifest.json?*", (route) => route.fulfill({ json: manifest }));
}
