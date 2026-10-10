import { BatteryCharging, CloudLightning, Flame, Hourglass, Shield, Swords, Zap } from "lucide-react";
import { useEffect, useState } from "react";

import type { ActionInput, Catalog, RunView } from "../api/types";
import { cardCost, cardDescription, findCard } from "../game/catalog";
import { missingClipKeys } from "./mythAnimation";
import type { MythAssets } from "./mythAssets";
import { MythStage } from "./MythStage";
import type { PresentationAdapter } from "./presentationQueue";

interface Props {
  run: RunView; catalog: Catalog; assets: MythAssets; busy: boolean; reducedMotion: boolean;
  onAction: (action: ActionInput) => Promise<void>; onAdapter: (adapter: PresentationAdapter | null) => void;
  onRetryAssets: () => void;
}

/** 渲染样板战斗并提交卡牌 UID/目标；数值、预告和手牌均来自展示快照或权威局面。 */
export function MythBattle(props: Props) {
  const combat = props.run.combat;
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const selected = combat?.hand.find((card) => card.uid === selectedUid) ?? null;
  const definition = selected ? findCard(props.catalog, selected.card_id) : null;
  useEffect(() => { if (selectedUid && !selected) setSelectedUid(null); }, [selected, selectedUid]);
  if (!combat) return <section className="myth-system">服务端缺少战斗快照。</section>;
  const play = () => selected && props.onAction({ kind: "play_card", card_uid: selected.uid });
  const target = () => selected && props.onAction({ kind: "play_card", card_uid: selected.uid, target_id: combat.enemy.id });
  return <section className="myth-battle" data-testid="phase-combat">
    <BattleStrip run={props.run} />
    <div className="myth-stage-wrap"><EnemyPanel run={props.run} />
      <MythStage assets={props.assets} enabled={!props.busy && definition?.target === "enemy"}
        onTarget={() => void target()} onRetry={props.onRetryAssets} onAdapter={props.onAdapter}
        reducedMotion={props.reducedMotion} />
      <AnimationStatus assets={props.assets} />
    </div>
    <BattleCommands run={props.run} busy={props.busy} onAction={props.onAction} />
    <div className="myth-hand" aria-label="手牌">{combat.hand.map((card) => <MythCard key={card.uid}
      card={card} catalog={props.catalog} selected={card.uid === selectedUid} disabled={props.busy}
      onSelect={() => setSelectedUid(card.uid === selectedUid ? null : card.uid)} />)}</div>
    <button className="myth-cast" data-testid="cast-selected" disabled={props.busy || !selected || definition?.target === "enemy"}
      onClick={() => void play()}>{selected ? definition?.target === "enemy" ? "点毕方出牌" : `打出 ${definition?.name}` : "先选一张牌"}</button>
  </section>;
}

function BattleStrip({ run }: { run: RunView }) {
  const combat = run.combat!;
  return <div className="myth-combat-strip"><span><BatteryCharging /> 灵力 <b>{combat.energy}/{combat.max_energy}</b></span>
    <span><Swords /> 剑意 <b>{combat.sword_intent}</b></span><span><Shield /> 反伤 <b>{run.player.reflect}</b></span>
    <span><CloudLightning /> 雷罚 <b>{combat.thunder_count} × {combat.thunder_damage}</b></span>
    <span>牌堆 {combat.draw_count} · 弃牌 {combat.discard_count} · 消耗 {combat.exhaust_count}</span></div>;
}

function EnemyPanel({ run }: { run: RunView }) {
  const enemy = run.combat!.enemy;
  const intent = enemy.intent;
  const total = intent.kind === "defend" ? intent.value : intent.value * intent.hits;
  return <aside className="myth-enemy-panel"><span>毕方预告</span><b>{intent.text}</b>
    <small>{intent.kind === "defend" ? `护盾 ${total}` : `${intent.hits} 段 · 共 ${total} 伤害`}
      {intent.wrath_change ? ` · 天谴 +${intent.wrath_change}` : ""}</small>
    <i><u style={{ width: `${Math.max(0, enemy.hp / enemy.max_hp * 100)}%` }} /></i>
    <em>生命 {enemy.hp}/{enemy.max_hp} · 护盾 {enemy.block} · 燃烧 {enemy.burn}</em></aside>;
}

function BattleCommands({ run, busy, onAction }: { run: RunView; busy: boolean; onAction: Props["onAction"] }) {
  const preview = run.combat!.taunt_preview;
  return <div className="myth-commands"><button data-testid="taunt" disabled={busy || !preview.available}
    onClick={() => void onAction({ kind: "taunt" })}><Zap /><span><b>挑衅天道</b><small>{preview.text}</small></span></button>
    <button data-testid="end-turn" disabled={busy} onClick={() => void onAction({ kind: "end_turn" })}>
      <Hourglass /> 结束回合</button></div>;
}

function MythCard({ card, catalog, selected, disabled, onSelect }: {
  card: RunView["deck"][number]; catalog: Catalog; selected: boolean; disabled: boolean; onSelect: () => void;
}) {
  const definition = findCard(catalog, card.card_id);
  if (!definition) return <span className="myth-card missing">未知卡牌</span>;
  return <button className={`myth-card ${definition.archetype}${selected ? " selected" : ""}`}
    data-card-id={card.card_id} data-testid={`hand-card-${card.uid}`} disabled={disabled} onClick={onSelect}>
    <span>{cardCost(card, definition)}</span><small>{definition.archetype}</small>
    <i aria-hidden="true">{definition.target === "enemy" ? <Swords /> : definition.archetype === "fire" ? <Flame /> : <Shield />}</i>
    <b>{definition.name}{card.upgraded ? "+" : ""}</b><em>{cardDescription(card, definition)}</em></button>;
}

function AnimationStatus({ assets }: { assets: MythAssets }) {
  if (assets.status !== "ready" || !assets.manifest) return null;
  const missing = missingClipKeys(assets.manifest.animations);
  if (missing.length === 0) return <span className="myth-animation-status ready">动作案卷齐备</span>;
  return <span className="myth-animation-status"><AlertIcon />动作案卷缺页 {missing.length}/10</span>;
}

function AlertIcon() { return <Zap aria-hidden="true" />; }
