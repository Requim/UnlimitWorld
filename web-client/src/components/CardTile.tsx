import type { Catalog, RunView } from "../api/types";
import { cardCost, cardDescription, findCard } from "../game/catalog";

type CardInstance = RunView["deck"][number];

interface CardTileProps {
  card: CardInstance;
  catalog: Catalog;
  selected?: boolean;
  disabled?: boolean;
  testId?: string;
  onClick?: () => void;
}

/** 渲染稳定尺寸 DOM 卡牌；目录缺失时明确显示错误而非虚构说明。 */
export function CardTile(props: CardTileProps) {
  const definition = findCard(props.catalog, props.card.card_id);
  if (!definition) return <div className="card-tile card-missing">未知卡牌：{props.card.card_id}</div>;
  return (
    <button
      className={`card-tile school-${definition.archetype}${props.selected ? " selected" : ""}`}
      data-card-id={props.card.card_id}
      data-card-uid={props.card.uid}
      data-testid={props.testId}
      disabled={props.disabled}
      onClick={props.onClick}
      type="button"
    >
      <span className="card-cost">{cardCost(props.card, definition)}</span>
      <span className="card-school">{schoolName(definition.archetype)}</span>
      <strong>{definition.name}{props.card.upgraded ? "+" : ""}</strong>
      <span className="card-rule">{cardDescription(props.card, definition)}</span>
      <small>{definition.target === "enemy" ? "敌方目标" : "立即生效"}</small>
    </button>
  );
}

function schoolName(school: string): string {
  return { common: "通用", sword: "御剑", fire: "业火", talisman: "符箓" }[school] ?? school;
}
