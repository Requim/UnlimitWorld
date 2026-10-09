"""初始权威局面构造。"""

from __future__ import annotations

from uuid import uuid4

from server.domain.roguelike.catalog import get_archetype
from server.domain.roguelike.map import generate_map
from server.domain.roguelike.models import CardInstance, RunMode, RunState
from server.domain.roguelike.myth import (
    STORY_ID,
    STORY_VERSION,
    create_myth_map,
    get_myth_deck_ids,
)


def create_run_state(
    profile_id: str,
    archetype: str,
    *,
    seed: int,
    mode: RunMode = "classic",
    causal_epitaphs: list[str] | None = None,
) -> RunState:
    """创建指定模式的权威局面；固定种子仅供服务端与规则测试，非法参数抛 KeyError。"""
    get_archetype(archetype)
    card_ids = _starter_deck(archetype, mode)
    deck = [CardInstance(uid=uuid4().hex, card_id=card_id) for card_id in card_ids]
    return RunState(
        run_id=uuid4().hex,
        profile_id=profile_id,
        archetype=archetype,
        mode=mode,
        phase="event" if mode == "myth_bifang" else "map",
        layer=1 if mode == "myth_bifang" else 0,
        deck=deck,
        map=create_myth_map() if mode == "myth_bifang" else generate_map(),
        story_id=STORY_ID if mode == "myth_bifang" else None,
        story_version=STORY_VERSION if mode == "myth_bifang" else None,
        rng_seed=seed,
        causal_epitaphs=list(causal_epitaphs or []),
    )


def _starter_deck(archetype: str, mode: RunMode) -> list[str]:
    if mode == "myth_bifang":
        return get_myth_deck_ids(archetype)
    starter = get_archetype(archetype).starter_card_id
    return ["flying_sword"] * 4 + ["guard"] * 4 + ["focus", starter]
