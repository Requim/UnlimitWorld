import * as Phaser from "phaser";

import type { AssetState } from "../game/useAssets";
import { battleBackgroundPath } from "./battleAssets";
import type { BattleSceneAdapter, BattleSnapshot } from "./battleRuntime";

interface BattleData {
  snapshot: BattleSnapshot;
  assets: AssetState;
  onError: (message: string) => void;
  scene: Phaser.Scene | null;
  dynamicLayer: Phaser.GameObjects.Container | null;
}

/** 创建可增量更新的 Phaser 适配器；规则状态只读，destroy 释放画布。 */
export function createBattleGame(
  parent: HTMLElement,
  initial: BattleSnapshot,
  assets: AssetState,
  onError: (message: string) => void,
): BattleSceneAdapter {
  const data: BattleData = { snapshot: initial, assets, onError, scene: null, dynamicLayer: null };
  const game = new Phaser.Game({
    type: Phaser.AUTO, parent, width: 900, height: 360, transparent: true,
    render: { antialias: true },
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
    scene: createBattleScene(data),
  });
  return {
    render(snapshot, emitEffects) {
      data.snapshot = snapshot;
      if (data.scene) renderSnapshot(data.scene, data, emitEffects);
    },
    destroy() { game.destroy(true); },
  };
}

function createBattleScene(data: BattleData): Phaser.Types.Scenes.SettingsConfig & Phaser.Types.Scenes.CreateSceneFromObjectConfig {
  return {
    key: "BattleScene",
    preload(this: Phaser.Scene) { preloadAssets(this, data); },
    create(this: Phaser.Scene) {
      data.scene = this;
      drawStage(this, data);
      renderSnapshot(this, data, true);
    },
  };
}

function preloadAssets(scene: Phaser.Scene, data: BattleData): void {
  if (data.assets.status !== "ready" || !data.assets.manifest) return;
  const manifest = data.assets.manifest;
  scene.load.image("stage-bg", battleBackgroundPath(manifest, data.snapshot.combat.enemy.id));
  scene.load.image("cultivator", manifest.characters.cultivator);
  scene.load.image("enemy", manifest.enemies[data.snapshot.combat.enemy.id]);
  scene.load.on("loaderror", () => data.onError("位图加载失败，请检查资源文件后重试"));
}

function drawStage(scene: Phaser.Scene, data: BattleData): void {
  const hasArt = scene.textures.exists("stage-bg") && scene.textures.exists("cultivator") && scene.textures.exists("enemy");
  if (hasArt) drawArt(scene);
  else drawTechnicalStage(scene);
}

function drawArt(scene: Phaser.Scene): void {
  scene.add.image(450, 180, "stage-bg").setDisplaySize(900, 360);
  scene.add.image(190, 210, "cultivator").setDisplaySize(190, 280);
  scene.add.image(710, 190, "enemy").setDisplaySize(210, 300);
}

function drawTechnicalStage(scene: Phaser.Scene): void {
  const graphics = scene.add.graphics();
  graphics.fillStyle(0xf7f7f4, 1).fillRect(0, 0, 900, 360);
  graphics.lineStyle(2, 0x202424, 0.18).lineBetween(70, 290, 830, 290);
  graphics.lineStyle(1, 0x202424, 0.12);
  for (let x = 100; x < 900; x += 100) graphics.lineBetween(x, 292, x + 80, 340);
  graphics.fillStyle(0x18796f, 0.15).fillCircle(190, 210, 76);
  graphics.fillStyle(0xbf2c24, 0.15).fillCircle(710, 190, 86);
  graphics.lineStyle(3, 0xf0bc30, 0.65).lineBetween(285, 215, 610, 195);
}

function renderSnapshot(scene: Phaser.Scene, data: BattleData, emitEffects: boolean): void {
  data.dynamicLayer?.destroy(true);
  data.dynamicLayer = scene.add.container(0, 0);
  drawLabels(scene, data.dynamicLayer, data.snapshot);
  if (emitEffects) drawEffects(scene, data.dynamicLayer, data.snapshot);
}

function drawLabels(scene: Phaser.Scene, layer: Phaser.GameObjects.Container, snapshot: BattleSnapshot): void {
  const combat = snapshot.combat;
  const style = { color: "#202424", fontFamily: "serif", fontSize: "20px", fontStyle: "bold" };
  layer.add(scene.add.text(450, 30, `第 ${combat.turn} 回合 · 雷罚 ${combat.thunder_count}`, {
    ...style, fontSize: "16px", color: "#6d716d",
  }).setOrigin(0.5));
}

function drawEffects(scene: Phaser.Scene, layer: Phaser.GameObjects.Container, snapshot: BattleSnapshot): void {
  snapshot.events.slice(-3).forEach((event, index) => {
    const label = scene.add.text(450, 80 + index * 30, event.text, {
      color: event.kind.includes("damage") ? "#bf2c24" : "#18796f",
      fontFamily: "sans-serif", fontSize: "16px", backgroundColor: "#ffffffdd", padding: { x: 8, y: 4 },
    }).setOrigin(0.5);
    layer.add(label);
    if (!snapshot.reducedMotion) scene.tweens.add({ targets: label, y: label.y - 12, alpha: 0.35, duration: 1100, yoyo: true });
  });
}
