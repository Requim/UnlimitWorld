from __future__ import annotations

import pytest

from server.application.roguelike.factory import create_run_state
from server.application.roguelike.views import build_run_view
from server.domain.roguelike.catalog import get_catalog
from server.domain.roguelike.combat import end_turn, play_card, start_combat, taunt
from server.domain.roguelike.errors import InvalidAction
from server.domain.roguelike.models import CardInstance, EnemyIntent
from server.domain.roguelike.nodes import (
    buy_item,
    choose_reward,
    finish_rest,
    generate_reward,
    open_shop,
    remove_card,
    upgrade_card,
)


def make_combat(archetype: str = "sword", enemy_id: str = "paper_soldier"):
    run = create_run_state("profile-test", archetype, seed=17)
    start_combat(run, enemy_id)
    assert run.combat is not None
    return run


def put_card_in_hand(run, card_id: str, *, upgraded: bool = False) -> CardInstance:
    assert run.combat is not None
    card = CardInstance(uid=f"test-{card_id}", card_id=card_id, upgraded=upgraded)
    run.combat.hand = [card]
    run.combat.energy = 9
    return card


def passive_enemy(run, *, hp: int = 100) -> None:
    assert run.combat is not None
    run.combat.enemy.hp = hp
    run.combat.enemy.max_hp = hp
    run.combat.enemy.intent = EnemyIntent(kind="defend", value=0, text="按兵不动")


def test_catalog_contains_complete_launch_content() -> None:
    catalog = get_catalog()

    assert len(catalog.cards) == 18
    assert len(catalog.relics) == 6
    assert len(catalog.enemies) == 7
    assert next(enemy for enemy in catalog.enemies if enemy.id == "bifang").max_hp == 48
    assert {item.id for item in catalog.archetypes} == {"sword", "fire", "talisman"}
    assert all(card.upgrade_text for card in catalog.cards)
    assert all(item.description for item in catalog.relics)


def test_sword_finisher_consumes_intent_for_burst_damage() -> None:
    run = make_combat()
    passive_enemy(run)
    assert run.combat is not None
    run.combat.sword_intent = 3
    card = put_card_in_hand(run, "myriad_swords")

    events = play_card(run, card.uid, run.combat.enemy.id)

    assert run.combat.enemy.hp == 80
    assert run.combat.sword_intent == 0
    assert any(event.kind == "damage" and event.amount == 20 for event in events)


def test_burn_ticks_after_enemy_action_and_then_decays() -> None:
    run = make_combat("fire")
    passive_enemy(run)
    assert run.combat is not None
    run.combat.enemy.burn = 5

    end_turn(run)

    assert run.combat.enemy.hp == 95
    assert run.combat.enemy.burn == 4


def test_reflect_damages_attacker_after_an_attack() -> None:
    run = make_combat("talisman")
    assert run.combat is not None
    run.combat.enemy.hp = 40
    run.combat.enemy.max_hp = 40
    run.combat.enemy.intent = EnemyIntent(kind="attack", value=7, text="造成 7 点伤害")
    run.player.block = 10
    run.player.reflect = 4

    end_turn(run)

    assert run.player.hp == 60
    assert run.combat.enemy.hp == 36


@pytest.mark.parametrize(
    ("wrath", "expected_hp", "expected_wrath"),
    [(29, 60, 29), (30, 52, 0), (60, 44, 0)],
)
def test_thunder_boundary_hits_player_before_enemy_action(
    wrath: int, expected_hp: int, expected_wrath: int
) -> None:
    run = make_combat()
    passive_enemy(run)
    assert run.combat is not None
    run.player.wrath = wrath

    end_turn(run)

    assert run.player.hp == expected_hp
    assert run.player.wrath == expected_wrath


def test_lightning_talisman_redirects_next_thunder_to_enemy() -> None:
    run = make_combat("talisman")
    passive_enemy(run)
    assert run.combat is not None
    run.player.wrath = 30
    card = put_card_in_hand(run, "lightning_talisman")

    play_card(run, card.uid, run.combat.enemy.id)
    end_turn(run)

    assert run.player.hp == 60
    assert run.combat.enemy.hp == 92
    assert run.player.wrath == 0


def test_lethal_thunder_stops_enemy_action_immediately() -> None:
    run = make_combat()
    assert run.combat is not None
    run.player.hp = 8
    run.player.wrath = 30
    run.combat.enemy.intent = EnemyIntent(kind="attack", value=99, text="造成 99 点伤害")
    enemy_hp = run.combat.enemy.hp

    events = end_turn(run)

    assert run.phase == "game_over"
    assert run.combat.enemy.hp == enemy_hp
    assert [event.kind for event in events] == ["thunder", "defeat"]


