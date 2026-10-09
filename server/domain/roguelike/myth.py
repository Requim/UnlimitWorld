"""章莪山毕方样板的独立剧情与关卡内容。"""

from __future__ import annotations

from .errors import InvalidAction
from .models import CombatState, GameEvent, MapNode, RunMap, RunState, StoryChoice, StoryView
from .presentation import battle_event


STORY_ID = "bifang_trial"
STORY_VERSION = "bifang-v1"
STORY_TITLE = "章莪山灰烬案"
STORY_BODY = "玉石山上无草木，毕方衔着旧案灰烬，等你决定这桩天火该如何结案。"
STORY_CHOICES = [
    StoryChoice(
        id="borrow_fire",
        label="借火验案",
        consequence="玩家天谴 +16；毕方初始燃烧 3。",
    ),
    StoryChoice(
        id="seal_evidence",
        label="封存灰证",
        consequence="玩家初始护盾 10；毕方初始护盾 6。",
    ),
    StoryChoice(
        id="destroy_scroll",
        label="毁卷结案",
        consequence="玩家首回合灵力 4；毕方下一次真实攻击每段 +2。",
    ),
]
VICTORY_EPITAPHS = {
    "borrow_fire": "借来的火照清旧案，毕方衔灰退回章莪山。",
    "seal_evidence": "灰证封存，毕方留下火羽作押。",
    "destroy_scroll": "卷宗化灰，毕方笑你比天火更会毁证。",
}
DEFEAT_EPITAPH = "章莪山火羽落定，毕方把你的嘴硬烧成了新证词。"


def get_myth_deck_ids(archetype: str) -> list[str]:
    """返回指定流派的十张毕方样板牌组；非法流派抛 KeyError，无副作用。"""
    archetype_cards = {
        "sword": ["charge_sword", "myriad_swords"],
        "fire": ["fire_seed", "borrow_fire"],
        "talisman": ["demon_mirror", "lightning_talisman"],
    }
    return ["flying_sword"] * 4 + ["guard"] * 3 + ["focus"] + archetype_cards[archetype]


def create_myth_map() -> RunMap:
    """创建单节点毕方 Boss 地图；无入参和外部副作用。"""
    node = MapNode(id="myth-bifang", layer=1, lane=0, kind="boss")
    return RunMap(nodes=[node], current_node_id=node.id)


def build_story_view(run: RunState) -> StoryView | None:
    """从持久化故事标识构建公共展示；经典局返回 None，未知版本抛 ValueError。"""
    if run.story_id is None:
        return None
    if (run.story_id, run.story_version) != (STORY_ID, STORY_VERSION):
        raise ValueError("未知的神话故事版本")
    return StoryView(
        id=STORY_ID,
        version=STORY_VERSION,
        title=STORY_TITLE,
        body=STORY_BODY,
        choices=STORY_CHOICES,
        selected_choice=run.story_selected_choice,
    )


def choose_story(run: RunState, choice_id: str) -> list[GameEvent]:
    """选择毕方剧情并开战；会写入选择和战斗修正，非法选择或阶段抛 InvalidAction。"""
    _validate_story_choice(run, choice_id)
    from .combat import start_combat

    run.story_selected_choice = choice_id
    events = [
        battle_event(
            run,
            "story_choice",
            f"选择了{_choice_label(choice_id)}",
            source="system",
        )
    ]
    events.extend(start_combat(run, "bifang"))
    events.extend(_apply_story_modifier(run, choice_id))
    return events


def _validate_story_choice(run: RunState, choice_id: str) -> None:
    valid_ids = {choice.id for choice in STORY_CHOICES}
    story_matches = (run.story_id, run.story_version) == (STORY_ID, STORY_VERSION)
    if run.mode != "myth_bifang" or run.phase != "event" or not story_matches:
        raise InvalidAction("当前不能选择毕方剧情")
    if run.story_selected_choice is not None or choice_id not in valid_ids:
        raise InvalidAction("毕方剧情选项无效")


def _choice_label(choice_id: str) -> str:
    return next(choice.label for choice in STORY_CHOICES if choice.id == choice_id)


def _apply_story_modifier(run: RunState, choice_id: str) -> list[GameEvent]:
    handlers = {
        "borrow_fire": _apply_borrow_fire,
        "seal_evidence": _apply_seal_evidence,
        "destroy_scroll": _apply_destroy_scroll,
    }
    return handlers[choice_id](run)


def _apply_borrow_fire(run: RunState) -> list[GameEvent]:
    combat = _require_combat(run)
    run.player.wrath += 16
    events = [
        battle_event(
            run,
            "wrath",
            "借火验案：天谴增加 16",
            amount=16,
            target="player",
            source="system",
            visual="thunder",
        )
    ]
    combat.enemy.burn += 3
    events.append(
        battle_event(
            run,
            "burn",
            "毕方带着 3 层燃烧开战",
            amount=3,
            target="bifang",
            source="system",
            visual="fire",
        )
    )
    return events


def _apply_seal_evidence(run: RunState) -> list[GameEvent]:
    combat = _require_combat(run)
    run.player.block += 10
    events = [
        battle_event(
            run,
            "block",
            "封存灰证：获得 10 点护盾",
            amount=10,
            target="player",
            source="system",
            visual="shield",
        )
    ]
    combat.enemy.block += 6
    events.append(
        battle_event(
            run,
            "enemy_block",
            "毕方获得 6 点护盾",
            amount=6,
            target="bifang",
            source="system",
            visual="shield",
        )
    )
    return events


def _apply_destroy_scroll(run: RunState) -> list[GameEvent]:
    combat = _require_combat(run)
    combat.energy = 4
    events = [
        battle_event(
            run,
            "energy",
            "毁卷结案：首回合灵力变为 4",
            amount=1,
            target="player",
            source="system",
        )
    ]
    combat.pending_attack_bonus += 2
    refresh_myth_intent(run)
    events.append(
        battle_event(
            run,
            "enemy_attack_bonus",
            "毕方下一次真实攻击每段 +2",
            amount=2,
            target="bifang",
            source="system",
            visual="hit",
        )
    )
    return events


def refresh_myth_intent(run: RunState) -> None:
    """按当前虚弱与待结算加值刷新毕方预告；非战斗状态抛 InvalidAction。"""
    from .combat import refresh_intent

    refresh_intent(run)


def complete_myth_victory(run: RunState, events: list[GameEvent]) -> None:
    """将已获胜的毕方战斗收束为 completed；会写碑文和地图，阶段非法时抛 InvalidAction。"""
    choice_id = run.story_selected_choice
    if run.mode != "myth_bifang" or run.phase != "battle_won" or choice_id not in VICTORY_EPITAPHS:
        raise InvalidAction("毕方战斗尚未获胜")
    run.phase = "completed"
    run.epitaph = VICTORY_EPITAPHS[choice_id]
    run.map.nodes[0].completed = True
    run.map.current_node_id = None
    events.append(
        battle_event(
            run,
            "completed",
            run.epitaph,
            target="bifang",
            source="system",
            visual="defeat",
        )
    )


def get_defeat_epitaph(run: RunState) -> str | None:
    """返回毕方模式失败碑文；经典模式返回 None，无副作用。"""
    return DEFEAT_EPITAPH if run.mode == "myth_bifang" else None


def _require_combat(run: RunState) -> CombatState:
    if run.combat is None:
        raise InvalidAction("毕方战斗尚未开始")
    return run.combat
