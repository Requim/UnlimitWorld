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
