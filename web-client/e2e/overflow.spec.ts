import { expect, test } from "@playwright/test";

for (const className of ["hand-zone", "choice-cards"]) {
  test(`${className} 桌面长列表首尾均可滚动访问`, async ({ page }) => {
    await page.goto("/");
    await page.evaluate((containerClass) => {
      document.body.innerHTML = `<div class="${containerClass}" data-testid="scroller">${Array.from(
        { length: 18 }, (_, index) => `<button class="card-tile" data-index="${index}">卡牌 ${index}</button>`,
      ).join("")}</div>`;
    }, className);
    const scroller = page.getByTestId("scroller");
    const first = scroller.locator(".card-tile").first();
    const last = scroller.locator(".card-tile").last();

    await expect.poll(async () => (await first.boundingBox())?.x).toBeGreaterThanOrEqual((await scroller.boundingBox())!.x);
    await scroller.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
    await expect.poll(async () => {
      const item = await last.boundingBox();
      const container = await scroller.boundingBox();
      return item && container ? item.x + item.width <= container.x + container.width + 1 : false;
    }).toBe(true);
  });
}

test("手机短屏 ready 卡面与选中详情保留完整规则", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 667 });
  await page.goto("/");
  await page.evaluate(() => {
    document.body.innerHTML = `<aside class="selected-card-detail" data-testid="selected-card-detail">
        <strong>万剑归宗+</strong>
        <span data-testid="rule">造成 12 点伤害，并获得两层剑意；若目标带有虚弱，再抽一张牌。升级：额外获得剑意。</span>
        <small>1 灵力 · 敌方目标</small>
      </aside>
      <div class="hand-zone" data-testid="short-hand">
      <button class="card-tile school-sword" data-testid="ready-card">
        <span class="card-cost" data-testid="cost">1</span><span class="card-school">御剑</span>
        <img class="card-art" alt="飞剑卡面" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">
        <strong data-testid="name">万剑归宗+</strong>
        <small data-testid="target">敌方目标</small>
      </button>
    </div>`;
  });
  const card = page.getByTestId("ready-card");
  const cardBox = await card.boundingBox();
  expect(cardBox?.height).toBeLessThanOrEqual(138);
  for (const testId of ["cost", "name", "target"]) {
    const child = await page.getByTestId(testId).boundingBox();
    expect(child && cardBox && child.y >= cardBox.y && child.y + child.height <= cardBox.y + cardBox.height).toBe(true);
  }
  const rule = page.getByTestId("rule");
  expect(await rule.evaluate((element) => element.scrollHeight <= element.clientHeight)).toBe(true);
  await expect(rule).toHaveText(/再抽一张牌。升级：额外获得剑意。/);
});

for (const width of [360, 390, 430]) {
  test(`${width}px 短屏状态、挑衅代价和选中详情不越界`, async ({ page }) => {
    await page.setViewportSize({ width, height: 740 });
    await page.goto("/");
    await page.evaluate(() => {
      document.body.innerHTML = `<section class="combat-view">
        <div class="combat-status" data-testid="status"><span>灵力 <b>3/3</b></span><span>剑意 <b>0</b></span><span>反伤 <b>0</b></span><span>雷罚 <b>0 × 8</b></span><span data-testid="last-status">牌堆 5 · 弃牌 0 · 消耗 0</span></div>
        <div class="battle-frame"></div>
        <div class="command-bar" data-testid="commands"><button class="taunt" data-testid="taunt"><svg viewBox="0 0 24 24" width="24" height="24"><path d="M12 2v20" /></svg><span class="command-label" data-testid="taunt-label">挑衅</span><span class="taunt-summary" data-testid="taunt-summary">灵力+1 · 天谴+8 · 敌攻+2/段</span></button><button class="end-turn" data-testid="end-turn">结束回合</button></div>
        <aside class="selected-card-detail" data-testid="detail"><strong>万剑归宗+</strong><span>造成 12 点伤害，并获得两层剑意；若目标带有虚弱，再抽一张牌。升级：额外获得剑意。</span><small>1 灵力 · 敌方目标</small></aside>
        <div class="hand-zone" data-testid="hand"><button class="card-tile"><strong>万剑归宗+</strong><small>敌方目标</small></button></div>
        <button class="cast-selected">点敌人出牌</button>
      </section>`;
    });
    await expectChildrenInside(page, "taunt", ["taunt-label", "taunt-summary"]);
    await expectChildrenInside(page, "commands", ["taunt", "end-turn"]);
    await expectVerticalChildrenInside(page, "status", ".combat-status > span");
    await expectVerticalChildrenInside(page, "detail", ".selected-card-detail > *");
    await expectNoVerticalOverlap(page, "commands", "detail");
    await expectNoVerticalOverlap(page, "detail", "hand");
    const status = page.getByTestId("status");
    await status.evaluate((element) => { element.scrollLeft = element.scrollWidth; });
    await expect.poll(() => rightEdgeVisible(page, "status", "last-status")).toBe(true);
  });
}

async function expectChildrenInside(page: import("@playwright/test").Page, parentId: string, childIds: string[]) {
  const parent = await page.getByTestId(parentId).boundingBox();
  for (const childId of childIds) {
    const child = await page.getByTestId(childId).boundingBox();
    expect(child && parent && child.x >= parent.x && child.x + child.width <= parent.x + parent.width + 1
      && child.y >= parent.y && child.y + child.height <= parent.y + parent.height + 1).toBe(true);
  }
}

async function expectVerticalChildrenInside(page: import("@playwright/test").Page, parentId: string, selector: string) {
  const parent = await page.getByTestId(parentId).boundingBox();
  for (const child of await page.locator(selector).all()) {
    const box = await child.boundingBox();
    expect(box && parent && box.y >= parent.y && box.y + box.height <= parent.y + parent.height + 1).toBe(true);
  }
}

async function expectNoVerticalOverlap(page: import("@playwright/test").Page, upperId: string, lowerId: string) {
  const upper = await page.getByTestId(upperId).boundingBox();
  const lower = await page.getByTestId(lowerId).boundingBox();
  expect(upper && lower && upper.y + upper.height <= lower.y + 1).toBe(true);
}

async function rightEdgeVisible(page: import("@playwright/test").Page, parentId: string, childId: string) {
  const parent = await page.getByTestId(parentId).boundingBox();
  const child = await page.getByTestId(childId).boundingBox();
  return Boolean(parent && child && child.x + child.width <= parent.x + parent.width + 1);
}
