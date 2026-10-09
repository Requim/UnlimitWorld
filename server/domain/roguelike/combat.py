"""回合制战斗与十八张卡牌的权威结算。"""

from __future__ import annotations

from server.domain.roguelike.catalog import get_card, get_enemy
from server.domain.roguelike.errors import InvalidAction
from server.domain.roguelike.models import (
    CardInstance,
    CombatState,
    EnemyIntent,
    EnemyState,
    GameEvent,
    RunState,
)
from server.domain.roguelike.random_source import shuffle


ATTACK_CARDS = {
    "flying_sword",
    "charge_sword",
    "flurry",
    "sword_draw",
    "myriad_swords",
    "fire_seed",
    "burn_heaven",
}


def start_combat(run: RunState, enemy_id: str) -> list[GameEvent]:
    """用当前牌组开始战斗；会洗牌、抽五张并重置场内资源，敌人 ID 无效时抛 KeyError。"""
    definition = get_enemy(enemy_id)
    pile = [card.model_copy(deep=True) for card in run.deck]
    shuffle(run, pile)
    enemy = _create_enemy(definition)
    run.player.block = 6 if "ancestor_talisman" in run.relics else 0
    run.player.reflect = 0
    run.combat = CombatState(enemy=enemy, draw_pile=pile)
    run.phase = "combat"
    draw_cards(run, 5)
    return [GameEvent(kind="combat_start", text=f"遭遇{enemy.name}", target=enemy.id)]


def _create_enemy(definition) -> EnemyState:
    intent = _build_intent(definition.intent_pattern[0])
    return EnemyState(
        id=definition.id,
        name=definition.name,
        hp=definition.max_hp,
        max_hp=definition.max_hp,
        intent=intent,
    )


def _build_intent(raw: tuple[str, int]) -> EnemyIntent:
    kind, value = raw
    if kind == "multi":
        return EnemyIntent(kind="multi", value=value, hits=2, text=f"连续 2 次造成 {value} 点伤害")
    texts = {
        "attack": f"造成 {value} 点伤害",
        "defend": f"获得 {value} 点护盾",
        "burn": f"造成 {value} 点伤害并增加天谴",
    }
    return EnemyIntent(kind=kind, value=value, text=texts[kind])


def draw_cards(run: RunState, count: int) -> list[GameEvent]:
    """从战斗牌堆抽牌，空堆时仅洗入弃牌堆；会修改牌区，非战斗状态抛 InvalidAction。"""
    combat = _combat(run)
    drawn: list[CardInstance] = []
    for _ in range(count):
        if not combat.draw_pile:
            _reshuffle(run)
        if not combat.draw_pile:
            break
        card = combat.draw_pile.pop()
        combat.hand.append(card)
        drawn.append(card)
    return [GameEvent(kind="draw", text=f"抽取 {len(drawn)} 张牌", amount=len(drawn))]


def _reshuffle(run: RunState) -> None:
    combat = _combat(run)
    if not combat.discard_pile:
        return
    combat.draw_pile = combat.discard_pile
    combat.discard_pile = []
    shuffle(run, combat.draw_pile)


def play_card(run: RunState, card_uid: str, target_id: str | None = None) -> list[GameEvent]:
    """即时结算手牌；会扣灵力并移动牌，资源不足、目标或卡 UID 无效时抛 InvalidAction。"""
    combat = _combat(run)
    card = _find_hand_card(combat, card_uid)
    definition = get_card(card.card_id)
    cost = definition.upgraded_cost if card.upgraded else definition.cost
    _validate_play(combat, definition.target, target_id, cost)
    combat.energy -= cost
    combat.hand.remove(card)
    events = _resolve_card(run, card)
    destination = combat.exhaust_pile if definition.exhaust else combat.discard_pile
    destination.append(card)
    _check_deaths(run, events)
    return events


def _find_hand_card(combat: CombatState, card_uid: str) -> CardInstance:
    try:
        return next(card for card in combat.hand if card.uid == card_uid)
    except StopIteration as exc:
        raise InvalidAction("手牌不存在") from exc


def _validate_play(combat: CombatState, target: str, target_id: str | None, cost: int) -> None:
    if combat.energy < cost:
        raise InvalidAction("灵力不足")
    if target == "enemy" and target_id != combat.enemy.id:
        raise InvalidAction("攻击目标无效")
    if target != "enemy" and target_id is not None:
        raise InvalidAction("该卡牌不接受目标")


