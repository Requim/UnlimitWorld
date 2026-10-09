"""回合制战斗与十八张卡牌的权威结算。"""

from __future__ import annotations

from server.domain.roguelike.catalog import get_card, get_enemy
from server.domain.roguelike.errors import InvalidAction
from server.domain.roguelike.models import (
    CardInstance,
    CombatState,
    EventSource,
    EnemyIntent,
    EnemyState,
    GameEvent,
    RunState,
)
from server.domain.roguelike.presentation import battle_event
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


def start_combat(
    run: RunState, enemy_id: str, *, defeat_epitaph: str | None = None
) -> list[GameEvent]:
    """用当前牌组开始战斗；可持久化内容侧失败碑文，敌人 ID 无效时抛 KeyError。"""
    definition = get_enemy(enemy_id)
    pile = [card.model_copy(deep=True) for card in run.deck]
    shuffle(run, pile)
    enemy = _create_enemy(definition)
    run.player.block = 6 if "ancestor_talisman" in run.relics else 0
    run.player.reflect = 0
    run.combat = CombatState(
        enemy=enemy,
        draw_pile=pile,
        defeat_epitaph=defeat_epitaph,
    )
    run.phase = "combat"
    draw_cards(run, 5)
    return [
        battle_event(
            run,
            "combat_start",
            f"遭遇{enemy.name}",
            target=enemy.id,
            source="system",
        )
    ]


def _create_enemy(definition) -> EnemyState:
    intent = _build_intent(definition.intent_pattern[0])
    return EnemyState(
        id=definition.id,
        name=definition.name,
        hp=definition.max_hp,
        max_hp=definition.max_hp,
        intent=intent,
    )


def _build_intent(
    raw: tuple[str, int], *, weak: int = 0, attack_bonus: int = 0
) -> EnemyIntent:
    kind, base_value = raw
    value = _final_intent_value(kind, base_value, weak, attack_bonus)
    if kind == "multi":
        return EnemyIntent(kind="multi", value=value, hits=2, text=f"连续 2 次造成 {value} 点伤害")
    if kind == "burn":
        return EnemyIntent(kind="burn", value=value, wrath_change=3, text=f"造成 {value} 点伤害，天谴 +3")
    text = f"获得 {value} 点护盾" if kind == "defend" else f"造成 {value} 点伤害"
    return EnemyIntent(kind=kind, value=value, text=text)


def _final_intent_value(kind: str, base: int, weak: int, attack_bonus: int) -> int:
    if kind == "defend":
        return base
    value = base + attack_bonus
    return value * 3 // 4 if weak > 0 else value


def draw_cards(
    run: RunState,
    count: int,
    *,
    source: EventSource = "system",
    card_id: str | None = None,
) -> list[GameEvent]:
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
    return [
        battle_event(
            run,
            "draw",
            f"抽取 {len(drawn)} 张牌",
            amount=len(drawn),
            source=source,
            card_id=card_id,
        )
    ]


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
    return handlers[card.card_id](run, card)


def _attack(run: RunState, amount: int, card_id: str) -> GameEvent:
    combat = _combat(run)
    if "broken_wood_sword" in run.relics:
        amount += 2
    dealt, absorbed = _damage_enemy(combat.enemy, amount)
    visual = "fire" if card_id in {"fire_seed", "burn_heaven"} else "sword"
    return battle_event(
        run,
        "damage",
        f"对敌人造成 {dealt} 点伤害",
        amount=dealt,
        target=combat.enemy.id,
        source="player",
        card_id=card_id,
        visual=visual,
        absorbed=absorbed,
    )


def _damage_enemy(enemy: EnemyState, amount: int) -> tuple[int, int]:
    absorbed = min(enemy.block, amount)
    enemy.block -= absorbed
    dealt = amount - absorbed
    enemy.hp = max(0, enemy.hp - dealt)
    return dealt, absorbed


def _gain_block(run: RunState, amount: int, card_id: str) -> GameEvent:
    run.player.block += amount
    return battle_event(
        run,
        "block",
        f"获得 {amount} 点护盾",
        amount=amount,
        target="player",
        source="player",
        card_id=card_id,
        visual="shield",
    )