def test_redirected_lethal_thunder_stops_enemy_action() -> None:
    run = make_combat("talisman")
    assert run.combat is not None
    run.player.wrath = 30
    run.combat.lightning_redirect = True
    run.combat.enemy.hp = 8
    run.combat.enemy.intent = EnemyIntent(kind="attack", value=99, text="造成 99 点伤害")

    events = end_turn(run)

    assert run.phase == "battle_won"
    assert run.player.hp == 60
    assert [event.kind for event in events] == ["thunder", "victory"]


def test_taunt_can_only_be_used_once_per_combat() -> None:
    run = make_combat()
    assert run.combat is not None
    before_energy = run.combat.energy
    before_intent = run.combat.enemy.intent.value

    taunt(run)

    assert run.combat.energy == before_energy + 1
    assert run.player.wrath == 8
    assert run.combat.enemy.intent.value == before_intent + 2
    with pytest.raises(InvalidAction):
        taunt(run)


def test_taunt_during_defend_is_carried_to_next_real_attack() -> None:
    run = make_combat()
    assert run.combat is not None
    run.combat.enemy.intent_index = 1
    run.combat.enemy.intent = EnemyIntent(kind="defend", value=4, text="获得 4 点护盾")

    taunt(run)
    end_turn(run)

    assert run.combat.pending_attack_bonus == 2
    assert run.combat.enemy.intent.kind == "attack"
    assert run.combat.enemy.intent.value == 6
    end_turn(run)
    assert run.player.hp == 54
    assert run.combat.pending_attack_bonus == 0


def test_taunt_preview_uses_relic_adjusted_authoritative_values() -> None:
    run = make_combat()
    run.relics.append("advice_bell")

    preview = build_run_view(run).combat.taunt_preview

    assert preview.available is True
    assert preview.energy_gain == 1
    assert preview.wrath_change == 0
    assert preview.next_attack_bonus == 2
    assert "天谴 +0" in preview.text
    assert "下次攻击" in preview.text


def test_weak_preview_matches_damage_and_expires_by_enemy_turn() -> None:
    run = make_combat("talisman")
    assert run.combat is not None
    card = put_card_in_hand(run, "silence_talisman")

    play_card(run, card.uid, run.combat.enemy.id)

    assert run.combat.enemy.intent.value == 3
    end_turn(run)
    assert run.player.hp == 57
    assert run.combat.enemy.weak == 1
    end_turn(run)
    assert run.combat.enemy.weak == 0
    assert run.combat.enemy.intent.value == 4


def test_burn_intent_preview_matches_damage_hits_and_wrath() -> None:
    run = make_combat("talisman", "incense_guest")
    assert run.combat is not None
    card = put_card_in_hand(run, "silence_talisman")
    play_card(run, card.uid, run.combat.enemy.id)
    taunt(run)
    preview = run.combat.enemy.intent

    assert preview.value == 3
    assert preview.hits == 1
    assert preview.wrath_change == 3
    assert "天谴 +3" in preview.text
    events = end_turn(run)
    damage = next(event.amount for event in events if event.kind == "enemy_damage")
    assert damage == preview.value
    assert run.player.wrath == 11


def test_player_block_absorbs_thunder_then_clears_next_turn() -> None:
    run = make_combat()
    passive_enemy(run)
    run.player.block = 5
    run.player.wrath = 30

    events = end_turn(run)

    thunder = next(event for event in events if event.kind == "thunder")
    assert thunder.amount == 3
    assert run.player.hp == 57
    assert run.player.block == 0


def test_remaining_block_is_cleared_when_next_player_turn_starts() -> None:
    run = make_combat()
    passive_enemy(run)
    run.player.block = 20
    run.player.wrath = 30

    events = end_turn(run)

    thunder = next(event for event in events if event.kind == "thunder")
    assert thunder.amount == 0
    assert run.player.hp == 60
    assert run.player.block == 0


def test_lethal_enemy_attack_does_not_trigger_reflect() -> None:
    run = make_combat("talisman")
    assert run.combat is not None
    run.player.hp = 3
    run.player.reflect = 10
    run.combat.enemy.hp = 40
    run.combat.enemy.max_hp = 40
    run.combat.enemy.intent = EnemyIntent(kind="attack", value=4, text="造成 4 点伤害")

    end_turn(run)

    assert run.phase == "game_over"
    assert run.combat.enemy.hp == 40


