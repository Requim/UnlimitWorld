"""
领域层：命格签目录与抽取逻辑

命格签属于局内开局修正，不做账号持久化。
"""

from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class DestinySign:
    id: str
    title: str
    summary: str
    initial_luck: int = 0
    initial_foundation: int = 0
    initial_sin: int = 0
    prd_step_delta: int = 0
    custom_heaven_points_bonus: int = 0
    custom_sin_bonus: int = 0
    heaven_points_multiplier: float = 1.0

    def to_offer(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
        }

    def to_mods(self) -> dict:
        return {
            "initial_luck": self.initial_luck,
            "initial_foundation": self.initial_foundation,
            "initial_sin": self.initial_sin,
            "prd_step_delta": self.prd_step_delta,
            "custom_heaven_points_bonus": self.custom_heaven_points_bonus,
            "custom_sin_bonus": self.custom_sin_bonus,
            "heaven_points_multiplier": self.heaven_points_multiplier,
        }


DESTINY_SIGN_CATALOG: list[DestinySign] = [
    DestinySign(
        id="sharp_tongue",
        title="嘴硬成道",
        summary="嘴越硬，天道越想看你能扛到哪一步。",
        initial_luck=5,
        custom_heaven_points_bonus=3,
        custom_sin_bonus=5,
    ),
    DestinySign(
        id="secluded_meditation",
        title="清修避世",
        summary="少沾因果，少惹天道，稳扎稳打地活得更久。",
        initial_foundation=8,
        prd_step_delta=-3,
        heaven_points_multiplier=0.9,
    ),
    DestinySign(
        id="borrowed_fate_gambler",
        title="借命赌徒",
        summary="拿根基换天命，赌的就是一口翻盘的气。",
        initial_luck=8,
        initial_foundation=-8,
        prd_step_delta=2,
        heaven_points_multiplier=1.5,
    ),
    DestinySign(
        id="fortune_and_disaster",
        title="福祸同炉",
        summary="祸从福起，福从祸生，这一局注定不太安生。",
        initial_foundation=6,
        initial_sin=10,
        heaven_points_multiplier=1.3,
    ),
]


def get_catalog() -> list[DestinySign]:
    return DESTINY_SIGN_CATALOG[:]


def draw_destiny_offers(count: int = 3) -> list[DestinySign]:
    count = max(1, min(count, len(DESTINY_SIGN_CATALOG)))
    return random.sample(DESTINY_SIGN_CATALOG, count)


def find_destiny_sign(sign_id: str) -> DestinySign | None:
    for sign in DESTINY_SIGN_CATALOG:
        if sign.id == sign_id:
            return sign
    return None
