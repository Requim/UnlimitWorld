"""初始权威局面构造。"""

from __future__ import annotations

from uuid import uuid4

from server.domain.roguelike.catalog import get_archetype
from server.domain.roguelike.map import generate_map
from server.domain.roguelike.models import CardInstance, RunState


def create_run_state(
    profile_id: str,
    archetype: str,
    *,
    seed: int,
    causal_epitaphs: list[str] | None = None,
) -> RunState:
    """创建 map 阶段的权威局面；固定种子仅供服务端与规则测试，非法流派抛 KeyError。"""
    starter = get_archetype(archetype).starter_card_id
    card_ids = ["flying_sword"] * 4 + ["guard"] * 4 + ["focus", starter]
    deck = [CardInstance(uid=uuid4().hex, card_id=card_id) for card_id in card_ids]
    return RunState(
        run_id=uuid4().hex,
        profile_id=profile_id,
        archetype=archetype,
        deck=deck,
        map=generate_map(),
        rng_seed=seed,
        causal_epitaphs=list(causal_epitaphs or []),
    )