def test_lethal_sword_draw_does_not_draw_or_advance_random_source() -> None:
    run = make_combat("sword")
    assert run.combat is not None
    run.combat.enemy.hp = 5
    card = put_card_in_hand(run, "sword_draw")
    run.combat.draw_pile = [CardInstance(uid="waiting", card_id="guard")]
    counter = run.rng_counter

    play_card(run, card.uid, run.combat.enemy.id)

    assert run.phase == "battle_won"
    assert run.combat.hand == []
    assert run.combat.draw_pile[0].uid == "waiting"
    assert run.rng_counter == counter


@pytest.mark.parametrize(
    ("archetype", "card_id", "field"),
    [("sword", "charge_sword", "sword_intent"), ("fire", "fire_seed", "burn")],
)
def test_lethal_attack_skips_followup_effect(archetype: str, card_id: str, field: str) -> None:
    run = make_combat(archetype)
    assert run.combat is not None
    run.combat.enemy.hp = 4
    card = put_card_in_hand(run, card_id)

    play_card(run, card.uid, run.combat.enemy.id)

    target = run.combat if field == "sword_intent" else run.combat.enemy
    assert getattr(target, field) == 0


def test_zero_energy_and_invalid_target_do_not_mutate_combat() -> None:
    run = make_combat()
    assert run.combat is not None
    card = put_card_in_hand(run, "flying_sword")
    run.combat.energy = 0
    snapshot = run.model_dump(mode="json")

    with pytest.raises(InvalidAction):
        play_card(run, card.uid, run.combat.enemy.id)
    assert run.model_dump(mode="json") == snapshot

    run.combat.energy = 3
    snapshot = run.model_dump(mode="json")
    with pytest.raises(InvalidAction):
        play_card(run, card.uid, "missing-enemy")
    assert run.model_dump(mode="json") == snapshot


def test_exhausted_card_never_enters_reshuffled_draw_pile() -> None:
    run = make_combat("talisman")
    assert run.combat is not None
    card = put_card_in_hand(run, "swift_script")
    run.combat.draw_pile = []
    run.combat.discard_pile = [CardInstance(uid="discard", card_id="guard")]

    play_card(run, card.uid)

    all_live = run.combat.hand + run.combat.draw_pile + run.combat.discard_pile
    assert card.uid in {item.uid for item in run.combat.exhaust_pile}
    assert card.uid not in {item.uid for item in all_live}


def test_reward_is_generated_once_and_card_choice_is_added() -> None:
    run = create_run_state("profile-test", "fire", seed=19)

    first = generate_reward(run, "normal")
    second = generate_reward(run, "normal")

    assert first == second
    assert len(first.cards) == 3
    before = len(run.deck)
    chosen_id = first.cards[1].card_id
    choose_reward(run, 1)
    assert len(run.deck) == before + 1
    assert run.deck[-1].card_id == chosen_id


def test_shop_rejects_insufficient_or_duplicate_purchase() -> None:
    run = create_run_state("profile-test", "sword", seed=23)
    run.player.stones = 0
    shop = open_shop(run)
    item = shop.items[0]

    with pytest.raises(InvalidAction):
        buy_item(run, item.id)
    run.player.stones = item.price
    buy_item(run, item.id)
    with pytest.raises(InvalidAction):
        buy_item(run, item.id)


def test_upgrade_once_and_minimum_deck_size_are_enforced() -> None:
    run = create_run_state("profile-test", "sword", seed=29)
    card = run.deck[0]

    upgrade_card(run, card.uid)
    with pytest.raises(InvalidAction):
        upgrade_card(run, card.uid)

    run.deck = run.deck[:5]
    with pytest.raises(InvalidAction):
        remove_card(run, run.deck[0].uid)


def test_rest_heals_thirty_percent_without_exceeding_maximum() -> None:
    run = create_run_state("profile-test", "sword", seed=31)
    run.player.hp = 50
    run.phase = "rest"

    finish_rest(run, "heal")

    assert run.player.hp == 60


def test_map_locks_future_layers_and_has_single_boss() -> None:
    run = create_run_state("profile-test", "sword", seed=37)
    first = next(node for node in run.map.nodes if node.layer == 1)
    future = next(node for node in run.map.nodes if node.layer == 2)

    assert first.available is True
    assert future.available is False
    boss_nodes = [node for node in run.map.nodes if node.layer == 9]
    assert len(boss_nodes) == 1
    assert boss_nodes[0].kind == "boss"
