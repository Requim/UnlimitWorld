import { BatteryCharging, CloudLightning, Flame, Shield, Swords, Zap } from "lucide-react";
import { useState } from "react";

import type { ActionInput, Catalog, GameEvent, RunView } from "../api/types";
import { cardCost, cardDescription, findCard } from "../game/catalog";
import type { AssetState } from "../game/useAssets";
import { BattleStage } from "../scene/BattleStage";
import { ENEMY_TARGET_STYLE } from "../scene/battleLayout";
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

/** 输入权威局面与交互状态，返回战场/手牌；出牌通过 onAction 提交实例 UID/目标，不计算规则。 */
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
        <BattleStage assets={props.assets} combat={combat} events={props.events} revision={props.run.revision}
          reducedMotion={props.reducedMotion} onRetry={props.onRetryAssets} info={<EnemyInfo enemy={combat.enemy} />}>
          <button className="enemy-target" data-testid="enemy-target" style={ENEMY_TARGET_STYLE}
            disabled={props.busy || definition?.target !== "enemy"} onClick={attack}
            aria-label={`对${combat.enemy.name}打出所选卡牌`} title="对敌方打出所选卡牌" />
        </BattleStage>
      </div>
      <CommandBar run={props.run} busy={props.busy} onAction={props.onAction} />
      <SelectedCardDetail card={selected} definition={definition} />
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

function EnemyInfo({ enemy }: { enemy: NonNullable<RunView["combat"]>["enemy"] }) {
  return (
    <div className="enemy-info">
      <EnemyIntent intent={enemy.intent} />
      <strong>{enemy.name}</strong>
      <span>生命 {enemy.hp}/{enemy.max_hp} · 护盾 {enemy.block}</span>
      {(enemy.burn > 0 || enemy.weak > 0) && <small>燃烧 {enemy.burn} · 虚弱 {enemy.weak}</small>}
    </div>
  );
}

function SelectedCardDetail({ card, definition }: {
  card: NonNullable<RunView["combat"]>["hand"][number] | null;
  definition: ReturnType<typeof findCard> | null;
}) {
  if (!card || !definition) return <div className="selected-card-detail empty" aria-hidden="true" />;
  return (
    <aside className="selected-card-detail" data-testid="selected-card-detail">
      <strong>{definition.name}{card.upgraded ? "+" : ""}</strong>
      <span data-testid="selected-card-rule">{cardDescription(card, definition)}</span>
      <small>{cardCost(card, definition)} 灵力 · {definition.target === "enemy" ? "敌方目标" : "立即生效"}</small>
    </aside>
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
      <button className="taunt" data-testid="taunt" disabled={busy || !preview.available}
        onClick={() => onAction({ kind: "taunt" })} title={preview.text}>
        <Zap /><span className="command-label">挑衅</span>
        <span className="taunt-summary" data-testid="taunt-summary">{tauntSummary(preview)}</span>
      </button>
      <button className="end-turn" data-testid="end-turn" disabled={busy} onClick={() => onAction({ kind: "end_turn" })}>
        结束回合
      </button>
    </div>
  );
}

function tauntSummary(preview: NonNullable<RunView["combat"]>["taunt_preview"]): string {
  return `灵力${signed(preview.energy_gain)} · 天谴${signed(preview.wrath_change)} · 敌攻${signed(preview.next_attack_bonus)}/段`;
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

function MissingPhase({ phase }: { phase: string }) {
  return <section className="phase-error">服务端返回了 {phase} 阶段，但缺少对应局面数据。</section>;
}
