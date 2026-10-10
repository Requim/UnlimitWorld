import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";

import type { ActionRequest, RunView } from "../src/api/types";
import type { StoredSession } from "../src/state/storage";

const MYTH_KEY = "tiandao.cardRogue.mythBifang.session.v1";
const CLASSIC_KEY = "tiandao.cardRogue.session.v1";
const ACTION_ROUTE = "**/api/v2/runs/*/actions";
const SMOOTH_COLORS = Array.from({ length: 16 }, (_, index) => [
  32 + index * 11, 35 + (index * 47) % 190, 40 + (index * 83) % 180,
] as [number, number, number]);

for (const [archetype, choice] of [
  ["sword", "borrow_fire"], ["fire", "seal_evidence"], ["talisman", "destroy_scroll"],
] as const) {
  test(`真实 ${archetype} 流派与 ${choice} 剧情进入毕方战斗`, async ({ page }) => {
    await openStory(page, archetype);
    await expect(page.getByTestId(`story-choice-${choice}`)).toContainText(/天谴|护盾|灵力/);
    await page.getByTestId(`story-choice-${choice}`).click();
    await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
    await expect(page.locator(".myth-canvas canvas")).toBeVisible();
    await expect(page.locator('img[src^="/assets/cards"]')).toHaveCount(0);
    const keys = await page.evaluate(([myth, classic]) => [localStorage.getItem(myth), localStorage.getItem(classic)],
      [MYTH_KEY, CLASSIC_KEY]);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBeNull();
    if (archetype === "sword") await captureViewports(page);
    const revision = await page.getByTestId("myth-root").getAttribute("data-revision");
    await page.reload();
    await expect(page.getByTestId("myth-root")).toHaveAttribute("data-revision", revision!);
  });
}

test("剧情提交响应丢失时保留原动作编号并允许打开设置", async ({ page }) => {
  await openStory(page, "sword");
  const requests: ActionRequest[] = [];
  await page.route(ACTION_ROUTE, async (route) => {
    requests.push(route.request().postDataJSON());
    if (requests.length > 1) return route.continue();
    const committed = await route.fetch();
    expect(committed.status()).toBe(200);
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"run":' });
  });
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("retry-action")).toContainText("重试原动作");
  await expect(page.getByTestId("story-choice-borrow_fire")).toBeDisabled();
  await expect(page.getByTestId("settings-open")).toBeEnabled();
  await page.getByTestId("retry-action").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  expect(requests[1]).toEqual(requests[0]);
});

test("409 只同步权威局面，401 只清理样板凭证", async ({ page }) => {
  await openStory(page, "fire");
  const session = await readSession(page);
  await page.evaluate((key) => localStorage.setItem(key, '{"accessToken":"classic","runId":"classic-run"}'), CLASSIC_KEY);
  const committed = await page.request.post(`/api/v2/runs/${session.runId}/actions`, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
    data: { kind: "choose_event", choice_id: "seal_evidence", action_id: crypto.randomUUID(), expected_revision: 0 },
  });
  expect(committed.status()).toBe(200);
  await page.getByTestId("story-choice-destroy_scroll").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  await page.evaluate((key) => {
    const value = JSON.parse(localStorage.getItem(key)!);
    localStorage.setItem(key, JSON.stringify({ ...value, accessToken: "invalid" }));
  }, MYTH_KEY);
  await page.reload();
  await expect(page.getByTestId("reset-session")).toBeVisible();
  await page.getByTestId("reset-session").click();
  await expect(page.getByTestId("create-sword")).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), CLASSIC_KEY)).toContain("classic-run");
});

test("双角色 idle 持续播放且减少动态设置会停在静态种子", async ({ page }) => {
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  const heroIdle = await canvasRegionSignature(page, [.04, .46, .12, .98]);
  const bifangIdle = await canvasRegionSignature(page, [.5, .98, .05, .98]);
  await expect.poll(() => canvasRegionSignature(page, [.04, .46, .12, .98])).not.toBe(heroIdle);
  await expect.poll(() => canvasRegionSignature(page, [.5, .98, .05, .98])).not.toBe(bifangIdle);
  await page.getByTestId("settings-open").click();
  await page.getByRole("button", { name: "减少动态效果" }).click();
  await expect(page.getByTestId("myth-root")).toHaveClass(/reduced-motion/);
  expect(await canvasStayedStable(page, 600)).toBe(true);
});

