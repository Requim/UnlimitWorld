import { CircleDollarSign, Flame, MoonStar, Skull, Sparkles, Swords } from "lucide-react";

import type { ActionInput, RunView } from "../api/types";

interface MapViewProps {
  run: RunView;
  busy: boolean;
  onAction: (action: ActionInput) => void;
}

/** 渲染九层相邻路线；仅 available 节点可提交 choose_node。 */
export function MapView({ run, busy, onAction }: MapViewProps) {
  const layers = Array.from({ length: 9 }, (_, index) => 9 - index);
  return (
    <section className="map-view" data-testid="phase-map">
      <header className="phase-heading"><span>九层命途</span><p>抬头看路，低头看牌。终点只有监天判官。</p></header>
      <div className="route-map">
        {layers.map((layer) => (
          <div className="route-layer" key={layer}>
            <span className="layer-index">{layer}</span>
            <div className="route-nodes">
              {run.map.nodes.filter((node) => node.layer === layer).map((node) => (
                <button className={nodeClass(node)} data-testid={`map-node-${node.id}`}
                  disabled={busy || !node.available} key={node.id}
                  onClick={() => onAction({ kind: "choose_node", node_id: node.id })}
                  title={`${node.id} · ${nodeName(node.kind)}`}>
                  {nodeIcon(node.kind)}<span>{nodeName(node.kind)}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

type MapNode = RunView["map"]["nodes"][number];

function nodeClass(node: MapNode): string {
  return `route-node kind-${node.kind}${node.available ? " available" : ""}${node.completed ? " completed" : ""}`;
}

function nodeName(kind: string): string {
  return { combat: "斗法", elite: "强敌", event: "奇遇", shop: "黑市", rest: "休整", boss: "判官" }[kind] ?? kind;
}

function nodeIcon(kind: string) {
  const icons = { combat: Swords, elite: Flame, event: Sparkles, shop: CircleDollarSign, rest: MoonStar, boss: Skull };
  const Icon = icons[kind as keyof typeof icons] ?? Swords;
  return <Icon aria-hidden="true" />;
}
