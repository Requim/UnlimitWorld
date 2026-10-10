/** 角色原画布与可见 alpha 边界；缺边界时按完整画布计算，不修改纹理。 */
export interface ActorMetrics { size: readonly number[]; bounds?: readonly number[] }
/** Phaser 角色框；origin 指向种子可见边界的脚底中心。 */
export interface ActorLayout {
  x: number; y: number; width: number; height: number;
  originX: number; originY: number;
}
/** 战场共享几何；target 与 bifang 使用同一坐标系，可直接交给 DOM 点击层。 */
export interface MythLayout {
  hero: ActorLayout; bifang: ActorLayout;
  target: { left: number; top: number; width: number; height: number };
}
const FULL: ActorMetrics = { size: [2352, 3520] };

/** 按区域与原图边界返回共享渲染/目标几何；角色脚底共线，不保存游戏状态。 */
export function mythLayout(width: number, height: number, heroMetrics = FULL, bifangMetrics = FULL): MythLayout {
  const portrait = width < height * 1.1;
  const baseline = height * .94;
  const heroHeight = Math.min(height * .68, width * (portrait ? .59 : .35));
  const bifangHeight = Math.min(height * .88, width * (portrait ? .85 : .5));
  const heroX = width * .23;
  const bifangX = width * .73;
  const hero = placeActor(heroX, baseline, heroHeight, horizontalRoom(width, heroX), heroMetrics);
  const bifang = placeActor(bifangX, baseline, bifangHeight, horizontalRoom(width, bifangX), bifangMetrics);
  return { hero, bifang, target: visibleBounds(bifang, bifangMetrics) };
}

function placeActor(x: number, y: number, visibleHeight: number, maxWidth: number, metrics: ActorMetrics): ActorLayout {
  const [width, fullHeight] = metrics.size;
  const bounds = metrics.bounds ?? [0, 0, width, fullHeight];
  const scale = Math.min(visibleHeight / (bounds[3] - bounds[1]), maxWidth / width, y / fullHeight);
  return { x, y, width: width * scale, height: fullHeight * scale,
    originX: (bounds[0] + bounds[2]) / (2 * width), originY: bounds[3] / fullHeight };
}

function horizontalRoom(width: number, x: number): number {
  return Math.max(1, Math.min(x, width - x) * 2);
}

function visibleBounds(actor: ActorLayout, metrics: ActorMetrics) {
  const [width, height] = metrics.size;
  const bounds = metrics.bounds ?? [0, 0, width, height];
  return { left: actor.x - (bounds[2] - bounds[0]) * actor.width / width / 2,
    top: actor.y - (bounds[3] - bounds[1]) * actor.height / height,
    width: (bounds[2] - bounds[0]) * actor.width / width,
    height: (bounds[3] - bounds[1]) * actor.height / height };
}