test("synthetic smooth-v2 挥剑在真实 Phaser 中按行播放全部16帧", async ({ page }) => {
  await routeSyntheticClip(page, "hero_sword", 16, 24, SMOOTH_COLORS);
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  const run = await readRun(page);
  await routeSwordResponse(page, run);
  const sampled = sampleSyntheticFrames(page, SMOOTH_COLORS, [.04, .46, .12, .98]);
  await playFlyingSword(page);
  await page.waitForTimeout(250);
  await saveSmoothEvidence(page, "synthetic-hero-sword-mid.png");
  const sequence = compressFrames(await sampled).filter((frame) => frame >= 0);
  expect(sequence).toEqual(Array.from({ length: 16 }, (_, index) => index));
});

test("synthetic smooth-v2 演出可由减少动态及时取消并稳定回种子", async ({ page }) => {
  const synthetic = await routeSyntheticClip(page, "hero_sword", 16, 24, SMOOTH_COLORS);
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await synthetic.loaded;
  const run = await readRun(page);
  const routed = await routeSwordResponse(page, run);
  await expect(page.getByTestId("taunt")).toBeEnabled();
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.getByTestId("taunt").click();
  expect((await routed.received).kind).toBe("taunt");
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "true");
  expect(pageErrors).toEqual([]);
  await page.getByTestId("settings-open").click();
  await page.getByRole("button", { name: "减少动态效果" }).click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "false", { timeout: 300 });
  await saveSmoothEvidence(page, "synthetic-cancelled-to-seed.png");
  expect(await canvasStayedStable(page, 300)).toBe(true);
});

test("synthetic smooth-v2 减少动态后 resize 保持静态种子几何", async ({ page }) => {
  const synthetic = await routeSyntheticClip(page, "hero_sword", 16, 24, SMOOTH_COLORS);
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  await synthetic.loaded;
  const routed = await routeSwordResponse(page, await readRun(page));
  await page.getByTestId("taunt").click();
  expect((await routed.received).kind).toBe("taunt");
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "true");
  await page.getByTestId("settings-open").click();
  const toggle = page.getByRole("button", { name: "减少动态效果" });
  await toggle.click();
  await expect(page.getByTestId("myth-root")).toHaveClass(/reduced-motion/);
  const canvas = page.locator(".myth-canvas canvas");
  const initialWidth = (await canvas.boundingBox())!.width;
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async () => (await canvas.boundingBox())!.width).not.toBe(initialWidth);
  await expect(page.getByTestId("end-turn")).toBeEnabled();
  expect(await canvasStayedStable(page, 120)).toBe(true);
  const resized = await canvasRegionSample(page, [.04, .46, .12, .98]);
  await toggle.click();
  await expect(page.getByTestId("myth-root")).not.toHaveClass(/reduced-motion/);
  await toggle.click();
  await expect(page.getByTestId("myth-root")).toHaveClass(/reduced-motion/);
  expect(await canvasStayedStable(page, 120)).toBe(true);
  const restored = await canvasRegionSample(page, [.04, .46, .12, .98]);
  expect(sampleDifference(resized, restored)).toBeLessThan(.01);
});

test("synthetic smooth-v2 播放中 resize 会保留动作并在完成后解锁命令", async ({ page }) => {
  const synthetic = await routeSyntheticClip(page, "hero_sword", 16, 24, SMOOTH_COLORS);
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await synthetic.loaded;
  const run = await readRun(page);
  const routed = await routeSwordResponse(page, run);
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.getByTestId("taunt").click();
  expect((await routed.received).kind).toBe("taunt");
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "true");
  const canvas = page.locator(".myth-canvas canvas");
  const initialWidth = (await canvas.boundingBox())!.width;
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async () => (await canvas.boundingBox())!.width).not.toBe(initialWidth);
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "true");
  await expect(page.getByTestId("myth-root")).toHaveAttribute(
    "data-presentation-busy", "false", { timeout: 1_500 });
  await expect(page.getByTestId("taunt")).toBeEnabled();
  await expect(page.getByTestId("end-turn")).toBeEnabled();
  expect(pageErrors).toEqual([]);
});

