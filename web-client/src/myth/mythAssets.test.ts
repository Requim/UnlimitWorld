import { expect, it } from "vitest";
import { parseMythManifest } from "./mythAssets";

const seeds = {
  hero: { url: "/assets/myth/seeds/hero.png", size: [2352, 3520] },
  bifang: { url: "/assets/myth/seeds/bifang.png", size: [2352, 3520] },
  scene: { url: "/assets/myth/seeds/zhang-e-mountain.webp", size: [3840, 2160] },
};

const root = { version: "bifang-v1", status: "seed-review", seeds, animations: {}, cards: {} };

it("真实三种子可以载入，空动画不伪装正式动作", () => {
  const manifest = parseMythManifest(root);
  expect(manifest.version).toBe("bifang-v1");
  expect(manifest.seeds.hero.size).toEqual([2352, 3520]);
  expect(Object.keys(manifest.animations)).toHaveLength(0);
});

it("动作条带必须读取固定键、帧规格、速率和归一化锚点", () => {
  const clip = { url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768],
    frames: 4, fps: 8, anchor: [0.5, 1], reference_height: 634 };
  const manifest = parseMythManifest({ ...root, status: "animation-review",
    animations: { hero_sword: clip }, cards: {} });
  expect(manifest.animations.hero_sword).toEqual(clip);
});

it.each([
  ["hero_idle", 12, 12, 3],
  ["hero_sword", 16, 24, 4],
  ["hero_hurt", 12, 24, 3],
  ["bifang_strike", 16, 24, 4],
  ["bifang_retreat", 12, 24, 3],
] as const)("smooth-v2 %s 严格读取真实多帧网格", (key, frames, fps, rows) => {
  const clip = { url: `/assets/myth/animations/${key}.png`, frame_size: [704, 704],
    frames, fps, anchor: [0.5, 1], reference_height: 620,
    profile: "smooth-v2", columns: 4, rows };
  const manifest = parseMythManifest({ ...root, status: "animation-review",
    animations: { [key]: clip }, cards: {} });
  expect(manifest.animations[key]).toEqual(clip);
});

it.each([
  { profile: "smooth-v3", columns: 4, rows: 4, frames: 16, fps: 24, frame_size: [704, 704] },
  { profile: "smooth-v2", columns: 3, rows: 4, frames: 16, fps: 24, frame_size: [704, 704] },
  { profile: "smooth-v2", columns: 4, rows: 3, frames: 16, fps: 24, frame_size: [704, 704] },
  { profile: "smooth-v2", columns: 4, rows: 4, frames: 12, fps: 24, frame_size: [704, 704] },
  { profile: "smooth-v2", columns: 4, rows: 4, frames: 16, fps: 12, frame_size: [704, 704] },
  { profile: "smooth-v2", columns: 4, rows: 4, frames: 16, fps: 24, frame_size: [768, 768] },
])("smooth-v2 未知档位或错误帧数/fps/几何会拒绝", (invalid) => {
  const clip = { url: "/assets/myth/animations/hero_sword.png", anchor: [0.5, 1],
    reference_height: 620, ...invalid };
  expect(() => parseMythManifest({ ...root, status: "animation-review",
    animations: { hero_sword: clip }, cards: {} })).toThrow();
});

it.each([
  { hero_sword: { url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768], frames: 4, fps: 8 } },
  { hero_sword: { url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768], frames: 4, fps: 8,
    anchor: [1.2, 1], reference_height: 634 } },
  { hero_sword: { url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768], frames: 4, fps: 8,
    anchor: [0.5, 1], reference_height: 0 } },
  { hero_jump: { url: "/assets/myth/animations/hero-jump.png", frame_size: [768, 768], frames: 4, fps: 8,
    anchor: [0.5, 1], reference_height: 634 } },
])("缺锚点、越界锚点或未知动作键会拒绝载入", (animations) => {
  expect(() => parseMythManifest({ ...root, status: "animation-review", animations })).toThrow();
});

it.each([
  { ...root, version: "bifang-v2" },
  { ...root, status: "ready" },
  { ...root, status: "animation-review", animations: { hero_idle: {
    url: "/assets/myth/animations/hero-idle.png", frame_size: [768, 768], frames: 4, fps: 8,
    anchor: [0.5, 1], reference_height: 762 } } },
  { ...root, status: "animation-review", animations: { hero_sword: {
    url: "/assets/myth/animations/hero-sword.png", frame_size: [960, 768], frames: 4, fps: 8,
    anchor: [0.5, 1], reference_height: 634 } } },
  { ...root, status: "animation-review", animations: { hero_sword: {
    url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768], frames: 3, fps: 8,
    anchor: [0.5, 1], reference_height: 634 } } },
  { ...root, status: "animation-review", animations: { hero_sword: {
    url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768], frames: 4, fps: 4,
    anchor: [0.5, 1], reference_height: 634 } } },
  { ...root, status: "animation-review", animations: { hero_sword: {
    url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768], frames: 4, fps: 8,
    anchor: [0.5, 0.94], reference_height: 634 } } },
  { ...root, status: "animation-review", animations: { hero_sword: {
    url: "/assets/myth/animations/hero-sword.png", frame_size: [768, 768], frames: 4, fps: 8,
    anchor: [0.5, 1], reference_height: 634, columns: 4, rows: 1 } } },
])("非当前版本、状态或动作协议会拒绝载入", (invalid) => {
  expect(() => parseMythManifest(invalid)).toThrow();
});

it.each([
  { ...seeds, hero: { ...seeds.hero, url: "/assets/characters/cultivator.png" } },
  { ...seeds, hero: { ...seeds.hero, size: [0, 3520] } },
  { ...seeds, hero: { ...seeds.hero, url: "https://other.invalid/hero.png" } },
])("缺失或旧图路径不得作为神话资源载入", (invalid) => {
  expect(() => parseMythManifest({ ...root, seeds: invalid })).toThrow();
});
