"""战后奖励、奇遇、黑市与休整节点规则。"""

from __future__ import annotations

from uuid import uuid4

from .catalog import CARDS, RELICS
from .errors import InvalidAction
from .map import complete_current_node
from .models import (
    CardInstance,
    EventChoice,
    GameEvent,
    RewardCard,
    RewardState,
    RunState,
    ShopItem,
    ShopState,
)
from .random_source import randbelow, sample_unique


def generate_reward(run: RunState, source: str) -> RewardState:
    """生成并持久化三选一卡牌奖励；重复调用返回原奖励且不重复发灵石。"""
    if run.reward is not None:
        return run.reward
    candidates = [card for card in CARDS if card.archetype in {"common", run.archetype}]
    cards = [RewardCard(card_id=card.id) for card in sample_unique(run, candidates, 3)]
    stones = 35 if source == "elite" else 20
    run.player.stones += stones
    run.reward = RewardState(cards=cards, stones=stones, source=source)
    run.phase = "reward"
    return run.reward


def choose_reward(run: RunState, option_index: int) -> list[GameEvent]:
    """领取指定卡牌并结束节点；索引或阶段非法时抛 InvalidAction。"""
    reward = _require_reward(run)
    if option_index >= len(reward.cards):
        raise InvalidAction("奖励选项不存在")
    selected = reward.cards[option_index]
    run.deck.append(CardInstance(uid=uuid4().hex, card_id=selected.card_id, upgraded=selected.upgraded))
    run.reward = None
    run.combat = None
    complete_current_node(run)
    return [GameEvent(kind="reward", text="获得一张新卡", target=selected.card_id)]


def skip_reward(run: RunState) -> list[GameEvent]:
    """跳过战后卡牌奖励并结束节点；非奖励阶段抛 InvalidAction。"""
    _require_reward(run)
    run.reward = None
    run.combat = None
    complete_current_node(run)
    return [GameEvent(kind="reward_skipped", text="跳过卡牌奖励")]


def _require_reward(run: RunState) -> RewardState:
    if run.phase != "reward" or run.reward is None:
        raise InvalidAction("当前没有可领取奖励")
    return run.reward


def open_shop(run: RunState) -> ShopState:
    """生成三张卡、一件未持有法宝和移除服务；会消费服务端随机流并进入商店阶段。"""
    cards = sample_unique(run, CARDS, 3)
    relic_pool = [relic for relic in RELICS if relic.id not in run.relics] or RELICS
    relic = relic_pool[randbelow(run, len(relic_pool))]
    items = [ShopItem(id=f"card-{index}", kind="card", ref_id=card.id, price=30) for index, card in enumerate(cards)]
    items.append(ShopItem(id="relic-0", kind="relic", ref_id=relic.id, price=55))
    run.shop = ShopState(items=items)
    run.phase = "shop"
    return run.shop


def buy_item(run: RunState, item_id: str) -> list[GameEvent]:
    """购买商店卡牌或法宝；会扣灵石，余额不足、重复购买或商品无效时抛 InvalidAction。"""
    shop = _require_shop(run)
    item = _find_shop_item(shop, item_id)
    if item.purchased:
        raise InvalidAction("商品已经售出")
    if run.player.stones < item.price:
        raise InvalidAction("灵石不足")
    if item.kind == "relic" and item.ref_id in run.relics:
        raise InvalidAction("不能重复持有同一法宝")
    run.player.stones -= item.price
    item.purchased = True
    if item.kind == "card":
        run.deck.append(CardInstance(uid=uuid4().hex, card_id=item.ref_id))
    else:
        run.relics.append(item.ref_id)
    return [GameEvent(kind="purchase", text="购买成功", amount=-item.price, target=item.ref_id)]


def _find_shop_item(shop: ShopState, item_id: str) -> ShopItem:
    try:
        return next(item for item in shop.items if item.id == item_id)
    except StopIteration as exc:
        raise InvalidAction("商品不存在") from exc


