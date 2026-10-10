import { useCallback, useEffect, useState } from "react";
import { isMythClipKey, type MythClipKey } from "./mythAnimation";
import type { ActorMetrics } from "./mythLayout";

/** 原始种子路径、实际尺寸和可选 alpha 边界，均来自独立清单。 */
export interface MythSeed extends ActorMetrics { url: string }
/** 正式动作条带规格；空清单代表尚无序列帧，不从静态图合成动作。 */
export interface MythClip {
  url: string; frame_size: [number, number]; frames: number; fps: number;
  anchor: [number, number]; reference_height: number;
}
/** `/myth` 唯一资源协议；animations 可部分交付，cards 在正式卡面到位前保持空对象。 */
export interface MythManifest {
  status: string;
  seeds: { hero: MythSeed; bifang: MythSeed; scene: MythSeed };
  animations: Partial<Record<MythClipKey, MythClip>>;
  cards: Record<string, unknown>;
}
/** 素材读取状态；error 不携带旧清单，调用方必须显式重试。 */
export interface MythAssets {
  status: "loading" | "ready" | "error";
  manifest: MythManifest | null;
  error: string | null;
}

/** 核验独立三种子/条带，返回可加载清单；拒绝旧图替身和不完整规格，不做网络请求。 */
export function parseMythManifest(value: unknown): MythManifest {
  const root = object(value);
  const seeds = object(root.seeds);
  const animations = parseAnimations(root.animations);
  return { status: String(root.status), seeds: { hero: parseSeed(seeds.hero),
    bifang: parseSeed(seeds.bifang), scene: parseSeed(seeds.scene) }, animations, cards: object(root.cards) };
}

/** 加载独立素材；重试只重取清单，取消/卸载使旧 fetch 失效，失败保留明确错误。 */
export function useMythAssets(): [MythAssets, () => void] {
  const [attempt, setAttempt] = useState(0);
  const [assets, setAssets] = useState<MythAssets>({ status: "loading", manifest: null, error: null });
  useEffect(() => {
    const abort = new AbortController();
    setAssets({ status: "loading", manifest: null, error: null });
    void fetch("/assets/myth/manifest.json", { signal: abort.signal, cache: "no-cache" })
      .then(async (response) => {
        if (!response.ok) throw new Error("神话素材尚未就绪");
        const manifest = parseMythManifest(await response.json());
        if (!abort.signal.aborted) setAssets({ status: "ready", manifest, error: null });
      }).catch((cause: unknown) => {
        if (!abort.signal.aborted) setAssets({ status: "error", manifest: null,
          error: cause instanceof Error ? cause.message : "素材读取失败" });
      });
    return () => abort.abort();
  }, [attempt]);
  return [assets, useCallback(() => setAttempt((value) => value + 1), [])];
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("神话素材清单不完整");
  return value as Record<string, unknown>;
}

function dimensions(value: unknown): [number, number] {
  if (!Array.isArray(value) || value.length !== 2 || value.some((n) => !Number.isInteger(n) || n <= 0)) {
    throw new Error("素材像素规格无效");
  }
  return value as [number, number];
}

function assetPath(value: unknown): string {
  if (typeof value !== "string" || !/^\/assets\/myth\/[a-zA-Z0-9_/-]+\.(png|webp)$/.test(value)) {
    throw new Error("神话素材必须来自独立资源目录");
  }
  return value;
}

function parseSeed(value: unknown): MythSeed {
  const seed = object(value);
  const size = dimensions(seed.size);
  const bounds = seed.bounds;
  if (bounds !== undefined && (!Array.isArray(bounds) || bounds.length !== 4
    || bounds.some((n) => !Number.isFinite(n) || n < 0) || bounds[0] >= bounds[2] || bounds[1] >= bounds[3]
    || bounds[2] > size[0] || bounds[3] > size[1])) throw new Error("角色边界规格无效");
  return { url: assetPath(seed.url), size, bounds: bounds as number[] | undefined };
}

function parseClip(value: unknown): MythClip {
  const clip = object(value);
  if (!Number.isInteger(clip.frames) || Number(clip.frames) < 2 || !Number.isFinite(clip.fps)
    || Number(clip.fps) <= 0) throw new Error("动作条带规格无效");
  return { url: assetPath(clip.url), frame_size: dimensions(clip.frame_size),
    frames: Number(clip.frames), fps: Number(clip.fps), anchor: normalizedPoint(clip.anchor),
    reference_height: positiveNumber(clip.reference_height, "动作参考高度无效") };
}

function parseAnimations(value: unknown): Partial<Record<MythClipKey, MythClip>> {
  const parsed: Partial<Record<MythClipKey, MythClip>> = {};
  for (const [key, clip] of Object.entries(object(value))) {
    if (!isMythClipKey(key)) throw new Error("未知神话动作键");
    parsed[key] = parseClip(clip);
  }
  return parsed;
}

function normalizedPoint(value: unknown): [number, number] {
  if (!Array.isArray(value) || value.length !== 2
    || value.some((n) => !Number.isFinite(n) || n < 0 || n > 1)) throw new Error("动作锚点规格无效");
  return value as [number, number];
}

function positiveNumber(value: unknown, message: string): number {
  if (!Number.isFinite(value) || Number(value) <= 0) throw new Error(message);
  return Number(value);
}
