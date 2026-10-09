"""内部权威局面到前端只读视图的转换。"""

from __future__ import annotations

from server.domain.roguelike.models import CombatView, RunState, RunView, TauntPreview
from server.domain.roguelike.myth import build_story_view


def build_run_view(run: RunState) -> RunView:
    """构建不暴露随机种子与牌堆顺序的公共视图；无副作用。"""
    combat = _build_combat_view(run)
    return RunView(
        run_id=run.run_id,
        revision=run.revision,
        archetype=run.archetype,
        mode=run.mode,
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
        story=build_story_view(run),
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
        taunt_preview=_build_taunt_preview(run),
        sword_intent=combat.sword_intent,
        lightning_redirect=combat.lightning_redirect,
        thunder_count=run.player.wrath // 30,
    )


def _build_taunt_preview(run: RunState) -> TauntPreview:
    combat = run.combat
    wrath_change = 0 if "advice_bell" in run.relics else 8
    text = f"获得 1 灵力，天谴 +{wrath_change}；敌人下次攻击每段 +2。"
    return TauntPreview(
        available=bool(combat and not combat.taunt_used),
        energy_gain=1,
        wrath_change=wrath_change,
        next_attack_bonus=2,
        text=text,
    )
