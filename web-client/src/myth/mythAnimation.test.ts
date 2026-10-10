import { expect, it } from "vitest";

import type { GameEvent } from "../api/types";
import { clipKeyForEvent, clipKeysForEvent, impactIndexForClips, missingClipKeys, mythClipPose,
  REQUIRED_MYTH_CLIPS } from "./mythAnimation";

it.each([
  [{ source: "player", visual: "sword" }, "hero_sword"],
  [{ source: "player", visual: "fire" }, "hero_cast"],
  [{ source: "enemy", visual: "shield" }, "bifang_charge"],
  [{ source: "enemy", visual: "fire" }, "bifang_strike"],
  [{ target: "player", visual: "hit" }, "hero_hurt"],
  [{ target: "enemy", visual: "hit" }, "bifang_hurt"],
  [{ target: "player", visual: "defeat" }, "hero_defeat"],
  [{ target: "enemy", visual: "defeat" }, "bifang_retreat"],
] as Array<[Partial<GameEvent>, string]>)("结构化事件 %j 选择 %s", (event, key) => {
  expect(clipKeyForEvent({ kind: "test", text: "不参与判断", ...event })).toBe(key);
});

it("缺少动作会返回固定清单，不能用静态 seed 冒充", () => {
  expect(missingClipKeys({})).toEqual(REQUIRED_MYTH_CLIPS);
});

it("真实伤害按出招再受击的顺序播放", () => {
  expect(clipKeysForEvent({ kind: "damage", text: "飞剑命中", source: "player",
    target: "bifang", visual: "sword", amount: 6 })).toEqual(["hero_sword", "bifang_hurt"]);
  expect(clipKeysForEvent({ kind: "enemy_damage", text: "受到伤害", source: "enemy",
    target: "player", visual: "hit", amount: 5 })).toEqual(["bifang_strike", "hero_hurt"]);
});

it("技术反馈位于出招之后、受击之前", () => {
  expect(impactIndexForClips(["hero_sword", "bifang_hurt"])).toBe(1);
  expect(impactIndexForClips(["hero_cast"])).toBe(1);
  expect(impactIndexForClips(["hero_hurt"])).toBe(0);
});

it("按可见布局高度缩放规范化 clip，不继承 seed 纹理比例", () => {
  const pose = mythClipPose(294, 396, 286, 1280, {
    url: "/assets/myth/animations/hero_sword.png", frame_size: [768, 768], frames: 4, fps: 8,
    anchor: [.5, 1], reference_height: 634,
  });
  expect(pose.width).toBeCloseTo(346.46, 1);
  expect(pose.height).toBeCloseTo(346.46, 1);
  expect(pose.y).toBe(396);
});
