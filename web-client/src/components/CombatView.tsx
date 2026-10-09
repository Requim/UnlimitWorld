import { BatteryCharging, CloudLightning, Flame, Shield, Swords, Zap } from "lucide-react";
import { useMemo, useState } from "react";

import type { ActionInput, Catalog, GameEvent, RunView } from "../api/types";
import { findCard } from "../game/catalog";
import type { AssetState } from "../game/useAssets";
import { BattleStage } from "../scene/BattleStage";
import { CardTile } from "./CardTile";

interface CombatViewProps {
  run: RunView;
  catalog: Catalog;
  events: GameEvent[];
  assets: AssetState;
  busy: boolean;
  reducedMotion: boolean;
  onRetryAssets: () => void;
  onAction: (action: ActionInput) => void;
}

/** 渲染战场、权威意图与 DOM 手牌；出牌只提交实例 UID 和必要目标。 */
export function CombatView(props: CombatViewProps) {
  const combat = props.run.combat;
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const selected = combat?.hand.find((card) => card.uid === selectedUid) ?? null;
  const definition = selected ? findCard(props.catalog, selected.card_id) : null;
  if (!combat) return <MissingPhase phase="斗法" />;
  const cast = () => selected && props.onAction({ kind: "play_card", card_uid: selected.uid });
  const attack = () => selected && props.onAction({ kind: "play_card", card_uid: selected.uid, target_id: combat.enemy.id });
  return (
    <section className="combat-view" data-testid="phase-combat">
      <CombatStatus run={props.run} />
      <div className="battle-frame">
        <BattleStage assets={props.assets} combat={combat} events={props.events}
          reducedMotion={props.reducedMotion} onRetry={props.onRetryAssets} />
        <button className="enemy-target" data-testid="enemy-target" disabled={props.busy || definition?.target !== "enemy"}
          onClick={attack} title="对敌方打出所选卡牌">
          <EnemyIntent intent={combat.enemy.intent} />
          <strong>{combat.enemy.name}</strong>
          <span>生命 {combat.enemy.hp}/{combat.enemy.max_hp} · 护盾 {combat.enemy.block}</span>
          {(combat.enemy.burn > 0 || combat.enemy.weak > 0) && <small>燃烧 {combat.enemy.burn} · 虚弱 {combat.enemy.weak}</small>}
        </button>
      </div>
      <CommandBar run={props.run} busy={props.busy} onAction={props.onAction} />
      <div className="hand-zone" aria-label="手牌">
        {combat.hand.map((card) => <CardTile card={card} catalog={props.catalog} disabled={props.busy}
          key={card.uid} selected={card.uid === selectedUid} testId={`hand-card-${card.uid}`}
          onClick={() => setSelectedUid(card.uid === selectedUid ? null : card.uid)} />)}
      </div>
      <button className="cast-selected" data-testid="cast-selected" disabled={props.busy || !selected || definition?.target === "enemy"}
        onClick={cast}>{selected ? definition?.target === "enemy" ? "点敌人出牌" : `打出 ${definition?.name ?? "所选卡牌"}` : "先选择一张牌"}</button>
    </section>
  );
}

function CombatStatus({ run }: { run: RunView }) {
  const combat = run.combat!;
  return (
    <div className="combat-status">
      <span><BatteryCharging /> 灵力 <b>{combat.energy}/{combat.max_energy}</b></span>
      <span><Swords /> 剑意 <b>{combat.sword_intent}</b></span>
      <span><Shield /> 反伤 <b>{run.player.reflect}</b></span>
      <span className={combat.thunder_count > 0 ? "thunder-live" : ""}><CloudLightning /> 雷罚 <b>{combat.thunder_count} × {combat.thunder_damage}</b></span>
      <span>牌堆 {combat.draw_count} · 弃牌 {combat.discard_count} · 消耗 {combat.exhaust_count}</span>
    </div>
  );
}

function EnemyIntent({ intent }: { intent: NonNullable<RunView["combat"]>["enemy"]["intent"] }) {
  const total = intent.kind === "defend" ? intent.value : intent.value * intent.hits;
  return (
    <span className={`intent intent-${intent.kind}`}>
      {intent.kind === "defend" ? <Shield /> : intent.kind === "burn" ? <Flame /> : <Swords />}
      <b>{intent.text}</b><small>{intent.kind === "defend" ? `护盾 ${total}` : `${intent.hits} 段，共 ${total} 伤害`}</small>
      {intent.wrath_change !== 0 && <em><Zap size={13} /> 天谴 +{intent.wrath_change}</em>}
    </span>
  );
}

function CommandBar({ run, busy, onAction }: { run: RunView; busy: boolean; onAction: (action: ActionInput) => void }) {
  const preview = run.combat!.taunt_preview;
  return (
    <div className="command-bar">
      <button data-testid="taunt" disabled={busy || !preview.available} onClick={() => onAction({ kind: "taunt" })}>
        <Zap /> 挑衅 <span>{preview.text}</span>
      </button>
      <button className="end-turn" data-testid="end-turn" disabled={busy} onClick={() => onAction({ kind: "end_turn" })}>
        结束回合
      </button>
    </div>
  );
}

function MissingPhase({ phase }: { phase: string }) {
  return <section className="phase-error">服务端返回了 {phase} 阶段，但缺少对应局面数据。</section>;
}
