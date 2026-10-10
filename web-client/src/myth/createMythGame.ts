import * as Phaser from "phaser";
import type { GameEvent } from "../api/types";
import { clipKeysForEvent, impactIndexForClips, mythClipPose, type MythClipKey } from "./mythAnimation";
import type { MythClip, MythManifest } from "./mythAssets";
import { isTerminalMythClip, waitForMythAnimation, type MythPlaybackResult } from "./mythClipPlayback";
import { mythLayout, type ActorLayout } from "./mythLayout";
import { missingTextureKeys, mythClipTexture } from "./mythRuntimeAssets";
import type { PresentationAdapter } from "./presentationQueue";

/** Phaser 表现门面；present 只播权威事件，resize 不改规则，destroy 取消在途反馈。 */
export interface MythSceneAdapter {
  present: PresentationAdapter;
  resize: (width: number, height: number) => void;
  setReducedMotion: (value: boolean) => void;
  destroy: () => void;
}
interface World {
  scene: Phaser.Scene | null; hero: Phaser.GameObjects.Sprite | null; bifang: Phaser.GameObjects.Sprite | null;
  background: Phaser.GameObjects.Image | null; width: number; height: number;
  manifest: MythManifest; pending: Set<() => void>; reducedMotion: boolean; loadFailed: boolean;
  generations: Record<"hero" | "bifang", number>; destroyed: boolean;
}

/** 在 parent 加载独立种子及已登记条带；ready 后可播放，loaderror 显式通知，返回销毁门面。 */
export function createMythGame(parent: HTMLElement, manifest: MythManifest, width: number, height: number,
  reducedMotion: boolean, ready: (adapter: MythSceneAdapter) => void,
  error: (message: string) => void): MythSceneAdapter {
  const world: World = { scene: null, hero: null, bifang: null, background: null,
    width, height, manifest, pending: new Set(), reducedMotion, loadFailed: false,
    generations: { hero: 0, bifang: 0 }, destroyed: false };
  const game = new Phaser.Game({ type: Phaser.CANVAS, parent, width: Math.max(1, width), height: Math.max(1, height),
    transparent: true, render: { antialias: true }, scale: { mode: Phaser.Scale.NONE },
    scene: {
      preload(this: Phaser.Scene) { preload(this, world, error); },
      create(this: Phaser.Scene) { createWorld(this, world, error) && ready(adapter); },
    } });
  const adapter: MythSceneAdapter = {
    present: (event, signal) => presentEvent(world, event, signal),
    resize: (w, h) => { world.width = w; world.height = h; game.scale.resize(Math.max(1, w), Math.max(1, h)); positionWorld(world); },
    setReducedMotion: (value) => setReducedMotion(world, value),
    destroy: () => destroyWorld(world, game),
  };
  return adapter;
}

function preload(scene: Phaser.Scene, world: World, error: (message: string) => void): void {
  for (const [key, seed] of Object.entries(world.manifest.seeds)) scene.load.image(`myth-${key}`, seed.url);
  for (const [key, clip] of Object.entries(world.manifest.animations)) {
    scene.load.spritesheet(mythClipTexture(key), clip.url, { frameWidth: clip.frame_size[0], frameHeight: clip.frame_size[1],
      endFrame: clip.frames - 1 });
  }
  scene.load.on("loaderror", () => { world.loadFailed = true; error("神话位图加载失败"); });
}

function createWorld(scene: Phaser.Scene, world: World, error: (message: string) => void): boolean {
  const missing = missingTextureKeys(world.manifest, (key) => scene.textures.exists(key));
  if (world.loadFailed || missing.length > 0) {
    if (!world.loadFailed) error(`神话纹理不完整：${missing.join("、")}`);
    return false;
  }
  world.scene = scene;
  world.background = scene.add.image(0, 0, "myth-scene");
  world.hero = scene.add.sprite(0, 0, "myth-hero");
  world.bifang = scene.add.sprite(0, 0, "myth-bifang");
  for (const [key, clip] of Object.entries(world.manifest.animations)) {
    const animation = scene.anims.create({ key,
      frames: scene.anims.generateFrameNumbers(mythClipTexture(key), { start: 0, end: clip.frames - 1 }),
      frameRate: clip.fps, repeat: key.endsWith("_idle") ? -1 : 0 });
    if (!animation) { error(`神话动作登记失败：${key}`); return false; }
  }
  positionWorld(world);
  return true;
}

