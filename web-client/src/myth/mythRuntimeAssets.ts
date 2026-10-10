import type { MythManifest } from "./mythAssets";

/** 返回动作清单键对应的 Phaser 纹理键。 */
export function mythClipTexture(key: string): string {
  return `myth-clip-${key}`;
}

/** 列出清单中未载入的种子与已登记动作纹理；未登记动作不属于运行时失败。 */
export function missingTextureKeys(manifest: MythManifest, exists: (key: string) => boolean): string[] {
  const required = ["hero", "bifang", "scene"].map((key) => `myth-${key}`);
  required.push(...Object.keys(manifest.animations).map(mythClipTexture));
  return required.filter((key) => !exists(key));
}
