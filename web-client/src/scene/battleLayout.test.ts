import { describe, expect, it } from "vitest";

import { fitBattleViewport } from "./battleLayout";

describe("battle viewport projection", () => {
  it.each([
    { width: 390, height: 500, expected: { width: 390, height: 156 } },
    { width: 1440, height: 400, expected: { width: 1000, height: 400 } },
    { width: 360, height: 170, expected: { width: 360, height: 144 } },
    { width: 0, height: 400, expected: { width: 0, height: 0 } },
    { width: 400, height: 0, expected: { width: 0, height: 0 } },
  ])("将 $width×$height 中的画布完整放入同一命中坐标框", ({ width, height, expected }) => {
    expect(fitBattleViewport({ width, height })).toEqual(expected);
  });
});
