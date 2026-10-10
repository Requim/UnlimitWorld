import { expect, it } from "vitest";
import { parseMythManifest } from "./mythAssets";

const seeds = {
  hero: { url: "/assets/myth/seeds/hero.png", size: [2352, 3520] },
  bifang: { url: "/assets/myth/seeds/bifang.png", size: [2352, 3520] },
  scene: { url: "/assets/myth/seeds/zhang-e-mountain.webp", size: [3840, 2160] },
};

it("真实三种子可以载入，空动画不伪装正式动作", () => {
  const manifest = parseMythManifest({ status: "seed-review", seeds, animations: {}, cards: {} });
  expect(manifest.seeds.hero.size).toEqual([2352, 3520]);
  expect(Object.keys(manifest.animations)).toHaveLength(0);
});

it("动作条带必须读取固定键、帧规格、速率和归一化锚点", () => {
  const clip = { url: "/assets/myth/animations/hero-sword.png", frame_size: [960, 1280],
    frames: 4, fps: 8, anchor: [0.5, 0.94], reference_height: 634 };
  const manifest = parseMythManifest({ status: "animation-review", seeds,
    animations: { hero_sword: clip }, cards: {} });
  expect(manifest.animations.hero_sword).toEqual(clip);
});

it.each([
  { hero_sword: { url: "/assets/myth/animations/hero-sword.png", frame_size: [960, 1280], frames: 4, fps: 8 } },
  { hero_sword: { url: "/assets/myth/animations/hero-sword.png", frame_size: [960, 1280], frames: 4, fps: 8,
    anchor: [1.2, 0.94], reference_height: 634 } },
  { hero_sword: { url: "/assets/myth/animations/hero-sword.png", frame_size: [960, 1280], frames: 4, fps: 8,
    anchor: [0.5, 0.94], reference_height: 0 } },
  { hero_jump: { url: "/assets/myth/animations/hero-jump.png", frame_size: [960, 1280], frames: 4, fps: 8,
    anchor: [0.5, 0.94], reference_height: 634 } },
])("缺锚点、越界锚点或未知动作键会拒绝载入", (animations) => {
  expect(() => parseMythManifest({ status: "animation-review", seeds, animations, cards: {} })).toThrow();
});

it.each([
  { ...seeds, hero: { ...seeds.hero, url: "/assets/characters/cultivator.png" } },
  { ...seeds, hero: { ...seeds.hero, size: [0, 3520] } },
  { ...seeds, hero: { ...seeds.hero, url: "https://other.invalid/hero.png" } },
])("缺失或旧图路径不得作为神话资源载入", (invalid) => {
  expect(() => parseMythManifest({ status: "seed-review", seeds: invalid, animations: {}, cards: {} })).toThrow();
});
