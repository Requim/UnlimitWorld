import { expect, it } from "vitest";

import { mythLayout } from "./mythLayout";

it.each([[1440, 610], [390, 445], [430, 520], [360, 365]])(
  "全景 %sx%s 人物完整，DOM 命中与毕方位图同一边界", (width, height) => {
    const layout = mythLayout(width, height);
    for (const actor of [layout.hero, layout.bifang]) {
      expect(actor.x - actor.width / 2).toBeGreaterThanOrEqual(0);
      expect(actor.x + actor.width / 2).toBeLessThanOrEqual(width);
      expect(actor.y - actor.height).toBeGreaterThanOrEqual(0);
      expect(actor.y).toBeLessThanOrEqual(height);
    }
    expect(layout.target.left).toBe(layout.bifang.x - layout.bifang.width / 2);
    expect(layout.target.top).toBe(layout.bifang.y - layout.bifang.height);
    expect(layout.target.width).toBe(layout.bifang.width);
    expect(layout.target.height).toBe(layout.bifang.height);
    expect(layout.bifang.height).toBeGreaterThan(layout.hero.height);
  },
);