def _resolve_card(run: RunState, card: CardInstance) -> list[GameEvent]:
    handlers = {
        "flying_sword": _flying_sword,
        "guard": _guard,
        "focus": _focus,
        "charge_sword": _charge_sword,
        "flurry": _flurry,
        "sword_draw": _sword_draw,
        "myriad_swords": _myriad_swords,
        "hidden_edge": _hidden_edge,
        "fire_seed": _fire_seed,
        "fan_flames": _fan_flames,
        "burn_heaven": _burn_heaven,
        "borrow_fire": _borrow_fire,
        "embers": _embers,
        "golden_bell": _golden_bell,
        "demon_mirror": _demon_mirror,
        "silence_talisman": _silence_talisman,
        "swift_script": _swift_script,
        "lightning_talisman": _lightning_talisman,
    }
    return handlers[card.card_id](run, card.upgraded)


def _attack(run: RunState, amount: int) -> GameEvent:
    combat = _combat(run)
    if "broken_wood_sword" in run.relics:
        amount += 2
    dealt = _deal_damage_to_enemy(combat.enemy, amount)
    return GameEvent(kind="damage", text=f"对敌人造成 {dealt} 点伤害", amount=dealt, target=combat.enemy.id)


def _deal_damage_to_enemy(enemy: EnemyState, amount: int) -> int:
    absorbed = min(enemy.block, amount)
    enemy.block -= absorbed
    dealt = amount - absorbed
    enemy.hp = max(0, enemy.hp - dealt)
    return dealt


def _gain_block(run: RunState, amount: int) -> GameEvent:
    run.player.block += amount
    return GameEvent(kind="block", text=f"获得 {amount} 点护盾", amount=amount, target="player")


def _apply_burn(run: RunState, amount: int) -> GameEvent:
    if "ancestral_incense" in run.relics:
        amount += 1
    enemy = _combat(run).enemy
    enemy.burn += amount
    return GameEvent(kind="burn", text=f"施加 {amount} 层燃烧", amount=amount, target=enemy.id)


def _flying_sword(run: RunState, upgraded: bool) -> list[GameEvent]:
    return [_attack(run, 9 if upgraded else 6)]


def _guard(run: RunState, upgraded: bool) -> list[GameEvent]:
    return [_gain_block(run, 9 if upgraded else 6)]


def _focus(run: RunState, upgraded: bool) -> list[GameEvent]:
    events = draw_cards(run, 3 if upgraded else 2)
    _combat(run).energy += 1
    events.append(GameEvent(kind="energy", text="回复 1 点灵力", amount=1, target="player"))
    return events


def _charge_sword(run: RunState, upgraded: bool) -> list[GameEvent]:
    combat = _combat(run)
    gain = 2 if upgraded else 1
    combat.sword_intent += gain
    return [_attack(run, 6 if upgraded else 4), GameEvent(kind="sword_intent", text=f"获得 {gain} 剑意", amount=gain)]


def _flurry(run: RunState, upgraded: bool) -> list[GameEvent]:
    amount = 4 if upgraded else 3
    events = []
    for _ in range(2):
        if _combat(run).enemy.hp <= 0:
            break
        events.append(_attack(run, amount))
    return events


def _sword_draw(run: RunState, upgraded: bool) -> list[GameEvent]:
    return [_attack(run, 7 if upgraded else 5), *draw_cards(run, 2 if upgraded else 1)]


def _myriad_swords(run: RunState, upgraded: bool) -> list[GameEvent]:
    combat = _combat(run)
    amount = (10 if upgraded else 8) + combat.sword_intent * (5 if upgraded else 4)
    combat.sword_intent = 0
    return [_attack(run, amount)]


def _hidden_edge(run: RunState, upgraded: bool) -> list[GameEvent]:
    combat = _combat(run)
    gain = 2 if upgraded else 1
    combat.sword_intent += gain
    return [_gain_block(run, 8 if upgraded else 5), GameEvent(kind="sword_intent", text=f"获得 {gain} 剑意", amount=gain)]