test("synthetic smooth-v2 终局退场保留第12帧直到结算", async ({ page }) => {
  const colors = SMOOTH_COLORS.slice(0, 12);
  const synthetic = await routeSyntheticClip(page, "bifang_retreat", 12, 24, colors);
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  await synthetic.loaded;
  const run = await readRun(page);
  const defeated = lethalRun(run);
  let accept!: (action: ActionRequest) => void;
  const received = new Promise<ActionRequest>((resolve) => { accept = resolve; });
  await page.route(ACTION_ROUTE, async (route) => {
    const action = route.request().postDataJSON() as ActionRequest;
    await route.fulfill({ json: { run: defeated, events: [
      { kind: "completed", text: defeated.epitaph!, source: "system", target: "enemy", visual: "defeat",
        state_after: { player: run.player, enemy: { hp: 0, block: 0, burn: 0, weak: 0 } } },
    ] } });
    accept(action);
  });
  const sampled = sampleSyntheticFrames(page, colors, [.5, .98, .05, .98]);
  await expect(page.getByTestId("end-turn")).toBeEnabled();
  await page.getByTestId("end-turn").click();
  expect((await received).kind).toBe("end_turn");
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "true");
  await page.waitForTimeout(470);
  await saveSmoothEvidence(page, "synthetic-bifang-retreat-final.png");
  const sequence = compressFrames(await sampled);
  const visible = sequence.filter((frame) => frame >= 0);
  expect(visible).toEqual(Array.from({ length: 12 }, (_, index) => index));
  expect(sequence.slice(sequence.lastIndexOf(11) + 1)).not.toContain(-1);
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "completed");
});

test("已登记动作条带加载失败时锁住战斗命令且保留安全操作", async ({ page }) => {
  let actionRequests = 0;
  await page.route("**/assets/myth/animations/hero_idle.png", (route) => route.fulfill({ status: 404 }));
  await page.route(ACTION_ROUTE, async (route) => {
    actionRequests += 1;
    await route.continue();
  });
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  await expect(page.getByText("神话位图加载失败")).toBeVisible();
  await expect(page.getByTestId("end-turn")).toBeDisabled();
  await expect(page.getByTestId("enemy-target")).toBeDisabled();
  await expect(page.locator('[data-testid^="hand-card-"]').first()).toBeDisabled();
  await expect(page.getByTestId("settings-open")).toBeEnabled();
  await expect(page.getByTestId("retry-assets")).toBeEnabled();
  await page.getByTestId("settings-open").click();
  await expect(page.getByRole("complementary", { name: "游戏设置" })).toBeVisible();
  expect(actionRequests).toBe(1);
});

test("真实服务回合可从 UI 推进到败局并播放败北动作", async ({ page }) => {
  test.setTimeout(90_000);
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  let reachedTerminal = false;
  for (let turn = 0; turn < 20; turn += 1) {
    await expect(page.getByTestId("end-turn")).toBeEnabled();
    const response = page.waitForResponse((item) => item.url().includes("/api/v2/runs/")
      && item.url().endsWith("/actions") && item.request().method() === "POST");
    await page.getByTestId("end-turn").click();
    const body = await (await response).json() as { run: RunView; events: Array<{ visual?: string }> };
    if (body.run.phase === "game_over") {
      expect(body.events.some((event) => event.visual === "defeat")).toBe(true);
      await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "true");
      expect(await capturePresentationFrames(page, "myth-real-defeat")).toBeGreaterThan(1);
      await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "game_over", { timeout: 10_000 });
      await saveEvidence(page, "myth-real-service-game-over.png");
      reachedTerminal = true;
      break;
    }
    await expect(page.getByTestId("myth-root")).toHaveAttribute("data-revision", String(body.run.revision));
    await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "false");
  }
  expect(reachedTerminal).toBe(true);
});