function positionWorld(world: World): void {
  if (!world.scene || !world.background || !world.hero || !world.bifang) return;
  const { width, height, manifest } = world;
  const layout = mythLayout(width, height, manifest.seeds.hero, manifest.seeds.bifang);
  const scale = Math.max(width / manifest.seeds.scene.size[0], height / manifest.seeds.scene.size[1]);
  world.background.setPosition(width / 2, height / 2).setScale(scale);
  restoreActor(world, "hero", layout.hero);
  restoreActor(world, "bifang", layout.bifang);
}

function positionActor(sprite: Phaser.GameObjects.Sprite, actor: ActorLayout): void {
  sprite.setPosition(actor.x, actor.y).setOrigin(actor.originX, actor.originY).setDisplaySize(actor.width, actor.height);
}

function presentEvent(world: World, event: GameEvent, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve();
  if (!world.scene) return Promise.reject(new Error("战场尚未就绪"));
  let feedback: Phaser.GameObjects.Graphics | null = null;
  const showImpact = () => { feedback ??= spellFeedback(world.scene!, world, event); };
  return playEventClips(world, clipKeysForEvent(event), signal, showImpact)
    .finally(() => feedback?.destroy());
}

async function playEventClips(world: World, keys: MythClipKey[], signal: AbortSignal,
  showImpact: () => void): Promise<void> {
  if (world.reducedMotion) {
    showImpact();
    await waitForDelay(world, signal, 60);
    return;
  }
  const playable = keys.flatMap((key) => {
    const clip = world.manifest.animations[key];
    const actor = key.startsWith("bifang") ? world.bifang : world.hero;
    return clip && actor ? [{ key, clip, actor }] : [];
  });
  if (playable.length === 0) {
    showImpact();
    await waitForDelay(world, signal, 140);
    return;
  }
  const impactIndex = impactIndexForClips(playable.map(({ key }) => key));
  for (const [index, item] of playable.entries()) {
    if (index === impactIndex) showImpact();
    if (signal.aborted) break;
    const result = await playClip(world, item.actor, item.key, item.clip, signal);
    if (result === "cancelled") break;
  }
  if (impactIndex === playable.length && !signal.aborted) {
    showImpact();
    await waitForDelay(world, signal, 140);
  }
}

function waitForDelay(world: World, signal: AbortSignal, duration: number): Promise<void> {
  const scene = world.scene;
  if (!scene || signal.aborted) return Promise.resolve();
  return new Promise<void>((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      timer.remove(false);
      signal.removeEventListener("abort", finish);
      world.pending.delete(finish);
      resolve();
    };
    const timer = scene.time.delayedCall(duration, finish);
    world.pending.add(finish);
    signal.addEventListener("abort", finish, { once: true });
    if (signal.aborted) finish();
  });
}

function setReducedMotion(world: World, value: boolean): void {
  world.reducedMotion = value;
  invalidatePlaybacks(world);
  restoreNamedActor(world, "hero");
  restoreNamedActor(world, "bifang");
}

async function playClip(world: World, actor: Phaser.GameObjects.Sprite, key: MythClipKey,
  clip: MythClip, signal: AbortSignal): Promise<MythPlaybackResult> {
  const name = actorName(key);
  const generation = ++world.generations[name];
  positionClip(world, actor, key, clip);
  const result = await waitForMythAnimation(actor, key, signal, (cancel) => trackCancellation(world, cancel));
  restoreAfterPlayback(world, name, key, generation, result);
  return result;
}