def _fire_seed(run: RunState, upgraded: bool) -> list[GameEvent]:
    return [_attack(run, 6 if upgraded else 4), _apply_burn(run, 4 if upgraded else 3)]


def _fan_flames(run: RunState, upgraded: bool) -> list[GameEvent]:
    return [_apply_burn(run, 6 if upgraded else 4)]


def _burn_heaven(run: RunState, upgraded: bool) -> list[GameEvent]:
    amount = (14 if upgraded else 10) + run.player.wrath // 4
    run.player.wrath += 6
    return [_attack(run, amount), GameEvent(kind="wrath", text="天谴增加 6", amount=6, target="player")]


def _borrow_fire(run: RunState, upgraded: bool) -> list[GameEvent]:
    energy = 3 if upgraded else 2
    wrath = 8 if upgraded else 10
    _combat(run).energy += energy
    run.player.wrath += wrath
    return [
        GameEvent(kind="energy", text=f"获得 {energy} 点灵力", amount=energy, target="player"),
        GameEvent(kind="wrath", text=f"天谴增加 {wrath}", amount=wrath, target="player"),
    ]


def _embers(run: RunState, upgraded: bool) -> list[GameEvent]:
    reduction = 8 if upgraded else 5
    run.player.wrath = max(0, run.player.wrath - reduction)
    return [_gain_block(run, 10 if upgraded else 7), GameEvent(kind="wrath", text=f"天谴降低 {reduction}", amount=-reduction)]


def _golden_bell(run: RunState, upgraded: bool) -> list[GameEvent]:
    return [_gain_block(run, 12 if upgraded else 8)]


def _demon_mirror(run: RunState, upgraded: bool) -> list[GameEvent]:
    amount = 6 if upgraded else 4
    run.player.reflect += amount
    return [_gain_block(run, amount), GameEvent(kind="reflect", text=f"获得 {amount} 点反伤", amount=amount)]


def _silence_talisman(run: RunState, upgraded: bool) -> list[GameEvent]:
    amount = 3 if upgraded else 2
    _combat(run).enemy.weak += amount
    return [GameEvent(kind="weak", text=f"敌人虚弱 {amount} 回合", amount=amount, target=_combat(run).enemy.id)]


def _swift_script(run: RunState, upgraded: bool) -> list[GameEvent]:
    return draw_cards(run, 3 if upgraded else 2)


def _lightning_talisman(run: RunState, upgraded: bool) -> list[GameEvent]:
    _combat(run).lightning_redirect = True
    return [GameEvent(kind="redirect", text="下一次雷罚将转移给敌人")]


def taunt(run: RunState) -> list[GameEvent]:
    """每场战斗一次换取灵力并强化敌方攻击；重复使用抛 InvalidAction。"""
    combat = _combat(run)
    if combat.taunt_used:
        raise InvalidAction("本场战斗已经挑衅过")
    combat.taunt_used = True
    combat.energy += 1
    if "advice_bell" not in run.relics:
        run.player.wrath += 8
    if combat.enemy.intent.kind in {"attack", "multi", "burn"}:
        combat.enemy.intent.value += 2
        combat.enemy.intent.text = _intent_text(combat.enemy.intent)
    return [GameEvent(kind="taunt", text="挑衅成功：获得 1 灵力，敌人攻势增强")]


def _intent_text(intent: EnemyIntent) -> str:
    if intent.kind == "multi":
        return f"连续 {intent.hits} 次造成 {intent.value} 点伤害"
    if intent.kind == "burn":
        return f"造成 {intent.value} 点伤害并增加天谴"
    return f"造成 {intent.value} 点伤害"


def end_turn(run: RunState) -> list[GameEvent]:
    """按雷罚、敌方行动、燃烧顺序结算并开启下回合；死亡会立即中止后续行动。"""
    combat = _combat(run)
    combat.discard_pile.extend(combat.hand)
    combat.hand = []
    events = _resolve_thunder(run)
    if _check_deaths(run, events):
        return events
    events.extend(_enemy_action(run))
    if _check_deaths(run, events):
        return events
    events.extend(_burn_tick(run))
    if _check_deaths(run, events):
        return events
    events.extend(_start_player_turn(run))
    return events


