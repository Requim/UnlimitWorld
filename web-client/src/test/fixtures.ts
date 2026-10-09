import type { Catalog, RunView } from "../api/types";

/** 创建类型完整的测试目录；可覆盖局部数组且无副作用。 */
export function makeCatalog(overrides: Partial<Catalog> = {}): Catalog {
  return {
    cards: [
      { id: "flying_sword", name: "飞剑", archetype: "common", cost: 1, upgraded_cost: 1, target: "enemy", description: "造成 6 点伤害。", upgrade_text: "伤害提高至 9。", exhaust: false },
      { id: "guard", name: "护体", archetype: "common", cost: 1, upgraded_cost: 1, target: "self", description: "获得 6 点护盾。", upgrade_text: "护盾提高至 9。", exhaust: false },
    ],
    relics: [],
    enemies: [{ id: "paper_soldier", name: "纸兵", rank: "normal", max_hp: 20, intent_pattern: [["attack", 4]], description: "测试敌人" }],
    archetypes: [{ id: "sword", name: "御剑", description: "积攒剑意", starter_card_id: "flying_sword" }],
    ...overrides,
  };
}

/** 创建类型完整的公共局面；输入只覆盖顶层字段。 */
export function makeRun(overrides: Partial<RunView> = {}): RunView {
  return {
    run_id: "run-1", revision: 1, archetype: "sword", phase: "map", layer: 1,
    player: { hp: 60, max_hp: 60, block: 0, wrath: 0, stones: 60, reflect: 0 },
    deck: makeCards(10), relics: [], map: { current_node_id: null, nodes: [
      { id: "L1N0", layer: 1, lane: 0, kind: "combat", links_from: [], available: true, completed: false },
    ] },
    combat: null, reward: null, choices: [], shop: null, history: [], epitaph: null,
    ...overrides,
  };
}

/** 创建指定数量的卡牌实例，UID 稳定便于 selector 断言。 */
export function makeCards(count: number, cardId = "flying_sword"): RunView["deck"] {
  return Array.from({ length: count }, (_, index) => ({ uid: `card-${index}`, card_id: cardId, upgraded: false }));
}

/** 创建同一敌人的战斗视图；输入 revision 相关状态由测试局面持有。 */
export function makeCombat(hand = makeCards(12)): NonNullable<RunView["combat"]> {
  return {
    turn: 1, energy: 3, max_energy: 3, hand, draw_count: 5, discard_count: 0, exhaust_count: 0,
    enemy: { id: "paper_soldier", name: "纸兵", hp: 20, max_hp: 20, block: 0, burn: 0, weak: 0,
      intent_index: 0, intent: { kind: "attack", value: 4, hits: 1, wrath_change: 0, text: "攻击 4" } },
    taunt_used: false,
    taunt_preview: { available: true, energy_gain: 1, wrath_change: 8, next_attack_bonus: 2, text: "获得 1 灵力，天谴 +8；敌人下次攻击每段 +2。" },
    sword_intent: 0, lightning_redirect: false, thunder_count: 0, thunder_damage: 8,
  };
}