function positionClip(world: World, actor: Phaser.GameObjects.Sprite, key: MythClipKey, clip: MythClip): void {
  const layout = mythLayout(world.width, world.height, world.manifest.seeds.hero, world.manifest.seeds.bifang);
  const name = key.startsWith("bifang") ? "bifang" : "hero";
  const target = key.startsWith("bifang") ? layout.bifang : layout.hero;
  const seed = world.manifest.seeds[name];
  const visibleHeight = target.height * visibleRatio(seed);
  const pose = mythClipPose(target.x, target.y, visibleHeight, world.width, clip);
  actor.setPosition(pose.x, pose.y).setOrigin(...pose.origin).setDisplaySize(pose.width, pose.height);
}

function restoreAfterPlayback(world: World, name: "hero" | "bifang", key: MythClipKey,
  generation: number, result: MythPlaybackResult): void {
  if (world.destroyed || world.generations[name] !== generation) return;
  if (result === "cancelled" || !isTerminalMythClip(key)) restoreNamedActor(world, name);
}

function actorName(key: MythClipKey): "hero" | "bifang" {
  return key.startsWith("bifang") ? "bifang" : "hero";
}

function trackCancellation(world: World, cancel: () => void): () => void {
  world.pending.add(cancel);
  return () => world.pending.delete(cancel);
}

function invalidatePlaybacks(world: World): void {
  world.generations.hero += 1;
  world.generations.bifang += 1;
  [...world.pending].forEach((cancel) => cancel());
  world.pending.clear();
}

function destroyWorld(world: World, game: Phaser.Game): void {
  world.destroyed = true;
  invalidatePlaybacks(world);
  game.destroy(true);
}

function restoreNamedActor(world: World, name: "hero" | "bifang"): void {
  const layout = mythLayout(world.width, world.height, world.manifest.seeds.hero, world.manifest.seeds.bifang);
  const actor = name === "hero" ? world.hero : world.bifang;
  if (actor) restoreActor(world, name, name === "hero" ? layout.hero : layout.bifang);
}

function restoreActor(world: World, name: "hero" | "bifang", layout: ActorLayout): void {
  const actor = name === "hero" ? world.hero : world.bifang;
  if (!actor) return;
  const key = `${name}_idle` as MythClipKey;
  const idle = world.manifest.animations[key];
  actor.stop();
  if (idle && !world.reducedMotion) {
    positionClip(world, actor, key, idle);
    actor.play(key);
  }
  else positionActor(actor.setTexture(`myth-${name}`), layout);
}

function visibleRatio(seed: MythManifest["seeds"]["hero"]): number {
  const bounds = seed.bounds ?? [0, 0, seed.size[0], seed.size[1]];
  return (bounds[3] - bounds[1]) / seed.size[1];
}

function spellFeedback(scene: Phaser.Scene, world: World, event: GameEvent): Phaser.GameObjects.Graphics {
  const graphics = scene.add.graphics();
  const layout = mythLayout(world.width, world.height, world.manifest.seeds.hero, world.manifest.seeds.bifang);
  const target = event.target === "player" ? layout.hero : layout.bifang;
  const source = event.source === "enemy" ? layout.bifang : layout.hero;
  const color = event.visual === "fire" ? 0xd64732 : event.visual === "thunder" ? 0xe5e4ba : 0x91dbd2;
  graphics.lineStyle(3, color, .9);
  if (event.visual === "sword" || event.visual === "fire") {
    graphics.lineBetween(source.x, source.y - source.height * .55, target.x, target.y - target.height * .48);
  } else if (event.visual === "thunder") {
    graphics.lineBetween(target.x - 25, 0, target.x + 12, world.height * .35);
    graphics.lineBetween(target.x + 12, world.height * .35, target.x, target.y - target.height * .4);
  } else if (event.visual === "shield") {
    graphics.strokeEllipse(target.x, target.y - target.height * .45, target.width * 1.05, target.height * .85);
  }
  return graphics;
}
