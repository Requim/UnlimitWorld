import type { Catalog, RunView } from "../api/types";

/** OpenAPI 目录中的单张卡牌定义。 */
export type CardDefinition = Catalog["cards"][number];
/** 权威局面中的单张卡牌实例。 */
export type CardInstance = RunView["deck"][number];

/** 按 ID 查找卡牌定义；目录不完整时返回 undefined，不制造假数据。 */
export function findCard(catalog: Catalog, cardId: string): CardDefinition | undefined {
  return catalog.cards.find((card) => card.id === cardId);
}

/** 返回实例当前费用；升级牌使用服务端目录中的 upgraded_cost。 */
export function cardCost(card: CardInstance, definition: CardDefinition): number {
  return card.upgraded ? definition.upgraded_cost : definition.cost;
}

/** 返回卡牌当前说明；升级文本是差异说明，需和基础说明同时展示。 */
export function cardDescription(card: CardInstance, definition: CardDefinition): string {
  return card.upgraded
    ? `${definition.description} 升级：${definition.upgrade_text}`
    : definition.description;
}