def _resolve_thunder(run: RunState) -> list[GameEvent]:
    events = []
    combat = _combat(run)
    while run.player.wrath >= 30:
        run.player.wrath -= 30
        if combat.lightning_redirect:
            damage = 10 if "heaven_iou" in run.relics else 8
            dealt = _deal_damage_to_enemy(combat.enemy, damage)
            combat.lightning_redirect = False
            events.append(GameEvent(kind="thunder", text=f"雷罚转移，造成 {dealt} 点伤害", amount=dealt, target=combat.enemy.id))
        else:
            dealt = _damage_player(run, 8)
            events.append(GameEvent(kind="thunder", text=f"雷罚造成 {dealt} 点伤害", amount=dealt, target="player"))
        if run.player.hp <= 0 or combat.enemy.hp <= 0:
            break
    return events


def _enemy_action(run: RunState) -> list[GameEvent]:
    combat = _combat(run)
    enemy = combat.enemy
    intent = enemy.intent
    events: list[GameEvent] = []
    if intent.kind == "defend":
        enemy.block += intent.value
        events.append(GameEvent(kind="enemy_block", text=f"敌人获得 {intent.value} 护盾", amount=intent.value, target=enemy.id))
    else:
        events.extend(_enemy_attacks(run, intent))
        if intent.kind == "burn" and run.player.hp > 0:
            run.player.wrath += 3
            events.append(GameEvent(kind="wrath", text="敌招令天谴增加 3", amount=3, target="player"))
    if enemy.weak > 0:
        enemy.weak -= 1
    _advance_intent(enemy)
    return events


def _enemy_attacks(run: RunState, intent: EnemyIntent) -> list[GameEvent]:
    events = []
    amount = intent.value * 3 // 4 if _combat(run).enemy.weak > 0 else intent.value
    for _ in range(intent.hits):
        if run.player.hp <= 0:
            break
        dealt = _damage_player(run, amount)
        events.append(GameEvent(kind="enemy_damage", text=f"受到 {dealt} 点伤害", amount=dealt, target="player"))
        if run.player.reflect > 0:
            reflected = _deal_damage_to_enemy(_combat(run).enemy, run.player.reflect)
            events.append(GameEvent(kind="reflect", text=f"反伤 {reflected} 点", amount=reflected, target=_combat(run).enemy.id))
            if _combat(run).enemy.hp <= 0:
                break
    return events


def _damage_player(run: RunState, amount: int) -> int:
    absorbed = min(run.player.block, amount)
    run.player.block -= absorbed
    dealt = amount - absorbed
    run.player.hp = max(0, run.player.hp - dealt)
    return dealt


def _advance_intent(enemy: EnemyState) -> None:
    definition = get_enemy(enemy.id)
    enemy.intent_index = (enemy.intent_index + 1) % len(definition.intent_pattern)
    enemy.intent = _build_intent(definition.intent_pattern[enemy.intent_index])


def _burn_tick(run: RunState) -> list[GameEvent]:
    enemy = _combat(run).enemy
    if enemy.burn <= 0:
        return []
    bonus = 2 if "charred_bone" in run.relics else 0
    dealt = _deal_damage_to_enemy(enemy, enemy.burn + bonus)
    enemy.burn = max(0, enemy.burn - 1)
    return [GameEvent(kind="burn_tick", text=f"燃烧造成 {dealt} 点伤害", amount=dealt, target=enemy.id)]


def _start_player_turn(run: RunState) -> list[GameEvent]:
    combat = _combat(run)
    run.player.block = 0
    run.player.reflect = 0
    combat.turn += 1
    combat.energy = combat.max_energy
    return draw_cards(run, 5)


def _check_deaths(run: RunState, events: list[GameEvent]) -> bool:
    combat = _combat(run)
    if run.player.hp <= 0:
        run.phase = "game_over"
        run.epitaph = f"止步第 {run.layer} 层，被{combat.enemy.name}收走了嘴硬。"
        events.append(GameEvent(kind="defeat", text=run.epitaph, target="player"))
        return True
    if combat.enemy.hp <= 0:
        run.phase = "battle_won"
        events.append(GameEvent(kind="victory", text=f"击败{combat.enemy.name}", target=combat.enemy.id))
        return True
    return False


def _combat(run: RunState) -> CombatState:
    if run.phase not in {"combat", "battle_won"} or run.combat is None:
        raise InvalidAction("当前不在战斗中")
    return run.combat
