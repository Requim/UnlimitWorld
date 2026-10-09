from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from server.interface.roguelike_app import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_run(client: TestClient, archetype: str = "sword") -> dict[str, Any]:
    response = client.post("/api/v2/runs", json={"archetype": archetype})
    assert response.status_code == 201, response.text
    return response.json()


def create_myth_run(client: TestClient, archetype: str = "sword") -> dict[str, Any]:
    response = client.post(
        "/api/v2/runs",
        json={"archetype": archetype, "mode": "myth_bifang"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def action(
    client: TestClient,
    run_id: str,
    token: str,
    revision: int,
    action_id: str,
    kind: str,
    **data: Any,
):
    payload = {
        "action_id": action_id,
        "expected_revision": revision,
        "kind": kind,
        **data,
    }
    return client.post(
        f"/api/v2/runs/{run_id}/actions", json=payload, headers=auth(token)
    )


def test_health_catalog_and_openapi_have_explicit_models(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "m5.sqlite3")) as client:
        assert client.get("/health").json() == {"status": "ok"}
        catalog = client.get("/api/v2/catalog").json()
        schema = client.get("/openapi.json").json()

    assert len(catalog["cards"]) == 18
    assert len(catalog["relics"]) == 6
    assert "RunView" in schema["components"]["schemas"]
    assert "ActionRequest" in schema["components"]["schemas"]
    combat_fields = schema["components"]["schemas"]["CombatView"]["properties"]
    intent_fields = schema["components"]["schemas"]["EnemyIntent"]["properties"]
    event_fields = schema["components"]["schemas"]["GameEvent"]["properties"]
    assert "taunt_preview" in combat_fields
    assert "wrath_change" in intent_fields
    assert {"source", "card_id", "visual", "absorbed", "state_after"} <= set(event_fields)


def test_create_mode_defaults_classic_and_rejects_unknown(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "mode.sqlite3")) as client:
        classic = create_run(client)
        invalid = client.post(
            "/api/v2/runs",
            json={"archetype": "sword", "mode": "unknown"},
        )

    assert classic["run"]["mode"] == "classic"
    assert classic["run"]["story"] is None
    assert invalid.status_code == 422


@pytest.mark.parametrize(
    ("choice_id", "expected"),
    [
        ("borrow_fire", (16, 3, 0, 0, 3)),
        ("seal_evidence", (0, 0, 10, 6, 3)),
        ("destroy_scroll", (0, 0, 0, 0, 4)),
    ],
)
def test_myth_api_accepts_each_story_choice(
    tmp_path: Path,
    choice_id: str,
    expected: tuple[int, int, int, int, int],
) -> None:
    with TestClient(create_app(tmp_path / f"{choice_id}.sqlite3")) as client:
        created = create_myth_run(client)
        run = created["run"]
        response = action(
            client,
            run["run_id"],
            created["access_token"],
            0,
            f"choose-{choice_id}",
            "choose_event",
            choice_id=choice_id,
        )

    assert response.status_code == 200
    selected = response.json()["run"]
    combat = selected["combat"]
    actual = (
        selected["player"]["wrath"],
        combat["enemy"]["burn"],
        selected["player"]["block"],
        combat["enemy"]["block"],
        combat["energy"],
    )
    assert actual == expected
    assert selected["story"]["selected_choice"] == choice_id


def test_myth_choice_retry_conflicts_and_invalid_actions_are_atomic(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "atomic.sqlite3")) as client:
        created = create_myth_run(client)
        run = created["run"]
        common = (client, run["run_id"], created["access_token"], 0, "story-1")
        first = action(*common, "choose_event", choice_id="borrow_fire")
        duplicate = action(*common, "choose_event", choice_id="borrow_fire")
        changed = action(*common, "choose_event", choice_id="seal_evidence")
        stale = action(
            client, run["run_id"], created["access_token"], 0, "story-stale",
            "choose_event", choice_id="borrow_fire",
        )
        before = client.get(
            f"/api/v2/runs/{run['run_id']}", headers=auth(created["access_token"])
        ).json()
        repeated = action(
            client, run["run_id"], created["access_token"], 1, "story-repeat",
            "choose_event", choice_id="borrow_fire",
        )
        after = client.get(
            f"/api/v2/runs/{run['run_id']}", headers=auth(created["access_token"])
        ).json()

    assert first.status_code == duplicate.status_code == 200
    assert duplicate.json() == first.json()
    assert changed.status_code == stale.status_code == 409
    assert repeated.status_code == 422
    assert after == before


