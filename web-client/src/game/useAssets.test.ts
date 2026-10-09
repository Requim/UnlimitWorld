import { describe, expect, it } from "vitest";

import { REQUIRED_CARD_ASSETS, REQUIRED_ENEMY_ASSETS, resolveAssetManifest, type AssetManifest } from "./useAssets";

describe("asset manifest", () => {
  it("ready 必须覆盖全部卡牌、敌人、角色与双战场背景", () => {
    const manifest = completeManifest();
    delete manifest.cards[REQUIRED_CARD_ASSETS[0]];
    delete manifest.backgrounds.boss;

    const state = resolveAssetManifest(manifest);

    expect(state.status).toBe("error");
    expect(state.message).toContain(REQUIRED_CARD_ASSETS[0]);
    expect(state.message).toContain("backgrounds.boss");
  });

  it("完整 ready manifest 可提供卡面与 Boss 背景路径", () => {
    const state = resolveAssetManifest(completeManifest());
    expect(state.status).toBe("ready");
    expect(state.manifest?.cards.flying_sword).toBe("/cards/flying_sword.webp");
    expect(state.manifest?.backgrounds.boss).toBe("/backgrounds/boss.webp");
  });
});

function completeManifest(): AssetManifest {
  return {
    version: 1, status: "ready", characters: { cultivator: "/characters/cultivator.png" },
    backgrounds: { battle: "/backgrounds/battle.webp", boss: "/backgrounds/boss.webp" },
    enemies: Object.fromEntries(REQUIRED_ENEMY_ASSETS.map((id) => [id, `/enemies/${id}.png`])),
    cards: Object.fromEntries(REQUIRED_CARD_ASSETS.map((id) => [id, `/cards/${id}.webp`])),
  };
}
