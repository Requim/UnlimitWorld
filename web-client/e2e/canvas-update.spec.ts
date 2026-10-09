import { expect, test, type Page } from "@playwright/test";

import type { RunView } from "../src/api/types";

// @ts-expect-error The shared standalone Node QA helper is intentionally plain JavaScript.
import { captureStaticCanvas, verifyStaticCanvasUpdate } from "../../tools/playtest-canvas.mjs";

test("正常挑衅改变相同尺寸且减少动态的真实画布", async ({ page }, info) => {
  await page.goto("/");
  await page.getByTestId("create-sword").click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "map");
  await page.getByTestId("settings-open").click();
  await page.getByRole("button", { name: "减少动态效果" }).click();
  await page.getByTitle("关闭", { exact: true }).click();
  await page.locator('[data-testid^="map-node-"]:not([disabled])').first().click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "combat");
  const card = page.locator('[data-testid^="hand-card-"][data-card-id="guard"], [data-testid^="hand-card-"][data-card-id="flying_sword"]').first();
  const target = await card.getAttribute("data-card-id") === "guard" ? "cast-selected" : "enemy-target";
  await card.click();
  await page.getByTestId(target).click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-revision", "2");
  const beforeRun = await readRun(page);
  const tile = page.locator('[data-testid^="hand-card-"]').first();
  await tile.click();
  await tile.click();
  await expect(page.getByTestId("selected-card-detail")).toBeHidden();
  const canvas = page.locator(".phaser-host canvas");
  const bounds = await canvas.boundingBox();
  const before = await captureStaticCanvas(() => canvas.screenshot());
  await page.getByTestId("taunt").click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-revision", "3");
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "combat");
  expect(await canvas.boundingBox()).toEqual(bounds);
  expect(await verifyStaticCanvasUpdate(before, () => canvas.screenshot())).toBe(true);
  const afterRun = await readRun(page);
  expect(beforeRun.combat?.taunt_used).toBe(false);
  expect(afterRun.combat?.taunt_used).toBe(true);
  expect(afterRun.combat?.energy).toBe(beforeRun.combat!.energy + beforeRun.combat!.taunt_preview.energy_gain);
  await page.screenshot({ path: info.outputPath("static-action-update.png") });
});

async function readRun(page: Page): Promise<RunView> {
  return page.evaluate(async () => {
    const session = JSON.parse(localStorage.getItem("tiandao.cardRogue.session.v1")!);
    const response = await fetch(`/api/v2/runs/${session.runId}`, {
      headers: { Authorization: `Bearer ${session.accessToken}` },
    });
    return (await response.json()).run;
  });
}