def _apply_burn(run: RunState, amount: int, card_id: str) -> GameEvent:
    if "ancestral_incense" in run.relics:
        amount += 1
    enemy = _combat(run).enemy
    enemy.burn += amount
    return battle_event(
        run,
        "burn",
        f"施加 {amount} 层燃烧",
        amount=amount,
        target=enemy.id,
        source="player",
        card_id=card_id,
        visual="fire",
    )


def _flying_sword(run: RunState, card: CardInstance) -> list[GameEvent]:
    return [_attack(run, 9 if card.upgraded else 6, card.card_id)]


def _guard(run: RunState, card: CardInstance) -> list[GameEvent]:
    return [_gain_block(run, 9 if card.upgraded else 6, card.card_id)]


def _focus(run: RunState, card: CardInstance) -> list[GameEvent]:
    count = 3 if card.upgraded else 2
    events = draw_cards(run, count, source="player", card_id=card.card_id)
    _combat(run).energy += 1
    events.append(_player_event(run, "energy", "回复 1 点灵力", 1, card.card_id))
    return events


def _charge_sword(run: RunState, card: CardInstance) -> list[GameEvent]:
    combat = _combat(run)
    events = [_attack(run, 6 if card.upgraded else 4, card.card_id)]
    if combat.enemy.hp <= 0:
        return events
    gain = 2 if card.upgraded else 1
    combat.sword_intent += gain
    events.append(_player_event(run, "sword_intent", f"获得 {gain} 剑意", gain, card.card_id))
    return events


def _flurry(run: RunState, card: CardInstance) -> list[GameEvent]:
    amount = 4 if card.upgraded else 3
    events = []
    for _ in range(2):
        if _combat(run).enemy.hp <= 0:
            break
        events.append(_attack(run, amount, card.card_id))
    return events


def _sword_draw(run: RunState, card: CardInstance) -> list[GameEvent]:
    events = [_attack(run, 7 if card.upgraded else 5, card.card_id)]
    if _combat(run).enemy.hp > 0:
        count = 2 if card.upgraded else 1
        events.extend(draw_cards(run, count, source="player", card_id=card.card_id))
    return events


def _myriad_swords(run: RunState, card: CardInstance) -> list[GameEvent]:
    combat = _combat(run)
    amount = (10 if card.upgraded else 8) + combat.sword_intent * (5 if card.upgraded else 4)
    combat.sword_intent = 0
    return [_attack(run, amount, card.card_id)]


def _hidden_edge(run: RunState, card: CardInstance) -> list[GameEvent]:
    combat = _combat(run)
    events = [_gain_block(run, 8 if card.upgraded else 5, card.card_id)]
    gain = 2 if card.upgraded else 1
    combat.sword_intent += gain
    events.append(_player_event(run, "sword_intent", f"获得 {gain} 剑意", gain, card.card_id))
    return events


def _fire_seed(run: RunState, card: CardInstance) -> list[GameEvent]:
    events = [_attack(run, 6 if card.upgraded else 4, card.card_id)]
    if _combat(run).enemy.hp > 0:
        events.append(_apply_burn(run, 4 if card.upgraded else 3, card.card_id))
    return events


def _fan_flames(run: RunState, card: CardInstance) -> list[GameEvent]:
    return [_apply_burn(run, 6 if card.upgraded else 4, card.card_id)]


def _burn_heaven(run: RunState, card: CardInstance) -> list[GameEvent]:
    amount = (14 if card.upgraded else 10) + run.player.wrath // 4
    events = [_attack(run, amount, card.card_id)]
    if _combat(run).enemy.hp <= 0:
        return events
    run.player.wrath += 6
    events.append(_player_event(run, "wrath", "天谴增加 6", 6, card.card_id))
    return events


def _borrow_fire(run: RunState, card: CardInstance) -> list[GameEvent]:
    energy = 3 if card.upgraded else 2
    wrath = 8 if card.upgraded else 10
    _combat(run).energy += energy
    events = [_player_event(run, "energy", f"获得 {energy} 点灵力", energy, card.card_id)]
    run.player.wrath += wrath
    events.append(_player_event(run, "wrath", f"天谴增加 {wrath}", wrath, card.card_id))
    return events