def test_invalid_myth_choice_does_not_mutate_story(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        created = create_myth_run(client)
        run = created["run"]
        response = action(
            client, run["run_id"], created["access_token"], 0, "invalid-story",
            "choose_event", choice_id="missing",
        )
        snapshot = client.get(
            f"/api/v2/runs/{run['run_id']}", headers=auth(created["access_token"])
        ).json()["run"]

    assert response.status_code == 422
    assert snapshot == run


def test_myth_story_and_choice_survive_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "restart-myth.sqlite3"
    with TestClient(create_app(db_path)) as client:
        created = create_myth_run(client, "fire")
        run = created["run"]
        chosen = action(
            client, run["run_id"], created["access_token"], 0, "persist-story",
            "choose_event", choice_id="seal_evidence",
        ).json()["run"]

    with TestClient(create_app(db_path)) as restarted:
        restored = restarted.get(
            f"/api/v2/runs/{run['run_id']}", headers=auth(created["access_token"])
        ).json()["run"]

    assert restored == chosen
    assert restored["story"]["selected_choice"] == "seal_evidence"


def test_legacy_state_without_mode_or_story_defaults_classic(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    with TestClient(create_app(db_path)) as client:
        created = create_run(client)
    _strip_new_state_fields(db_path, created["run"]["run_id"])

    with TestClient(create_app(db_path)) as restarted:
        restored = restarted.get(
            f"/api/v2/runs/{created['run']['run_id']}",
            headers=auth(created["access_token"]),
        )

    assert restored.status_code == 200
    assert restored.json()["run"]["mode"] == "classic"
    assert restored.json()["run"]["story"] is None


def _strip_new_state_fields(db_path: Path, run_id: str) -> None:
    with sqlite3.connect(db_path) as connection:
        raw = connection.execute(
            "SELECT state_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        state = json.loads(raw)
        for field in ("mode", "story_id", "story_version", "story_selected_choice"):
            state.pop(field, None)
        connection.execute(
            "UPDATE runs SET state_json = ? WHERE run_id = ?",
            (json.dumps(state, ensure_ascii=False), run_id),
        )


def test_combat_payload_exposes_intent_and_taunt_preview(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "m5.sqlite3")) as client:
        created = create_run(client)
        run = created["run"]
        node = next(item for item in run["map"]["nodes"] if item["available"])
        response = action(
            client,
            run["run_id"],
            created["access_token"],
            run["revision"],
            "choose-first",
            "choose_node",
            node_id=node["id"],
        )

    combat = response.json()["run"]["combat"]
    assert combat["taunt_preview"] == {
        "available": True,
        "energy_gain": 1,
        "wrath_change": 8,
        "next_attack_bonus": 2,
        "text": "获得 1 灵力，天谴 +8；敌人下次攻击每段 +2。",
    }
    assert set(combat["enemy"]["intent"]) >= {"value", "hits", "wrath_change", "text"}


def test_profile_token_scopes_runs_and_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "m5.sqlite3"
    with TestClient(create_app(db_path)) as client:
        created = create_run(client)
        other = create_run(client, "fire")

    with TestClient(create_app(db_path)) as restarted:
        own = restarted.get(
            f"/api/v2/runs/{created['run']['run_id']}",
            headers=auth(created["access_token"]),
        )
        forbidden = restarted.get(
            f"/api/v2/runs/{created['run']['run_id']}",
            headers=auth(other["access_token"]),
        )
        sibling = restarted.post(
            "/api/v2/runs",
            json={"archetype": "talisman"},
            headers=auth(created["access_token"]),
        )

    assert own.status_code == 200
    assert forbidden.status_code == 401
    assert sibling.status_code == 201
    assert sibling.json()["access_token"] == created["access_token"]


def test_duplicate_conflict_and_illegal_action_are_atomic(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "m5.sqlite3")) as client:
        created = create_run(client)
        run = created["run"]
        token = created["access_token"]
        node = next(item for item in run["map"]["nodes"] if item["available"])
        first = action(client, run["run_id"], token, 0, "same", "choose_node", node_id=node["id"])
        duplicate = action(client, run["run_id"], token, 0, "same", "choose_node", node_id=node["id"])
        smuggled = action(client, run["run_id"], token, 0, "same", "choose_node", node_id="other")
        stale = action(client, run["run_id"], token, 0, "stale", "end_turn")
        before = client.get(f"/api/v2/runs/{run['run_id']}", headers=auth(token)).json()
        illegal = action(
            client,
            run["run_id"],
            token,
            before["run"]["revision"],
            "illegal",
            "choose_node",
            node_id=node["id"],
        )
        after = client.get(f"/api/v2/runs/{run['run_id']}", headers=auth(token)).json()

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()
    assert smuggled.status_code == 409
    assert stale.status_code == 409
    assert illegal.status_code == 422
    assert after == before


def test_two_concurrent_actions_only_advance_one_revision(tmp_path: Path) -> None:
    db_path = tmp_path / "m5.sqlite3"
    with TestClient(create_app(db_path)) as client:
        created = create_run(client)
        run = created["run"]
        token = created["access_token"]
        nodes = [item for item in run["map"]["nodes"] if item["available"]]

    def choose(index: int) -> int:
        with TestClient(create_app(db_path)) as worker:
            response = action(
                worker,
                run["run_id"],
                token,
                0,
                f"parallel-{index}",
                "choose_node",
                node_id=nodes[index]["id"],
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(choose, (0, 1)))

    assert statuses == [200, 409]


def test_unicode_action_retry_and_changed_payload_preserve_snapshot(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "unicode.sqlite3")) as client:
        created = create_run(client)
        run_id = created["run"]["run_id"]
        token = created["access_token"]
        nodes = [node for node in created["run"]["map"]["nodes"] if node["available"]]
        first = action(client, run_id, token, 0, "动作一", "choose_node", node_id=nodes[0]["id"])
        before = client.get(f"/api/v2/runs/{run_id}", headers=auth(token))
        duplicate = action(client, run_id, token, 0, "动作一", "choose_node", node_id=nodes[0]["id"])
        changed = action(client, run_id, token, 0, "动作一", "choose_node", node_id=nodes[1]["id"])
        snapshot = client.get(f"/api/v2/runs/{run_id}", headers=auth(token))

    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json() == first.json()
    assert changed.status_code == 409
    assert snapshot.json() == before.json()
    assert snapshot.json()["run"] == first.json()["run"]


