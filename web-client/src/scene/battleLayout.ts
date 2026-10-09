import type { CSSProperties } from "react";

/** Phaser 渲染与 DOM 命中共用的只读场景坐标；不包含游戏规则。 */
export const BATTLE_LAYOUT = {
  width: 900,
  height: 360,
  cultivator: { x: 190, y: 210, width: 190, height: 280, radius: 76 },
  enemy: { x: 710, y: 190, width: 210, height: 300, radius: 86 },
} as const;

/** 可用区域或投影框的像素尺寸；读取布局，不保存权威局面。 */
export interface BattleViewport {
  width: number;
  height: number;
}

/** 接收可用区域像素尺寸，返回完整场景的等比尺寸；零区域返回零尺寸，无副作用。 */
export function fitBattleViewport(bounds: BattleViewport): BattleViewport {
  const ratio = BATTLE_LAYOUT.width / BATTLE_LAYOUT.height;
  const width = Math.max(0, Math.min(bounds.width, bounds.height * ratio));
  return { width, height: width / ratio };
}

/** 敌人整幅位图在统一坐标框内的百分比命中边界；不随文字、缩放或交互状态变化。 */
export const ENEMY_TARGET_STYLE: CSSProperties = {
  left: `${(BATTLE_LAYOUT.enemy.x - BATTLE_LAYOUT.enemy.width / 2) / BATTLE_LAYOUT.width * 100}%`,
  top: `${(BATTLE_LAYOUT.enemy.y - BATTLE_LAYOUT.enemy.height / 2) / BATTLE_LAYOUT.height * 100}%`,
  width: `${BATTLE_LAYOUT.enemy.width / BATTLE_LAYOUT.width * 100}%`,
  height: `${BATTLE_LAYOUT.enemy.height / BATTLE_LAYOUT.height * 100}%`,
};
