import { expect, test, type Page } from "@playwright/test";

import type { ActionRequest, RunView } from "../src/api/types";
import type { StoredSession } from "../src/state/storage";

const sessionKey = "tiandao.cardRogue.session.v1";
const runGet = /\/api\/v2\/runs\/[^/]+$/;

test("真实档案恢复失败显式 reload 后保留原档案", async ({ page }) => {
  await startMap(page);
  const session = await readSession(page);
  await page.route(runGet, (route) => route.abort("failed"));
  await page.reload();
  await expect(page.getByTestId("reload-client")).toBeVisible();
  await expect(page.getByTestId("create-sword")).toHaveCount(0);
  expect(await readSession(page)).toEqual(session);
  await page.unroute(runGet);
  await page.getByTestId("reload-client").click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-revision", "0");
  expect(await readSession(page)).toEqual(session);
});

for (const fault of ["truncated-json", "5xx"] as const) {
  test(`真实提交后 ${fault} 保留原动作编号并从缓存恢复`, async ({ page }) => {
    await startMap(page);
    const requests: ActionRequest[] = [];
    await page.route("**/api/v2/runs/*/actions", async (route) => {
      requests.push(route.request().postDataJSON());
      if (requests.length !== 1) return route.continue();
      const committed = await route.fetch();
      expect(committed.status()).toBe(200);
      await route.fulfill({ status: fault === "5xx" ? 503 : 200, contentType: "application/json",
        body: fault === "5xx" ? '{"detail":"提交后响应不可用"}' : '{"run":' });
    });
    const nodeId = await page.locator('[data-testid^="map-node-"]:not([disabled])').first().getAttribute("data-testid");
    const node = page.getByTestId(nodeId!);
    await node.click();
    await expect(page.getByTestId("retry-action")).toHaveText(/重试原动作/);
    await expect(node).toBeDisabled();
    const authoritative = await readRun(page);
    expect(authoritative.revision).toBe(1);
    await page.getByTestId("retry-action").click();
    await expect(page.getByTestId("game-root")).toHaveAttribute("data-revision", "1");
    await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "combat");
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual(requests[0]);
    expect(await readRun(page)).toEqual(authoritative);
  });
}

test("真实 409 后同步断网只重试 GET，并保持过期命令锁", async ({ page }) => {
  await startMap(page);
  const session = await readSession(page);
  const stale = await readRun(page);
  const nodeId = stale.map.nodes.find((node) => node.available)!.id;
  const advanced = await page.request.post(`/api/v2/runs/${session.runId}/actions`, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
    data: { kind: "choose_node", node_id: nodeId, action_id: crypto.randomUUID(), expected_revision: 0 },
  });
  expect(advanced.status()).toBe(200);
  let posts = 0;
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/actions")) posts += 1; });
  await page.route(runGet, (route) => route.abort("failed"));
  await page.getByTestId(`map-node-${nodeId}`).click();
  await expect(page.getByTestId("retry-action")).toHaveText(/同步权威局面/);
  await expect(page.getByTestId(`map-node-${nodeId}`)).toBeDisabled();
  await page.unroute(runGet);
  await page.getByTestId("retry-action").click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-revision", "1");
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "combat");
  expect(posts).toBe(1);
});

async function startMap(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByTestId("create-sword").click();
  await expect(page.getByTestId("game-root")).toHaveAttribute("data-phase", "map");
}

async function readSession(page: Page): Promise<StoredSession> {
  return page.evaluate((key) => JSON.parse(localStorage.getItem(key)!), sessionKey);
}

async function readRun(page: Page): Promise<RunView> {
  const session = await readSession(page);
  const response = await page.request.get(`/api/v2/runs/${session.runId}`, {
    headers: { Authorization: `Bearer ${session.accessToken}` },
  });
  expect(response.status()).toBe(200);
  return (await response.json()).run;
}
