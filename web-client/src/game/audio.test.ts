import { describe, expect, it } from "vitest";

import { toneForEvent } from "./audio";

describe("audio feedback", () => {
  it("按伤害、奖励和雷罚事件选择不同提示音", () => {
    expect(toneForEvent("damage")).toBe(170);
    expect(toneForEvent("reward")).toBe(520);
    expect(toneForEvent("thunder")).toBe(95);
  });
});
