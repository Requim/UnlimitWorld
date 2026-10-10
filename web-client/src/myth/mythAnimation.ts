import type { GameEvent } from "../api/types";
import type { MythClip } from "./mythAssets";

/** 样板运行时允许的固定动作键；缺项表示对应真实姿态动作尚未交付。 */
export const REQUIRED_MYTH_CLIPS = [
  "hero_idle", "hero_sword", "hero_cast", "hero_hurt", "hero_defeat",
  "bifang_idle", "bifang_charge", "bifang_strike", "bifang_hurt", "bifang_retreat",
] as const;

export type MythClipKey = typeof REQUIRED_MYTH_CLIPS[number];

/** 规范化动作帧在当前战场中的最终位置、尺寸与脚锚。 */
export interface MythClipPose {
  x: number; y: number; width: number; height: number; origin: [number, number];
}

/** 按布局可见身高和 clip 参考高度计算最终帧几何；会横向夹紧但不裁剪或二次缩放。 */
export function mythClipPose(x: number, y: number, visibleHeight: number,
  worldWidth: number, clip: MythClip): MythClipPose {
  const scale = visibleHeight / clip.reference_height;
  const width = clip.frame_size[0] * scale;
  const height = clip.frame_size[1] * scale;
  return { x: clampAnchor(x, worldWidth, width, clip.anchor[0]), y,
    width, height, origin: clip.anchor };
}

/** 仅依据服务端结构化字段选择动作；返回 null 时保持静态 seed，不伪造姿态变化。 */
export function clipKeyForEvent(event: GameEvent): MythClipKey | null {
  if (event.visual === "defeat") return event.target === "player" ? "hero_defeat" : "bifang_retreat";
  if (event.visual === "hit") return event.target === "player" ? "hero_hurt" : "bifang_hurt";
  if (event.source === "enemy") return enemyClip(event.visual);
  if (event.source === "player") return heroClip(event.visual);
  return null;
}

/** 将单条权威伤害展开为有序出招/受击动作；不复制或改变服务端状态快照。 */
export function clipKeysForEvent(event: GameEvent): MythClipKey[] {
  const key = clipKeyForEvent(event);
  if (!key) return [];
  if (isPlayerDamage(event)) return [key, "bifang_hurt"];
  if (isEnemyDamage(event)) return ["bifang_strike", "hero_hurt"];
  return [key];
}

/** 返回技术反馈插入位置：出招后、受击前；单独受击在动作前显示。 */
export function impactIndexForClips(keys: MythClipKey[]): number {
  if (keys.length > 1) return 1;
  return keys[0] && /_(hurt|defeat|retreat)$/.test(keys[0]) ? 0 : keys.length;
}

/** 返回清单缺失的必需动作键，供 UI 如实展示未完成状态。 */
export function missingClipKeys(clips: Record<string, unknown>): MythClipKey[] {
  return REQUIRED_MYTH_CLIPS.filter((key) => !clips[key]);
}

/** 判断外部 manifest 键是否属于固定动作协议。 */
export function isMythClipKey(value: string): value is MythClipKey {
  return (REQUIRED_MYTH_CLIPS as readonly string[]).includes(value);
}

function heroClip(visual: GameEvent["visual"]): MythClipKey {
  if (visual === "sword") return "hero_sword";
  if (["fire", "shield", "thunder"].includes(visual ?? "")) return "hero_cast";
  return "hero_idle";
}

function enemyClip(visual: GameEvent["visual"]): MythClipKey {
  if (visual === "shield") return "bifang_charge";
  if (["fire", "sword", "thunder"].includes(visual ?? "")) return "bifang_strike";
  return "bifang_idle";
}

function isPlayerDamage(event: GameEvent): boolean {
  return event.kind === "damage" && event.source === "player" && event.target !== "player" && Number(event.amount) > 0;
}

function isEnemyDamage(event: GameEvent): boolean {
  return event.source === "enemy" && event.target === "player" && event.visual === "hit" && Number(event.amount) > 0;
}

function clampAnchor(x: number, worldWidth: number, displayWidth: number, anchorX: number): number {
  const minimum = displayWidth * anchorX;
  const maximum = worldWidth - displayWidth * (1 - anchorX);
  if (minimum > maximum) return worldWidth / 2;
  return Math.min(maximum, Math.max(minimum, x));
}