def remove_card(run: RunState, card_uid: str) -> list[GameEvent]:
    """支付 45 灵石移除一张牌；牌组少于六张、余额不足或已使用服务时拒绝。"""
    shop = _require_shop(run)
    if shop.removal_used:
        raise InvalidAction("本次黑市已经移除过卡牌")
    if len(run.deck) <= 5:
        raise InvalidAction("牌组至少保留五张")
    if run.player.stones < shop.removal_price:
        raise InvalidAction("灵石不足")
    card = _find_deck_card(run, card_uid)
    run.player.stones -= shop.removal_price
    shop.removal_used = True
    run.deck.remove(card)
    return [GameEvent(kind="remove_card", text="移除一张卡牌", amount=-shop.removal_price, target=card.card_id)]


def leave_shop(run: RunState) -> list[GameEvent]:
    """离开黑市并完成节点；非商店阶段抛 InvalidAction。"""
    _require_shop(run)
    run.shop = None
    complete_current_node(run)
    return [GameEvent(kind="leave_shop", text="离开黑市")]


def _require_shop(run: RunState) -> ShopState:
    if run.phase != "shop" or run.shop is None:
        raise InvalidAction("当前不在黑市")
    return run.shop


def finish_rest(run: RunState, mode: str) -> list[GameEvent]:
    """休整时选择治疗或进入升级选择；会修改生命/阶段，模式非法时抛 InvalidAction。"""
    if run.phase != "rest":
        raise InvalidAction("当前不在休整点")
    if mode == "upgrade":
        run.phase = "rest_upgrade"
        return [GameEvent(kind="rest_upgrade", text="选择一张卡牌升级")]
    if mode != "heal":
        raise InvalidAction("休整方式无效")
    amount = (run.player.max_hp * 30 + 99) // 100
    healed = min(amount, run.player.max_hp - run.player.hp)
    run.player.hp += healed
    complete_current_node(run)
    return [GameEvent(kind="heal", text=f"恢复 {healed} 点生命", amount=healed, target="player")]


def upgrade_card(run: RunState, card_uid: str) -> list[GameEvent]:
    """将指定卡牌升级一次；卡牌不存在或已升级时抛 InvalidAction。"""
    card = _find_deck_card(run, card_uid)
    if card.upgraded:
        raise InvalidAction("卡牌最多升级一次")
    card.upgraded = True
    if run.phase == "rest_upgrade":
        complete_current_node(run)
    return [GameEvent(kind="upgrade_card", text="卡牌升级完成", target=card.card_id)]


def _find_deck_card(run: RunState, card_uid: str) -> CardInstance:
    try:
        return next(card for card in run.deck if card.uid == card_uid)
    except StopIteration as exc:
        raise InvalidAction("牌组中不存在该卡牌") from exc


def open_event(run: RunState) -> list[EventChoice]:
    """生成奇遇选项；若档案有已结束战报则提供本机因果选项，否则使用普通事件。"""
    choices = [
        EventChoice(id="take_stones", label="顺走香火", description="获得 25 灵石，天谴 +5。"),
        EventChoice(id="heal", label="装作听劝", description="恢复 12 点生命。"),
    ]
    if run.causal_epitaphs:
        epitaph = run.causal_epitaphs[randbelow(run, len(run.causal_epitaphs))]
        choices[0] = EventChoice(id="karma", label="翻阅前人因果", description=epitaph)
    run.choices = choices
    run.phase = "event"
    return choices


def choose_event(run: RunState, choice_id: str) -> list[GameEvent]:
    """结算奇遇选择并完成节点；未知选项或阶段非法时抛 InvalidAction。"""
    if run.phase != "event" or choice_id not in {item.id for item in run.choices}:
        raise InvalidAction("奇遇选项无效")
    if choice_id == "heal":
        healed = min(12, run.player.max_hp - run.player.hp)
        run.player.hp += healed
        event = GameEvent(kind="heal", text=f"恢复 {healed} 点生命", amount=healed)
    else:
        run.player.stones += 25
        run.player.wrath += 5
        event = GameEvent(kind="event", text="获得 25 灵石，天谴增加 5", amount=25)
    run.choices = []
    complete_current_node(run)
    return [event]
