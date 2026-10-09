"""内部权威局面到前端只读视图的转换。"""

from __future__ import annotations

from server.domain.roguelike.models import CombatView, RunState, RunView


def build_run_view(run: RunState) -> RunView:
    """构建不暴露随机种子与牌堆顺序的公共视图；无副作用。"""
    combat = _build_combat_view(run)
    return RunView(
        run_id=run.run_id,
        revision=run.revision,
        archetype=run.archetype,
        phase=run.phase,
        layer=run.layer,
        player=run.player,
        deck=run.deck,
        relics=run.relics,
        map=run.map,
        combat=combat,
        reward=run.reward,
        choices=run.choices,
        shop=run.shop,
        history=run.history,
        epitaph=run.epitaph,
    )


def _build_combat_view(run: RunState) -> CombatView | None:
    combat = run.combat
    if combat is None:
        return None
    return CombatView(
        turn=combat.turn,
        energy=combat.energy,
        max_energy=combat.max_energy,
        hand=combat.hand,
        draw_count=len(combat.draw_pile),
        discard_count=len(combat.discard_pile),
        exhaust_count=len(combat.exhaust_pile),
        enemy=combat.enemy,
        taunt_used=combat.taunt_used,
        sword_intent=combat.sword_intent,
        lightning_redirect=combat.lightning_redirect,
        thunder_count=run.player.wrath // 30,
    )
