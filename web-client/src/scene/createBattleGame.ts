import * as Phaser from "phaser";

import type { GameEvent, RunView } from "../api/types";
import type { AssetState } from "../game/useAssets";

type Combat = NonNullable<RunView["combat"]>;

interface BattleData {
  combat: Combat;
  assets: AssetState;
  events: GameEvent[];
  reducedMotion: boolean;
  onError: (message: string) => void;
}

/** 创建可销毁 Phaser 实例；输入只读局面，输出不参与规则计算。 */
export function createBattleGame(
  parent: HTMLElement,
  combat: Combat,
  assets: AssetState,
  events: GameEvent[],
  reducedMotion: boolean,
  onError: (message: string) => void,
): Phaser.Game {
  const scene = createBattleScene({ combat, assets, events, reducedMotion, onError });
  return new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    width: 900,
    height: 360,
    transparent: true,
    render: { antialias: true },
    scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
    scene,
  });
}

function createBattleScene(data: BattleData): Phaser.Types.Scenes.SettingsConfig & Phaser.Types.Scenes.CreateSceneFromObjectConfig {
  return {
    key: "BattleScene",
    preload(this: Phaser.Scene) { preloadAssets(this, data); },
    create(this: Phaser.Scene) { drawBattle(this, data); },
  };
}

function preloadAssets(scene: Phaser.Scene, data: BattleData): void {
  if (data.assets.status !== "ready" || !data.assets.manifest) return;
  const manifest = data.assets.manifest;
  scene.load.image("battle-bg", manifest.backgrounds.battle);
  scene.load.image("cultivator", manifest.characters.cultivator);
  const enemyPath = manifest.enemies[data.combat.enemy.id];
  if (enemyPath) scene.load.image("enemy", enemyPath);
  scene.load.on("loaderror", () => data.onError("位图加载失败，请检查资源清单后重试"));
}

function drawBattle(scene: Phaser.Scene, data: BattleData): void {
  const hasArt = scene.textures.exists("battle-bg") && scene.textures.exists("cultivator") && scene.textures.exists("enemy");
  if (hasArt) drawArt(scene);
  else drawTechnicalStage(scene);
  drawLabels(scene, data.combat);
  drawEffects(scene, data.events, data.reducedMotion);
}

function drawArt(scene: Phaser.Scene): void {
  scene.add.image(450, 180, "battle-bg").setDisplaySize(900, 360);
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

function drawLabels(scene: Phaser.Scene, combat: Combat): void {
  const style = { color: "#202424", fontFamily: "serif", fontSize: "20px", fontStyle: "bold" };
  scene.add.text(190, 205, "修行者", style).setOrigin(0.5);
  scene.add.text(710, 185, combat.enemy.name, style).setOrigin(0.5);
  scene.add.text(450, 30, `第 ${combat.turn} 回合`, { ...style, fontSize: "16px", color: "#6d716d" }).setOrigin(0.5);
}

function drawEffects(scene: Phaser.Scene, events: GameEvent[], reducedMotion: boolean): void {
  const recent = events.slice(-3);
  recent.forEach((event, index) => {
    const label = scene.add.text(450, 80 + index * 30, event.text, {
      color: event.kind.includes("damage") ? "#bf2c24" : "#18796f",
      fontFamily: "sans-serif", fontSize: "16px", backgroundColor: "#ffffffdd", padding: { x: 8, y: 4 },
    }).setOrigin(0.5);
    if (!reducedMotion) scene.tweens.add({ targets: label, y: label.y - 12, alpha: 0.35, duration: 1100, yoyo: true });
  });
}
