import { expect, it } from "vitest";

import publishedManifest from "../../public/assets/myth/manifest.json";
import { parseMythManifest } from "./mythAssets";
import { missingTextureKeys } from "./mythRuntimeAssets";

it("九条已登记动作均需载入，未登记退场动作保持未完成边界", () => {
  const manifest = parseMythManifest(publishedManifest);
  const loaded = new Set(["myth-hero", "myth-bifang", "myth-scene",
    ...Object.keys(manifest.animations).map((key) => `myth-clip-${key}`)]);

  expect(Object.keys(manifest.animations)).toHaveLength(9);
  expect(manifest.animations.bifang_retreat).toBeUndefined();
  expect(missingTextureKeys(manifest, (key) => loaded.has(key))).toEqual([]);

  loaded.delete("myth-clip-hero_sword");
  expect(missingTextureKeys(manifest, (key) => loaded.has(key))).toEqual(["myth-clip-hero_sword"]);
});