test("致命结算等待真实画布事件完成后才切换结局", async ({ page }) => {
  await openStory(page, "sword");
  await page.getByTestId("story-choice-borrow_fire").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  const run = await readRun(page);
  const before = await canvasSignature(page);
  const heroBefore = await canvasRegionSample(page, [.04, .46, .12, .98]);
  await page.route(ACTION_ROUTE, async (route) => {
    const action = route.request().postDataJSON() as ActionRequest;
    const defeated = lethalRun(run);
    await route.fulfill({ json: { run: defeated, events: lethalEvents(run, defeated, action) } });
  });
  await page.locator('[data-testid^="hand-card-"][data-card-id="flying_sword"]').first().click();
  await page.getByTestId("enemy-target").click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-presentation-busy", "true");
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "combat");
  const actionStart = await canvasSignature(page);
  await expect.poll(() => canvasSignature(page)).not.toBe(actionStart);
  const heroAction = await canvasRegionSample(page, [.04, .46, .12, .98]);
  expect(sampleDifference(heroBefore, heroAction)).toBeGreaterThan(.04);
  await saveEvidence(page, "myth-hero-sword-action.png");
  expect(await canvasSignature(page)).not.toBe(before);
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "completed");
  await expect(page.getByTestId("phase-completed")).toBeVisible();
});

async function openStory(page: Page, archetype: "sword" | "fire" | "talisman"): Promise<void> {
  await page.goto("/myth");
  await page.getByTestId(`create-${archetype}`).click();
  await expect(page.getByTestId("myth-root")).toHaveAttribute("data-phase", "event");
  await expect(page.locator('[data-testid^="story-choice-"]')).toHaveCount(3);
}

async function routeSyntheticClip(page: Page, key: "hero_sword" | "bifang_retreat",
  frames: number, fps: number, colors: Array<[number, number, number]>): Promise<{ loaded: Promise<void> }> {
  await page.addInitScript((settingsKey) => localStorage.removeItem(settingsKey),
    "tiandao.cardRogue.settings.v1");
  const rows = frames / 4;
  const url = `/assets/myth/animations/synthetic-${key}.png`;
  let markLoaded!: () => void;
  const loaded = new Promise<void>((resolve) => { markLoaded = resolve; });
  await page.route("**/assets/myth/manifest.json", async (route) => {
    const response = await route.fetch();
    const manifest = await response.json();
    manifest.animations[key] = { url, frame_size: [704, 704], frames, fps,
      anchor: [0.5, 1], reference_height: 620, profile: "smooth-v2", columns: 4, rows };
    await route.fulfill({ response, json: manifest });
  });
  await page.route(`**${url}`, async (route) => {
    await route.fulfill({ contentType: "image/svg+xml", body: syntheticSheetSvg(colors, rows) });
    markLoaded();
  });
  return { loaded };
}

