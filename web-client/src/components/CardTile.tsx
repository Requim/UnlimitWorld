import { useEffect, useState } from "react";

import type { Catalog, RunView } from "../api/types";
import { useAssetState } from "../game/AssetContext";
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
  const assets = useAssetState();
  const artwork = assets.status === "ready" ? assets.manifest?.cards[props.card.card_id] : undefined;
  const [imageFailed, setImageFailed] = useState(false);
  useEffect(() => setImageFailed(false), [artwork, assets.manifest]);
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
      {artwork && !imageFailed && <img className="card-art" data-testid={`card-art-${props.card.card_id}`}
        src={artwork} alt={`${definition.name}卡面`} onError={() => setImageFailed(true)} />}
      {artwork && imageFailed && <span className="card-art-error">卡面加载失败</span>}
      <strong>{definition.name}{props.card.upgraded ? "+" : ""}</strong>
      <span className="card-rule">{cardDescription(props.card, definition)}</span>
      <small>{definition.target === "enemy" ? "敌方目标" : "立即生效"}</small>
    </button>
  );
}

function schoolName(school: string): string {
  return { common: "通用", sword: "御剑", fire: "业火", talisman: "符箓" }[school] ?? school;
}
