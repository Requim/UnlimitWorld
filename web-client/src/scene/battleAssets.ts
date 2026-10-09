import type { AssetManifest } from "../game/useAssets";

/** 返回敌人对应的战场背景路径；天道裁决者使用 Boss 专属背景。 */
export function battleBackgroundPath(manifest: AssetManifest, enemyId: string): string {
  return enemyId === "heaven_judge" ? manifest.backgrounds.boss : manifest.backgrounds.battle;
}
