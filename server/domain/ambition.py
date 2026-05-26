"""
领域层：本局执念目录与抽取逻辑

执念回答“这一局追什么结果”，只在当局生效。
"""

from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class Ambition:
    id: str
    title: str
    summary: str
    target: int
    progress_label: str
    reward_hint: str

    def to_offer(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "target": self.target,
            "progress_label": self.progress_label,
            "reward_hint": self.reward_hint,
        }


AMBITION_CATALOG: list[Ambition] = [
    Ambition(
        id="survive_foundation",
        title="苟到筑基",
        summary="先活过新手劫，再谈逆天改命。",
        target=1,
        progress_label="抵达筑基",
        reward_hint="达成后提高盖棺定论评分，并奖励天道点。",
    ),
    Ambition(
        id="taunt_heaven",
        title="嘴硬十回合",
        summary="天道越看不惯你，你越要把话说满。",
        target=3,
        progress_label="自由对线",
        reward_hint="每次直谏天道都会推进嘴硬榜候选分。",
    ),
    Ambition(
        id="beautiful_death",
        title="死得漂亮",
        summary="修仙可以失败，但死法必须上桌。",
        target=1,
        progress_label="高戏剧死亡",
        reward_hint="死亡时按天谴、境界和事件稀有度冲击暴毙榜。",
    ),
    Ambition(
        id="borrowed_fate_comeback",
        title="借命翻盘",
        summary="至少从一次高风险裁决里活着走出来。",
        target=1,
        progress_label="赌命存活",
        reward_hint="高风险事件存活后提高赌命评分与结算倍率。",
    ),
    Ambition(
        id="clean_merit",
        title="功德圆满",
        summary="少作孽，少嘴硬，拿一条干净仙路给天道看。",
        target=1,
        progress_label="低天谴进阶",
        reward_hint="低天谴突破时提高稳健评分。",
    ),
    Ambition(
        id="pollute_karma",
        title="污染因果",
        summary="就算倒下，也要给后来者留一点小惊喜。",
        target=1,
        progress_label="留下遗毒",
        reward_hint="死亡或结算后可冲击因果污染榜。",
    ),
]


def get_catalog() -> list[Ambition]:
    return AMBITION_CATALOG[:]


def draw_ambition_offers(count: int = 3) -> list[Ambition]:
    count = max(1, min(count, len(AMBITION_CATALOG)))
    return random.sample(AMBITION_CATALOG, count)


def find_ambition(ambition_id: str) -> Ambition | None:
    for ambition in AMBITION_CATALOG:
        if ambition.id == ambition_id:
            return ambition
    return None
