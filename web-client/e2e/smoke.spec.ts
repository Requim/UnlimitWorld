import { expect, test } from "@playwright/test";

const ENEMY_CARDS = new Set([
  "flying_sword", "charge_sword", "flurry", "sword_draw", "myriad_swords",
  "fire_seed", "fan_flames", "burn_heaven", "silence_talisman", "lightning_talisman",
]);

test("真实 API 开局、出牌与刷新恢复", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("create-sword").click();
  const game = page.getByTestId("game-root");
  await expect(game).toHaveAttribute("data-phase", "map");
  await page.locator('[data-testid^="map-node-"]:not([disabled])').first().click();
  await expect(game).toHaveAttribute("data-phase", "combat");
  await expect(page.getByTestId("retry-assets")).toBeVisible();

  const revision = Number(await game.getAttribute("data-revision"));
  const card = page.locator('[data-testid^="hand-card-"]').first();
  const cardId = await card.getAttribute("data-card-id");
  await card.click();
  if (cardId && ENEMY_CARDS.has(cardId)) await page.getByTestId("enemy-target").click();
  else await page.getByTestId("cast-selected").click();
  await expect.poll(async () => Number(await game.getAttribute("data-revision"))).toBeGreaterThan(revision);

  const advancedRevision = await game.getAttribute("data-revision");
  await page.reload();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-revision", advancedRevision!);
  await page.getByTestId("settings-open").click();
  await expect(page.getByRole("button", { name: "减少动态效果" })).toBeVisible();
});