def play_combat(client: TestClient, run: dict[str, Any], token: str, counter: list[int]):
    catalog = {card["id"]: card for card in client.get("/api/v2/catalog").json()["cards"]}
    while run["phase"] == "combat":
        combat = run["combat"]
        progressed = False
        for card in list(combat["hand"]):
            definition = catalog[card["card_id"]]
            cost = definition["upgraded_cost"] if card["upgraded"] else definition["cost"]
            if cost > combat["energy"]:
                continue
            data = {"card_uid": card["uid"]}
            if definition["target"] == "enemy":
                data["target_id"] = combat["enemy"]["id"]
            counter[0] += 1
            response = action(
                client, run["run_id"], token, run["revision"], f"a-{counter[0]}", "play_card", **data
            )
            assert response.status_code == 200, response.text
            run = response.json()["run"]
            progressed = True
            break
        if progressed or run["phase"] != "combat":
            continue
        if not combat["taunt_used"]:
            counter[0] += 1
            response = action(
                client, run["run_id"], token, run["revision"], f"a-{counter[0]}", "taunt"
            )
        else:
            counter[0] += 1
            response = action(
                client, run["run_id"], token, run["revision"], f"a-{counter[0]}", "end_turn"
            )
        assert response.status_code == 200, response.text
        run = response.json()["run"]
    return run


def advance_noncombat(client: TestClient, run: dict[str, Any], token: str, counter: list[int]):
    counter[0] += 1
    common = (client, run["run_id"], token, run["revision"], f"a-{counter[0]}")
    if run["phase"] == "map":
        node = next(item for item in run["map"]["nodes"] if item["available"])
        response = action(*common, "choose_node", node_id=node["id"])
    elif run["phase"] == "reward":
        response = action(*common, "choose_reward", option_index=0)
    elif run["phase"] == "event":
        response = action(*common, "choose_event", choice_id=run["choices"][0]["id"])
    elif run["phase"] == "shop":
        response = action(*common, "leave_shop")
    elif run["phase"] == "rest":
        response = action(*common, "rest", mode="heal")
    else:
        raise AssertionError(f"unexpected phase: {run['phase']}")
    assert response.status_code == 200, response.text
    return response.json()["run"]


def _open_followup_karma_event(
    client: TestClient, token: str, counter: list[int]
) -> dict[str, Any]:
    response = client.post(
        "/api/v2/runs",
        json={"archetype": "sword"},
        headers=auth(token),
    )
    run = response.json()["run"]
    run = advance_noncombat(client, run, token, counter)
    run = play_combat(client, run, token, counter)
    run = advance_noncombat(client, run, token, counter)
    return advance_noncombat(client, run, token, counter)


def test_full_normal_action_path_wins_and_reward_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "m5.sqlite3"
    counter = [0]
    with TestClient(create_app(db_path)) as client:
        created = create_run(client, "sword")
        run = created["run"]
        token = created["access_token"]
        reward_snapshot = None
        for _ in range(500):
            if run["phase"] in {"completed", "game_over"}:
                break
            run = (
                play_combat(client, run, token, counter)
                if run["phase"] == "combat"
                else advance_noncombat(client, run, token, counter)
            )
            if run["phase"] == "reward" and reward_snapshot is None:
                reward_snapshot = run["reward"]
                break
        assert reward_snapshot is not None

    with TestClient(create_app(db_path)) as restarted:
        restored = restarted.get(f"/api/v2/runs/{run['run_id']}", headers=auth(token)).json()["run"]
        assert restored["reward"] == reward_snapshot
        run = restored
        for _ in range(800):
            if run["phase"] in {"completed", "game_over"}:
                break
            run = (
                play_combat(restarted, run, token, counter)
                if run["phase"] == "combat"
                else advance_noncombat(restarted, run, token, counter)
            )

    assert run["phase"] == "completed"
    assert run["layer"] == 9
    assert run["epitaph"]

    with TestClient(create_app(db_path)) as client:
        next_run = _open_followup_karma_event(client, token, counter)

    assert next_run["phase"] == "event"
    karma = next(choice for choice in next_run["choices"] if choice["id"] == "karma")
    assert run["epitaph"] in karma["description"]
    assert "获得 25 灵石" in karma["description"]
    assert "天谴 +5" in karma["description"]
