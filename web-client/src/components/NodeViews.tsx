import { ArrowRight, HeartPulse, LogOut, Sparkles } from "lucide-react";

import type { ActionInput, Catalog, RunView } from "../api/types";
import { findCard } from "../game/catalog";
import { CardTile } from "./CardTile";

interface NodeViewProps { run: RunView; catalog: Catalog; busy: boolean; onAction: (action: ActionInput) => void }

/** 渲染三选一战利品；跳过与选择均提交权威动作。 */
export function RewardView({ run, catalog, busy, onAction }: NodeViewProps) {
  if (!run.reward) return <PhaseError name="奖励" />;
  return (
    <section className="choice-view" data-testid="phase-reward">
      <PhaseTitle title="择取机缘" copy={`此战已获 ${run.reward.stones} 灵石，再选一张牌。`} />
      <div className="choice-cards">
        {run.reward.cards.map((reward, index) => {
          const card = { uid: `reward-${index}`, card_id: reward.card_id, upgraded: reward.upgraded };
          return <CardTile card={card} catalog={catalog} disabled={busy} key={card.uid}
            testId={`reward-${index}`} onClick={() => onAction({ kind: "choose_reward", option_index: index })} />;
        })}
      </div>
      <button className="text-command" data-testid="skip-reward" disabled={busy} onClick={() => onAction({ kind: "skip_reward" })}>空手离开 <ArrowRight /></button>
    </section>
  );
}

/** 渲染服务端奇遇文本与实际资源说明。 */
export function EventView({ run, busy, onAction }: NodeViewProps) {
  return (
    <section className="choice-view event-view" data-testid="phase-event">
      <PhaseTitle title="因果拦路" copy="有些便宜是机缘，有些机缘只是写得像便宜。" />
      <div className="event-choices">{run.choices.map((choice) => (
        <button data-testid={`event-${choice.id}`} disabled={busy} key={choice.id}
          onClick={() => onAction({ kind: "choose_event", choice_id: choice.id })}>
          <Sparkles /><strong>{choice.label}</strong><span>{choice.description}</span>
        </button>
      ))}</div>
    </section>
  );
}

/** 渲染黑市商品、移牌服务与离开命令。 */
export function ShopView({ run, catalog, busy, onAction }: NodeViewProps) {
  if (!run.shop) return <PhaseError name="黑市" />;
  return (
    <section className="shop-view" data-testid="phase-shop">
      <PhaseTitle title="天缝黑市" copy="一手交灵石，一手交来路不明的机缘。" />
      <div className="shop-items">{run.shop.items.map((item) => (
        <button data-testid={`shop-buy-${item.id}`} disabled={busy || item.purchased || run.player.stones < item.price}
          key={item.id} onClick={() => onAction({ kind: "buy", item_id: item.id })}>
          <small>{item.kind === "card" ? "卡牌" : "法宝"}</small>
          <strong>{itemName(catalog, item.kind, item.ref_id)}</strong>
          <span>{itemDescription(catalog, item.kind, item.ref_id)}</span><b>{item.purchased ? "已售" : `${item.price} 灵石`}</b>
        </button>
      ))}</div>
      <RemoveCards run={run} catalog={catalog} busy={busy} onAction={onAction} />
      <button className="leave-command" data-testid="leave-shop" disabled={busy} onClick={() => onAction({ kind: "leave_shop" })}><LogOut /> 离开黑市</button>
    </section>
  );
}

function RemoveCards({ run, catalog, busy, onAction }: NodeViewProps) {
  const shop = run.shop!;
  return (
    <div className="remove-service"><h3>断舍离 · {shop.removal_price} 灵石</h3>
      <div>{run.deck.map((card) => <button data-testid={`remove-${card.uid}`} disabled={busy || shop.removal_used || run.player.stones < shop.removal_price}
        key={card.uid} onClick={() => onAction({ kind: "remove_card", card_uid: card.uid })}>
        {findCard(catalog, card.card_id)?.name ?? card.card_id}{card.upgraded ? "+" : ""}
      </button>)}</div>
    </div>
  );
}

/** 渲染治疗与升级分支；数值说明与里程碑规则一致。 */
export function RestView({ busy, onAction }: NodeViewProps) {
  return (
    <section className="choice-view rest-view" data-testid="phase-rest">
      <PhaseTitle title="借地歇脚" copy="只够做一件事：把命续上，或把牌磨利。" />
      <div className="event-choices">
        <button data-testid="rest-heal" disabled={busy} onClick={() => onAction({ kind: "rest", mode: "heal" })}><HeartPulse /><strong>调息</strong><span>恢复最大生命的 30%</span></button>
        <button data-testid="rest-upgrade" disabled={busy} onClick={() => onAction({ kind: "rest", mode: "upgrade" })}><Sparkles /><strong>点化</strong><span>选择一张未升级卡牌</span></button>
      </div>
    </section>
  );
}

/** 渲染可升级牌组；已升级卡牌不可重复提交。 */
export function UpgradeView({ run, catalog, busy, onAction }: NodeViewProps) {
  return <section className="choice-view" data-testid="phase-rest_upgrade"><PhaseTitle title="点化卡牌" copy="一张牌，一次改命。" />
    <div className="choice-cards">{run.deck.map((card) => <CardTile card={card} catalog={catalog} disabled={busy || card.upgraded}
      key={card.uid} testId={`upgrade-${card.uid}`} onClick={() => onAction({ kind: "upgrade_card", card_uid: card.uid })} />)}</div>
  </section>;
}

function PhaseTitle({ title, copy }: { title: string; copy: string }) {
  return <header className="phase-heading"><span>{title}</span><p>{copy}</p></header>;
}

function PhaseError({ name }: { name: string }) { return <section className="phase-error">{name}数据缺失，请刷新权威局面。</section>; }

function itemName(catalog: Catalog, kind: string, id: string): string {
  return kind === "card" ? findCard(catalog, id)?.name ?? id : catalog.relics.find((item) => item.id === id)?.name ?? id;
}

function itemDescription(catalog: Catalog, kind: string, id: string): string {
  return kind === "card" ? findCard(catalog, id)?.description ?? "" : catalog.relics.find((item) => item.id === id)?.description ?? "";
}
