from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.application.roguelike.factory import create_run_state
from server.domain.roguelike import myth
from server.domain.roguelike.combat import end_turn, play_card, taunt
from server.domain.roguelike.models import CardInstance, EnemyIntent
from server.interface.roguelike_app import create_app


def make_myth(archetype: str = "sword", choice_id: str = "borrow_fire"):
    run = create_run_state(
        "profile-myth",
        archetype,
        seed=41,
        mode="myth_bifang",
    )
    myth.choose_story(run, choice_id)
    assert run.combat is not None
    return run


def put_card_in_hand(run, card_id: str) -> CardInstance:
    assert run.combat is not None
    card = CardInstance(uid=f"myth-{card_id}", card_id=card_id)
    run.combat.hand = [card]
    run.combat.energy = 9
    return card


def test_myth_start_has_story_and_sample_deck(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "myth.sqlite3")) as client:
        response = client.post(
            "/api/v2/runs",
            json={"archetype": "sword", "mode": "myth_bifang"},
        )

    assert response.status_code == 201
    run = response.json()["run"]
    assert run["phase"] == "event"
    assert run["mode"] == "myth_bifang"
    story = run["story"]
    assert (story["id"], story["version"]) == ("bifang_trial", "bifang-v1")
    assert story["title"] == "章莪山灰烬案"
    assert story["body"] == (
        "章莪山无草木而多玉石。天道把山火归罪于毕方；毕方坚持自己只是火灾的预兆，"
        "不是纵火者。为证明清白，它当庭烧毁了指控卷宗，于是天道命修士为仅剩的灰烬作证。"
    )
    assert [choice["id"] for choice in story["choices"]] == [
        "borrow_fire",
        "seal_evidence",
        "destroy_scroll",
    ]
    assert all(choice["consequence"] for choice in story["choices"])
    assert story["selected_choice"] is None
    assert len(run["deck"]) == 10
    assert len(run["map"]["nodes"]) == 1
    assert run["map"]["nodes"][0]["kind"] == "boss"
    assert run["map"]["current_node_id"] == run["map"]["nodes"][0]["id"]


@pytest.mark.parametrize(
    ("archetype", "specials"),
    [
        ("sword", ["charge_sword", "myriad_swords"]),
        ("fire", ["fire_seed", "borrow_fire"]),
        ("talisman", ["demon_mirror", "lightning_talisman"]),
    ],
)
def test_myth_deck_uses_two_archetype_cards(archetype: str, specials: list[str]) -> None:
    run = create_run_state("profile", archetype, seed=43, mode="myth_bifang")
    card_ids = [card.card_id for card in run.deck]

    assert card_ids == ["flying_sword"] * 4 + ["guard"] * 3 + ["focus"] + specials


@pytest.mark.parametrize(
    ("choice_id", "expected"),
    [
        ("borrow_fire", (16, 3, 0, 0, 3, 0)),
        ("seal_evidence", (0, 0, 10, 6, 3, 0)),
        ("destroy_scroll", (0, 0, 0, 0, 4, 2)),
    ],
)
def test_story_choice_applies_exact_starting_modifier(
    choice_id: str, expected: tuple[int, int, int, int, int, int]
) -> None:
    run = make_myth(choice_id=choice_id)
    assert run.combat is not None

    actual = (
        run.player.wrath,
        run.combat.enemy.burn,
        run.player.block,
        run.combat.enemy.block,
        run.combat.energy,
        run.combat.pending_attack_bonus,
    )
    assert actual == expected
    assert run.story_selected_choice == choice_id


def test_destroy_scroll_bonus_survives_defense_until_real_attack() -> None:
    run = make_myth(choice_id="destroy_scroll")
    assert run.combat is not None

    end_turn(run)

    assert run.combat.enemy.block == 8
    assert run.combat.pending_attack_bonus == 2
    assert run.combat.enemy.intent.kind == "burn"
    assert run.combat.enemy.intent.value == 7


def test_burn_attack_adds_wrath_even_when_fully_blocked() -> None:
    run = make_myth(choice_id="borrow_fire")
    assert run.combat is not None
    end_turn(run)
    run.player.block = 99

    events = end_turn(run)

    damage = next(event for event in events if event.kind == "enemy_damage")
    assert damage.amount == 0
    assert run.player.hp == 60
    assert run.player.wrath == 19


def test_bifang_multi_hits_twice_in_order() -> None:
    run = make_myth(choice_id="seal_evidence")
    assert run.combat is not None
    end_turn(run)
    end_turn(run)

    events = end_turn(run)

    damage_events = [event for event in events if event.kind == "enemy_damage"]
    assert [event.amount for event in damage_events] == [5, 5]
    assert run.player.hp == 45