def _embers(run: RunState, card: CardInstance) -> list[GameEvent]:
    reduction = 8 if card.upgraded else 5
    events = [_gain_block(run, 10 if card.upgraded else 7, card.card_id)]
    run.player.wrath = max(0, run.player.wrath - reduction)
    events.append(_player_event(run, "wrath", f"天谴降低 {reduction}", -reduction, card.card_id))
    return events


def _golden_bell(run: RunState, card: CardInstance) -> list[GameEvent]:
    return [_gain_block(run, 12 if card.upgraded else 8, card.card_id)]


def _demon_mirror(run: RunState, card: CardInstance) -> list[GameEvent]:
    amount = 6 if card.upgraded else 4
    events = [_gain_block(run, amount, card.card_id)]
    run.player.reflect += amount
    events.append(_player_event(run, "reflect", f"获得 {amount} 点反伤", amount, card.card_id))
    return events


def _silence_talisman(run: RunState, card: CardInstance) -> list[GameEvent]:
    amount = 3 if card.upgraded else 2
    combat = _combat(run)
    combat.enemy.weak += amount
    _refresh_intent(combat)
    return [
        battle_event(
            run,
            "weak",
            f"敌人虚弱 {amount} 回合",
            amount=amount,
            target=combat.enemy.id,
            source="player",
            card_id=card.card_id,
        )
    ]


def _swift_script(run: RunState, card: CardInstance) -> list[GameEvent]:
    count = 3 if card.upgraded else 2
    return draw_cards(run, count, source="player", card_id=card.card_id)


def _lightning_talisman(run: RunState, card: CardInstance) -> list[GameEvent]:
    _combat(run).lightning_redirect = True
    return [
        battle_event(
            run,
            "redirect",
            "下一次雷罚将转移给敌人",
            source="player",
            card_id=card.card_id,
            visual="thunder",
        )
    ]


def _player_event(
    run: RunState, kind: str, text: str, amount: int, card_id: str
) -> GameEvent:
    return battle_event(
        run,
        kind,
        text,
        amount=amount,
        target="player",
        source="player",
        card_id=card_id,
    )


def taunt(run: RunState) -> list[GameEvent]:
    """每场战斗一次换取灵力并强化敌方攻击；重复使用抛 InvalidAction。"""
    combat = _combat(run)
    if combat.taunt_used:
        raise InvalidAction("本场战斗已经挑衅过")
    combat.taunt_used = True
    combat.energy += 1
    wrath_change = 0 if "advice_bell" in run.relics else 8
    run.player.wrath += wrath_change
    combat.pending_attack_bonus += 2
    _refresh_intent(combat)
    text = f"挑衅成功：获得 1 灵力，天谴 +{wrath_change}；敌人下次攻击每段 +2"
    return [battle_event(run, "taunt", text, source="player")]


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
            dealt, absorbed = _damage_enemy(combat.enemy, damage)
            combat.lightning_redirect = False
            events.append(
                _thunder_event(run, dealt, absorbed, combat.enemy.id, redirected=True)
            )
        else:
            dealt, absorbed = _damage_player(run, 8)
            events.append(_thunder_event(run, dealt, absorbed, "player"))
        if run.player.hp <= 0 or combat.enemy.hp <= 0:
            break
    return events


def _thunder_event(
    run: RunState,
    dealt: int,
    absorbed: int,
    target: str,
    *,
    redirected: bool = False,
) -> GameEvent:
    text = f"雷罚转移，造成 {dealt} 点伤害" if redirected else f"雷罚造成 {dealt} 点伤害"
    return battle_event(
        run,
        "thunder",
        text,
        amount=dealt,
        target=target,
        source="heaven",
        visual="thunder",
        absorbed=absorbed,
    )


