import * as Phaser from "phaser";

import type { AssetState } from "../game/useAssets";
import { battleBackgroundPath } from "./battleAssets";
import { BATTLE_LAYOUT } from "./battleLayout";
import type { BattleSceneAdapter, BattleSnapshot } from "./battleRuntime";

interface BattleData {
  snapshot: BattleSnapshot;
  assets: AssetState;
  onError: (message: string) => void;
  scene: Phaser.Scene | null;
  dynamicLayer: Phaser.GameObjects.Container | null;
}

/** 将只读快照与资源绘入 parent，返回更新/销毁适配器；加载错误调用 onError，destroy 释放画布。 */
export function createBattleGame(
  parent: HTMLElement,
  initial: BattleSnapshot,
  assets: AssetState,
  onError: (message: string) => void,
): BattleSceneAdapter {
  const data: BattleData = { snapshot: initial, assets, onError, scene: null, dynamicLayer: null };
  const game = new Phaser.Game({
    type: Phaser.AUTO, parent, width: BATTLE_LAYOUT.width, height: BATTLE_LAYOUT.height, transparent: true,
    render: { antialias: true },
    scale: { mode: Phaser.Scale.NONE, autoCenter: Phaser.Scale.NO_CENTER },
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
  const { width, height, cultivator, enemy } = BATTLE_LAYOUT;
  scene.add.image(width / 2, height / 2, "stage-bg").setDisplaySize(width, height);
  scene.add.image(cultivator.x, cultivator.y, "cultivator").setDisplaySize(cultivator.width, cultivator.height);
  scene.add.image(enemy.x, enemy.y, "enemy").setDisplaySize(enemy.width, enemy.height);
}

function drawTechnicalStage(scene: Phaser.Scene): void {
  const { width, height, cultivator, enemy } = BATTLE_LAYOUT;
  const graphics = scene.add.graphics();
  graphics.fillStyle(0xf7f7f4, 1).fillRect(0, 0, width, height);
  graphics.lineStyle(2, 0x202424, 0.18).lineBetween(70, 290, 830, 290);
  graphics.lineStyle(1, 0x202424, 0.12);
  for (let x = 100; x < 900; x += 100) graphics.lineBetween(x, 292, x + 80, 340);
  graphics.fillStyle(0x18796f, 0.15).fillCircle(cultivator.x, cultivator.y, cultivator.radius);
  graphics.fillStyle(0xbf2c24, 0.15).fillCircle(enemy.x, enemy.y, enemy.radius);
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