def test_weak_and_taunt_are_reflected_in_bifang_attack_intent() -> None:
    run = make_myth("talisman", "destroy_scroll")
    assert run.combat is not None
    card = put_card_in_hand(run, "silence_talisman")

    play_card(run, card.uid, run.combat.enemy.id)
    taunt(run)
    end_turn(run)

    assert run.combat.enemy.intent.kind == "burn"
    assert run.combat.enemy.intent.value == 6
    assert run.combat.enemy.intent.wrath_change == 3
    assert run.combat.pending_attack_bonus == 4


@pytest.mark.parametrize(
    ("choice_id", "epitaph"),
    [
        ("borrow_fire", "借来的火照清旧案，毕方衔灰退回章莪山。"),
        ("seal_evidence", "灰证封存，毕方留下火羽作押。"),
        ("destroy_scroll", "卷宗化灰，毕方笑你比天火更会毁证。"),
    ],
)
def test_myth_victory_uses_choice_specific_epitaph(
    choice_id: str, epitaph: str
) -> None:
    run = make_myth(choice_id=choice_id)
    assert run.combat is not None
    run.combat.enemy.hp = 1
    run.combat.enemy.block = 0
    card = put_card_in_hand(run, "flying_sword")

    events = play_card(run, card.uid, run.combat.enemy.id)
    myth.complete_myth_victory(run, events)

    assert run.phase == "completed"
    assert run.epitaph == epitaph
    assert events[-1].kind == "completed"


def test_myth_defeat_records_bifang_epitaph() -> None:
    run = make_myth()
    assert run.combat is not None
    run.player.hp = 1
    run.combat.enemy.intent_index = 1
    myth.refresh_myth_intent(run)

    events = end_turn(run)

    assert run.phase == "game_over"
    assert run.epitaph == "章莪山火羽落定，毕方把你的嘴硬烧成了新证词。"
    assert events[-1].kind == "defeat"


def test_story_modifier_events_keep_intermediate_snapshots() -> None:
    run = create_run_state("profile", "fire", seed=47, mode="myth_bifang")

    events = myth.choose_story(run, "borrow_fire")

    wrath = next(event for event in events if event.kind == "wrath")
    burn = next(event for event in events if event.kind == "burn")
    assert wrath.state_after.player.wrath == 16
    assert wrath.state_after.enemy.burn == 0
    assert burn.state_after.player.wrath == 16
    assert burn.state_after.enemy.burn == 3


def test_fully_blocked_card_hit_keeps_card_and_absorption_metadata() -> None:
    run = make_myth(choice_id="seal_evidence")
    assert run.combat is not None
    card = put_card_in_hand(run, "flying_sword")

    events = play_card(run, card.uid, run.combat.enemy.id)

    damage = next(event for event in events if event.kind == "damage")
    assert damage.amount == 0
    assert damage.absorbed == 6
    assert damage.card_id == "flying_sword"
    assert damage.source == "player"
    assert damage.visual == "sword"
    assert damage.state_after.enemy.hp == 48
    assert damage.state_after.enemy.block == 0


def test_multi_hit_snapshots_follow_real_damage_order() -> None:
    run = make_myth(choice_id="seal_evidence")
    assert run.combat is not None
    end_turn(run)
    end_turn(run)

    events = end_turn(run)

    hits = [event for event in events if event.kind == "enemy_damage"]
    assert [event.state_after.player.hp for event in hits] == [50, 45]
    assert [event.source for event in hits] == ["enemy", "enemy"]
    assert [event.visual for event in hits] == ["hit", "hit"]


def test_redirected_lightning_has_heaven_metadata_without_card_id() -> None:
    run = make_myth("talisman", "borrow_fire")
    assert run.combat is not None
    run.player.wrath = 30
    card = put_card_in_hand(run, "lightning_talisman")
    redirect = play_card(run, card.uid, run.combat.enemy.id)[0]

    events = end_turn(run)

    thunder = next(event for event in events if event.kind == "thunder")
    assert redirect.card_id == "lightning_talisman"
    assert thunder.source == "heaven"
    assert thunder.visual == "thunder"
    assert thunder.card_id is None
    assert thunder.state_after.enemy.hp == 40


def test_lethal_multi_stops_without_postmortem_hit() -> None:
    run = make_myth()
    assert run.combat is not None
    run.player.hp = 5
    run.combat.enemy.intent = EnemyIntent(
        kind="multi",
        value=5,
        hits=2,
        text="连续 2 次造成 5 点伤害",
    )

    events = end_turn(run)

    assert [event.kind for event in events] == ["enemy_damage", "defeat"]
    assert events[0].state_after.player.hp == 0
    assert events[0].absorbed == 0
