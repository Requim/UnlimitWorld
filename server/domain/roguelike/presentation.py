"""战斗表现事件的公共快照与稳定语义元数据。"""

from __future__ import annotations

from .models import (
    CombatPresentationSnapshot,
    EnemyPresentationState,
    EventSource,
    EventVisual,
    GameEvent,
    PlayerPresentationState,
    RunState,
)


def combat_snapshot(run: RunState) -> CombatPresentationSnapshot | None:
    """读取当前公开战斗属性；非战斗局面返回 None，不暴露随机源或隐藏牌序。"""
    combat = run.combat
    if combat is None:
        return None
    return CombatPresentationSnapshot(
        player=PlayerPresentationState(
            hp=run.player.hp,
            block=run.player.block,
            wrath=run.player.wrath,
            reflect=run.player.reflect,
        ),
        enemy=EnemyPresentationState(
            hp=combat.enemy.hp,
            block=combat.enemy.block,
            burn=combat.enemy.burn,
            weak=combat.enemy.weak,
        ),
        turn=combat.turn,
        energy=combat.energy,
    )


def battle_event(
    run: RunState,
    kind: str,
    text: str,
    *,
    amount: int | None = None,
    target: str | None = None,
    source: EventSource = "system",
    card_id: str | None = None,
    visual: EventVisual = "idle",
    absorbed: int | None = None,
) -> GameEvent:
    """构建带当时快照的表现事件；无额外状态修改，调用方须先完成对应权威变更。"""
    return GameEvent(
        kind=kind,
        text=text,
        amount=amount,
        target=target,
        source=source,
        card_id=card_id,
        visual=visual,
        absorbed=absorbed,
        state_after=combat_snapshot(run),
    )