function syntheticSheetSvg(colors: Array<[number, number, number]>, rows: number): string {
  const rects = colors.map(([red, green, blue], index) => {
    const x = (index % 4) * 704;
    const y = Math.floor(index / 4) * 704;
    return `<rect x="${x}" y="${y}" width="704" height="704" fill="rgb(${red},${green},${blue})"/>`;
  }).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="2816" height="${rows * 704}" viewBox="0 0 2816 ${rows * 704}">${rects}</svg>`;
}

async function routeSwordResponse(page: Page, run: RunView): Promise<{ received: Promise<ActionRequest> }> {
  const after = { ...run, revision: run.revision + 1 };
  const state = { player: run.player, enemy: run.combat?.enemy,
    turn: run.combat?.turn, energy: run.combat?.energy };
  let accept!: (action: ActionRequest) => void;
  const received = new Promise<ActionRequest>((resolve) => { accept = resolve; });
  await page.route(ACTION_ROUTE, async (route) => {
    const action = route.request().postDataJSON() as ActionRequest;
    await route.fulfill({ json: { run: after, events: [
      { kind: "damage", text: "synthetic frame order", source: "player", target: "enemy",
        visual: "sword", amount: 1, state_after: state },
    ] } });
    accept(action);
  });
  return { received };
}

async function playFlyingSword(page: Page): Promise<void> {
  await page.locator('[data-testid^="hand-card-"][data-card-id="flying_sword"]').first().click();
  await page.getByTestId("enemy-target").click();
}

async function sampleSyntheticFrames(page: Page, colors: Array<[number, number, number]>,
  region: [number, number, number, number]): Promise<number[]> {
  return page.evaluate(async ({ palette, box }) => {
    const root = document.querySelector<HTMLElement>('[data-testid="myth-root"]')!;
    const samples: number[] = [];
    const readFrame = (canvas: HTMLCanvasElement) => {
      const context = canvas.getContext("2d");
      if (!context) return -1;
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const counts = palette.map(() => 0);
      const left = Math.floor(canvas.width * box[0]); const right = Math.floor(canvas.width * box[1]);
      const top = Math.floor(canvas.height * box[2]); const bottom = Math.floor(canvas.height * box[3]);
      for (let y = top; y < bottom; y += 4) for (let x = left; x < right; x += 4) {
        const offset = (y * canvas.width + x) * 4;
        const index = palette.findIndex((color) => color[0] === pixels[offset]
          && color[1] === pixels[offset + 1] && color[2] === pixels[offset + 2]);
        if (index >= 0) counts[index] += 1;
      }
      const maximum = Math.max(...counts);
      return maximum >= 20 ? counts.indexOf(maximum) : -1;
    };
    const deadline = performance.now() + 5_000;
    while (root.dataset.presentationBusy !== "true" && performance.now() < deadline) {
      await new Promise(requestAnimationFrame);
    }
    const canvas = document.querySelector<HTMLCanvasElement>(".myth-canvas canvas");
    if (!canvas) return samples;
    while (root.dataset.presentationBusy === "true" && performance.now() < deadline) {
      samples.push(readFrame(canvas));
      await new Promise(requestAnimationFrame);
    }
    return samples;
  }, { palette: colors, box: region });
}

function compressFrames(frames: number[]): number[] {
  return frames.filter((frame, index) => index === 0 || frame !== frames[index - 1]);
}

async function readSession(page: Page): Promise<StoredSession> {
  return page.evaluate((key) => JSON.parse(localStorage.getItem(key)!), MYTH_KEY);
}

async function readRun(page: Page): Promise<RunView> {
  const session = await readSession(page);
  const response = await page.request.get(`/api/v2/runs/${session.runId}`, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).run;
}

async function captureViewports(page: Page): Promise<void> {
  for (const [width, height] of [[1440, 900], [390, 844], [430, 932], [360, 740]]) {
    await page.setViewportSize({ width, height });
    await assertStageGeometry(page);
    await saveEvidence(page, `myth-${width}x${height}.png`);
  }
}

async function saveEvidence(page: Page, name: string): Promise<void> {
  const evidence = path.resolve("..", ".data", "playtest-myth-3b");
  await mkdir(evidence, { recursive: true });
  await page.screenshot({ path: path.join(evidence, name) });
}

async function saveSmoothEvidence(page: Page, name: string): Promise<void> {
  const evidence = path.resolve("..", ".data", "playtest-myth-smooth-4a");
  await mkdir(evidence, { recursive: true });
  await page.screenshot({ path: path.join(evidence, name) });
}

async function assertStageGeometry(page: Page): Promise<void> {
  const stage = await page.getByTestId("myth-stage").boundingBox();
  const target = await page.getByTestId("enemy-target").boundingBox();
  const card = await page.locator(".myth-card").first().boundingBox();
  const rule = await page.locator(".myth-card em").first().boundingBox();
  const signature = await canvasSignature(page);
  const pixels = await canvasPixelMetrics(page);
  await expect(page.locator(".myth-player-stats span").nth(1)).toBeVisible();
  expect(stage && target && card && rule).toBeTruthy();
  expect(target!.x).toBeGreaterThanOrEqual(stage!.x);
  expect(target!.y).toBeGreaterThanOrEqual(stage!.y);
  expect(target!.x + target!.width).toBeLessThanOrEqual(stage!.x + stage!.width + 1);
  expect(target!.y + target!.height).toBeLessThanOrEqual(stage!.y + stage!.height + 1);
  expect(rule!.y + rule!.height).toBeLessThanOrEqual(card!.y + card!.height + 1);
  expect(signature.length).toBeGreaterThan(1000);
  expect(pixels.opaqueRatio).toBeGreaterThan(.98);
  expect(pixels.colorfulRatio).toBeGreaterThan(.08);
  expect(pixels.lightRange).toBeGreaterThan(120);
}

async function canvasSignature(page: Page): Promise<string> {
  return page.locator(".myth-canvas canvas").evaluate((canvas: HTMLCanvasElement) => canvas.toDataURL("image/png"));
}

async function canvasStayedStable(page: Page, duration: number): Promise<boolean> {
  return page.locator(".myth-canvas canvas").evaluate(async (canvas: HTMLCanvasElement, wait) => {
    const signature = canvas.toDataURL("image/png");
    await new Promise((resolve) => window.setTimeout(resolve, wait));
    return canvas.toDataURL("image/png") === signature;
  }, duration);
}

async function canvasPixelMetrics(page: Page) {
  return page.locator(".myth-canvas canvas").evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext("2d")!;
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let sampled = 0; let opaque = 0; let colorful = 0; let low = 255; let high = 0;
    for (let y = 0; y < canvas.height; y += 8) for (let x = 0; x < canvas.width; x += 8) {
      const offset = (y * canvas.width + x) * 4;
      const red = pixels[offset]; const green = pixels[offset + 1]; const blue = pixels[offset + 2];
      const light = (red + green + blue) / 3;
      sampled += 1; opaque += pixels[offset + 3] > 240 ? 1 : 0;
      colorful += Math.max(red, green, blue) - Math.min(red, green, blue) > 28 ? 1 : 0;
      low = Math.min(low, light); high = Math.max(high, light);
    }
    return { opaqueRatio: opaque / sampled, colorfulRatio: colorful / sampled, lightRange: high - low };
  });
}

async function canvasRegionSignature(page: Page, region: [number, number, number, number]): Promise<string> {
  const sample = await canvasRegionSample(page, region);
  return sample.join(",");
}

async function canvasRegionSample(page: Page, region: [number, number, number, number]): Promise<number[]> {
  return page.locator(".myth-canvas canvas").evaluate((canvas: HTMLCanvasElement, box) => {
    const context = canvas.getContext("2d")!;
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    const sample: number[] = [];
    for (let row = 0; row < 32; row += 1) for (let column = 0; column < 32; column += 1) {
      const x = Math.floor(canvas.width * (box[0] + (box[1] - box[0]) * column / 31));
      const y = Math.floor(canvas.height * (box[2] + (box[3] - box[2]) * row / 31));
      const offset = (y * canvas.width + x) * 4;
      sample.push(pixels[offset], pixels[offset + 1], pixels[offset + 2]);
    }
    return sample;
  }, region);
}

function sampleDifference(before: number[], after: number[]): number {
  let changed = 0;
  for (let index = 0; index < before.length; index += 3) {
    const delta = Math.abs(before[index] - after[index]) + Math.abs(before[index + 1] - after[index + 1])
      + Math.abs(before[index + 2] - after[index + 2]);
    if (delta > 60) changed += 1;
  }
  return changed / (before.length / 3);
}

async function capturePresentationFrames(page: Page, prefix: string): Promise<number> {
  let captured = 0;
  for (let index = 0; index < 10; index += 1) {
    if (await page.getByTestId("myth-root").getAttribute("data-phase") !== "combat") break;
    const current = await canvasRegionSignature(page, [.04, .46, .12, .98]);
    try {
      await expect.poll(() => canvasRegionSignature(page, [.04, .46, .12, .98]), { timeout: 1_200 }).not.toBe(current);
    } catch {
      break;
    }
    if (await page.getByTestId("myth-root").getAttribute("data-phase") !== "combat") break;
    await saveEvidence(page, `${prefix}-${index}.png`);
    captured += 1;
  }
  return captured;
}

function lethalRun(run: RunView): RunView {
  return { ...run, revision: run.revision + 1, phase: "completed", epitaph: "毕方收翼退入火云。",
    combat: run.combat ? { ...run.combat, enemy: { ...run.combat.enemy, hp: 0 } } : null };
}

function lethalEvents(before: RunView, after: RunView, action: ActionRequest) {
  const state = { player: before.player, enemy: { hp: 0, block: 0, burn: 0, weak: 0 },
    turn: before.combat?.turn, energy: before.combat?.energy };
  return [
    { kind: "damage", text: "飞剑命中", source: "player", target: "enemy", card_id: "flying_sword",
      visual: "sword", amount: 99, state_after: state },
    { kind: "completed", text: after.epitaph!, source: "system", target: "enemy", visual: "defeat",
      state_after: state, action_id: action.action_id },
  ];
}
