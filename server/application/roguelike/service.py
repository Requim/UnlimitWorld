"""M5 卡牌肉鸽用例编排。"""

from __future__ import annotations

import json
import secrets

from server.application.roguelike.factory import create_run_state
from server.application.roguelike.ports import RunRepository
from server.application.roguelike.views import build_run_view
from server.domain.roguelike import combat, map as run_map, nodes
from server.domain.roguelike.catalog import ENEMIES
from server.domain.roguelike.errors import InvalidAction
from server.domain.roguelike.models import (
    ActionData,
    BuyAction,
    ChooseEventAction,
    ChooseNodeAction,
    ChooseRewardAction,
    CreateRunResponse,
    EndTurnAction,
    GameEvent,
    HistoryEntry,
    LeaveShopAction,
    PlayCardAction,
    RemoveCardAction,
    RestAction,
    RunResponse,
    RunState,
    SkipRewardAction,
    TauntAction,
    UpgradeCardAction,
)
from server.domain.roguelike.random_source import randbelow


class RoguelikeService:
    """协调领域规则与 SQLite 原子边界。"""

    def __init__(self, repository: RunRepository):
        self._repository = repository

    def create_run(self, archetype: str, access_token: str | None) -> CreateRunResponse:
        """创建匿名权威局面；复用有效 Bearer 档案，错误凭证抛 Unauthorized。"""
        profile_id, token = self._repository.prepare_profile(access_token)
        epitaphs = self._repository.list_epitaphs(profile_id)
        run = create_run_state(
            profile_id,
            archetype,
            seed=secrets.randbits(63),
            causal_epitaphs=epitaphs,
        )
        self._repository.insert_run(run)
        return CreateRunResponse(run=build_run_view(run), events=[], access_token=token)

    def get_run(self, run_id: str, access_token: str) -> RunResponse:
        """读取凭证所属局面；无状态修改，错误凭证或局面由仓储抛错。"""
        run = self._repository.get_run(run_id, access_token)
        return RunResponse(run=build_run_view(run), events=[])

    def perform_action(
        self, run_id: str, access_token: str, action: ActionData
    ) -> RunResponse:
        """在单个 SQLite 事务中执行类型化动作；非法、冲突或未授权时不落盘。"""
        payload = _canonical_payload(action.model_dump(mode="json"))
        return self._repository.transact_action(
            run_id,
            access_token,
            action.action_id,
            action.expected_revision,
            payload,
            lambda run: self._apply_action(run, action),
        )

    def _apply_action(self, run: RunState, action: ActionData) -> list[GameEvent]:
        handlers = {
            "choose_node": self._choose_node,
            "play_card": self._play_card,
            "end_turn": self._end_turn,
            "taunt": self._taunt,
            "choose_reward": self._choose_reward,
            "skip_reward": self._skip_reward,
            "choose_event": self._choose_event,
            "buy": self._buy,
            "remove_card": self._remove_card,
            "rest": self._rest,
            "upgrade_card": self._upgrade_card,
            "leave_shop": self._leave_shop,
        }
        events = handlers[action.kind](run, action)
        run.history.append(
            HistoryEntry(revision=run.revision + 1, kind=action.kind, text=events[-1].text if events else action.kind)
        )
        run.history = run.history[-50:]
        return events

    def _choose_node(self, run: RunState, action: ChooseNodeAction) -> list[GameEvent]:
        node = run_map.choose_node(run, action.node_id)
        if node.kind in {"combat", "elite", "boss"}:
            return combat.start_combat(run, self._enemy_for_node(run, node.kind))
        if node.kind == "event":
            nodes.open_event(run)
            return [GameEvent(kind="event_start", text="一桩不太正经的奇遇拦住了去路")]
        if node.kind == "shop":
            nodes.open_shop(run)
            return [GameEvent(kind="shop_start", text="黑市开门，概不赊账")]
        run.phase = "rest"
        return [GameEvent(kind="rest_start", text="抵达休整点")]

    def _enemy_for_node(self, run: RunState, kind: str) -> str:
        if kind == "boss":
            return "heaven_judge"
        if kind == "elite":
            return "heaven_tax_collector"
        normal = [enemy.id for enemy in ENEMIES if enemy.rank == "normal"]
        return normal[randbelow(run, len(normal))]

    def _play_card(self, run: RunState, action: PlayCardAction) -> list[GameEvent]:
        events = combat.play_card(run, action.card_uid, action.target_id)
        return self._settle_battle(run, events)

    def _end_turn(self, run: RunState, action: EndTurnAction) -> list[GameEvent]:
        return self._settle_battle(run, combat.end_turn(run))

    def _taunt(self, run: RunState, action: TauntAction) -> list[GameEvent]:
        return combat.taunt(run)

    def _settle_battle(self, run: RunState, events: list[GameEvent]) -> list[GameEvent]:
        if run.phase != "battle_won":
            return events
        current = next(node for node in run.map.nodes if node.id == run.map.current_node_id)
        if current.kind == "boss":
            run_map.complete_current_node(run)
            run.phase = "completed"
            run.epitaph = "九层天关尽破，监天判官的朱笔改写成了欠条。"
            events.append(GameEvent(kind="completed", text=run.epitaph))
            return events
        source = "elite" if current.kind == "elite" else "normal"
        nodes.generate_reward(run, source)
        events.append(GameEvent(kind="reward_ready", text="战利品已经摆好"))
        return events

    def _choose_reward(self, run: RunState, action: ChooseRewardAction) -> list[GameEvent]:
        return nodes.choose_reward(run, action.option_index)

    def _skip_reward(self, run: RunState, action: SkipRewardAction) -> list[GameEvent]:
        return nodes.skip_reward(run)

    def _choose_event(self, run: RunState, action: ChooseEventAction) -> list[GameEvent]:
        return nodes.choose_event(run, action.choice_id)

    def _buy(self, run: RunState, action: BuyAction) -> list[GameEvent]:
        return nodes.buy_item(run, action.item_id)

    def _remove_card(self, run: RunState, action: RemoveCardAction) -> list[GameEvent]:
        return nodes.remove_card(run, action.card_uid)

    def _rest(self, run: RunState, action: RestAction) -> list[GameEvent]:
        return nodes.finish_rest(run, action.mode)

    def _upgrade_card(self, run: RunState, action: UpgradeCardAction) -> list[GameEvent]:
        if run.phase != "rest_upgrade":
            raise InvalidAction("当前没有卡牌升级机会")
        return nodes.upgrade_card(run, action.card_uid)

    def _leave_shop(self, run: RunState, action: LeaveShopAction) -> list[GameEvent]:
        return nodes.leave_shop(run)


def _canonical_payload(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
