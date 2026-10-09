import { describe, expect, it } from "vitest";

import type { AssetManifest } from "../game/useAssets";
import { battleBackgroundPath } from "./battleAssets";

describe("battle assets", () => {
  it("天道裁决者使用 Boss 背景，普通敌人使用战斗背景", () => {
    const manifest: AssetManifest = {
      version: 1,
      status: "ready",
      characters: {},
      enemies: {},
      backgrounds: { battle: "/battle.webp", boss: "/boss.webp" },
      cards: {},
    };

    expect(battleBackgroundPath(manifest, "heaven_judge")).toBe("/boss.webp");
    expect(battleBackgroundPath(manifest, "sword_puppet")).toBe("/battle.webp");
  });
});