def _enemy_action(run: RunState) -> list[GameEvent]:
    combat = _combat(run)
    enemy = combat.enemy
    intent = enemy.intent
    events: list[GameEvent] = []
    if intent.kind == "defend":
        enemy.block += intent.value
        events.append(
            battle_event(
                run,
                "enemy_block",
                f"敌人获得 {intent.value} 护盾",
                amount=intent.value,
                target=enemy.id,
                source="enemy",
                visual="shield",
            )
        )
    else:
        events.extend(_enemy_attacks(run, intent))
        combat.pending_attack_bonus = 0
        if run.player.hp <= 0 or enemy.hp <= 0:
            return events
        if intent.wrath_change:
            run.player.wrath += intent.wrath_change
            events.append(
                battle_event(
                    run,
                    "wrath",
                    f"敌招令天谴增加 {intent.wrath_change}",
                    amount=intent.wrath_change,
                    target="player",
                    source="enemy",
                    visual="fire",
                )
            )
    if enemy.weak > 0:
        enemy.weak -= 1
    _advance_intent(combat)
    return events


def _enemy_attacks(run: RunState, intent: EnemyIntent) -> list[GameEvent]:
    events = []
    for _ in range(intent.hits):
        if run.player.hp <= 0:
            break
        dealt, absorbed = _damage_player(run, intent.value)
        events.append(
            battle_event(
                run,
                "enemy_damage",
                f"受到 {dealt} 点伤害",
                amount=dealt,
                target="player",
                source="enemy",
                visual="hit",
                absorbed=absorbed,
            )
        )
        if run.player.hp > 0 and run.player.reflect > 0:
            enemy = _combat(run).enemy
            reflected, blocked = _damage_enemy(enemy, run.player.reflect)
            events.append(
                battle_event(
                    run,
                    "reflect",
                    f"反伤 {reflected} 点",
                    amount=reflected,
                    target=enemy.id,
                    source="player",
                    visual="hit",
                    absorbed=blocked,
                )
            )
            if _combat(run).enemy.hp <= 0:
                break
    return events


def _damage_player(run: RunState, amount: int) -> tuple[int, int]:
    absorbed = min(run.player.block, amount)
    run.player.block -= absorbed
    dealt = amount - absorbed
    run.player.hp = max(0, run.player.hp - dealt)
    return dealt, absorbed


def _advance_intent(combat: CombatState) -> None:
    definition = get_enemy(combat.enemy.id)
    combat.enemy.intent_index = (combat.enemy.intent_index + 1) % len(definition.intent_pattern)
    _refresh_intent(combat)


def _refresh_intent(combat: CombatState) -> None:
    enemy = combat.enemy
    definition = get_enemy(enemy.id)
    raw = definition.intent_pattern[enemy.intent_index]
    enemy.intent = _build_intent(
        raw,
        weak=enemy.weak,
        attack_bonus=combat.pending_attack_bonus,
    )


def refresh_intent(run: RunState) -> None:
    """刷新当前敌人公开预告；非战斗阶段抛 InvalidAction，会修改 combat.intent。"""
    _refresh_intent(_combat(run))


def _burn_tick(run: RunState) -> list[GameEvent]:
    enemy = _combat(run).enemy
    if enemy.burn <= 0:
        return []
    bonus = 2 if "charred_bone" in run.relics else 0
    dealt, absorbed = _damage_enemy(enemy, enemy.burn + bonus)
    enemy.burn = max(0, enemy.burn - 1)
    return [
        battle_event(
            run,
            "burn_tick",
            f"燃烧造成 {dealt} 点伤害",
            amount=dealt,
            target=enemy.id,
            source="system",
            visual="fire",
            absorbed=absorbed,
        )
    ]


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
        run.epitaph = combat.defeat_epitaph or f"止步第 {run.layer} 层，被{combat.enemy.name}收走了嘴硬。"
        events.append(
            battle_event(
                run,
                "defeat",
                run.epitaph,
                target="player",
                source="system",
                visual="defeat",
            )
        )
        return True
    if combat.enemy.hp <= 0:
        run.phase = "battle_won"
        events.append(
            battle_event(
                run,
                "victory",
                f"击败{combat.enemy.name}",
                target=combat.enemy.id,
                source="system",
                visual="defeat",
            )
        )
        return True
    return False


def _combat(run: RunState) -> CombatState:
    if run.phase not in {"combat", "battle_won"} or run.combat is None:
        raise InvalidAction("当前不在战斗中")
    return run.combat
