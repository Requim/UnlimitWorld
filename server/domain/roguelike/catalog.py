"""首发卡牌、法宝、敌人与流派目录。"""

from __future__ import annotations

from functools import lru_cache

from .models import (
    ArchetypeDefinition,
    CardDefinition,
    CatalogResponse,
    EnemyDefinition,
    RelicDefinition,
)


def _card(
    id: str,
    name: str,
    archetype: str,
    cost: int,
    target: str,
    description: str,
    upgrade_text: str,
    *,
    upgraded_cost: int | None = None,
    exhaust: bool = False,
) -> CardDefinition:
    return CardDefinition(
        id=id,
        name=name,
        archetype=archetype,
        cost=cost,
        upgraded_cost=cost if upgraded_cost is None else upgraded_cost,
        target=target,
        description=description,
        upgrade_text=upgrade_text,
        exhaust=exhaust,
    )


CARDS = [
    _card("flying_sword", "飞剑", "common", 1, "enemy", "造成 6 点伤害。", "伤害提高至 9。"),
    _card("guard", "护体", "common", 1, "self", "获得 6 点护盾。", "护盾提高至 9。"),
    _card("focus", "凝神", "common", 1, "none", "抽 2 张牌，回复 1 灵力。", "改为抽 3 张牌。"),
    _card("charge_sword", "蓄剑", "sword", 1, "enemy", "造成 4 点伤害，获得 1 剑意。", "造成 6 点伤害，获得 2 剑意。"),
    _card("flurry", "连斩", "sword", 1, "enemy", "连续造成 2 次 3 点伤害。", "每次伤害提高至 4。"),
    _card("sword_draw", "剑引", "sword", 1, "enemy", "造成 5 点伤害，抽 1 张牌。", "造成 7 点伤害并抽 2 张。"),
    _card("myriad_swords", "万剑归宗", "sword", 2, "enemy", "造成 8 点伤害，每点剑意追加 4 点并消耗全部剑意。", "基础 10，每点剑意追加 5。"),
    _card("hidden_edge", "藏锋", "sword", 1, "self", "获得 5 护盾和 1 剑意。", "获得 8 护盾和 2 剑意。"),
    _card("fire_seed", "火种", "fire", 1, "enemy", "造成 4 点伤害，施加 3 层燃烧。", "造成 6 点，施加 4 层燃烧。"),
    _card("fan_flames", "煽风", "fire", 1, "enemy", "施加 4 层燃烧。", "施加 6 层燃烧。"),
    _card("burn_heaven", "焚天", "fire", 2, "enemy", "造成 10 点伤害，天谴每 4 点追加 1 点，天谴 +6。", "基础伤害提高至 14。"),
    _card("borrow_fire", "借火", "fire", 0, "none", "获得 2 灵力，天谴 +10，消耗。", "获得 3 灵力，天谴只 +8。", exhaust=True),
    _card("embers", "余烬", "fire", 1, "self", "获得 7 护盾，天谴 -5。", "获得 10 护盾，天谴 -8。"),
    _card("golden_bell", "金钟符", "talisman", 1, "self", "获得 8 护盾。", "获得 12 护盾。"),
    _card("demon_mirror", "照妖镜", "talisman", 1, "self", "获得 4 护盾与 4 反伤。", "各提高至 6。"),
    _card("silence_talisman", "封口符", "talisman", 1, "enemy", "使敌人虚弱 2 回合。", "虚弱提高至 3 回合。"),
    _card("swift_script", "疾书", "talisman", 0, "none", "抽 2 张牌，消耗。", "改为抽 3 张牌。", exhaust=True),
    _card("lightning_talisman", "引雷符", "talisman", 1, "enemy", "下一次雷罚转移给敌人。", "费用降为 0。", upgraded_cost=0),
]

RELICS = [
    RelicDefinition(id="broken_wood_sword", name="破木剑", description="攻击牌额外造成 2 点伤害。"),
    RelicDefinition(id="ancestral_incense", name="祖传香炉", description="每次施加燃烧时额外施加 1 层。"),
    RelicDefinition(id="heaven_iou", name="天道欠条", description="转移给敌人的雷罚额外造成 2 点伤害。"),
    RelicDefinition(id="ancestor_talisman", name="祖师符", description="每场战斗开始时获得 6 点护盾。"),
    RelicDefinition(id="charred_bone", name="焦骨珠", description="燃烧结算时额外造成 2 点伤害。"),
    RelicDefinition(id="advice_bell", name="听劝铃", description="每场战斗首次挑衅不增加天谴。"),
]

ENEMIES = [
    EnemyDefinition(id="paper_soldier", name="纸兵", rank="normal", max_hp=20, intent_pattern=[("attack", 4), ("defend", 4)], description="纸糊的天兵，刀口却很认真。"),
    EnemyDefinition(id="incense_guest", name="香火客", rank="normal", max_hp=24, intent_pattern=[("burn", 3), ("attack", 5)], description="拿香火当账本的游魂。"),
    EnemyDefinition(id="fallen_monk", name="破戒僧", rank="normal", max_hp=28, intent_pattern=[("attack", 6), ("defend", 5)], description="戒律全破，拳头尚硬。"),
    EnemyDefinition(id="debt_immortal", name="讨债仙", rank="normal", max_hp=32, intent_pattern=[("multi", 3), ("attack", 7)], description="连利息都修成了仙。"),
    EnemyDefinition(id="heaven_tax_collector", name="天税总管", rank="elite", max_hp=40, intent_pattern=[("attack", 7), ("defend", 7), ("multi", 4)], description="专收逆天改命附加税。"),
    EnemyDefinition(id="heaven_judge", name="监天判官", rank="boss", max_hp=55, intent_pattern=[("attack", 8), ("multi", 4), ("defend", 8)], description="九层尽头的朱笔执法者。"),
    EnemyDefinition(id="bifang", name="毕方", rank="boss", max_hp=48, intent_pattern=[("defend", 8), ("burn", 5), ("multi", 5)], description="章莪山衔火旧案的独足神鸟。"),
]

ARCHETYPES = [
    ArchetypeDefinition(id="sword", name="御剑", description="积攒剑意，以万剑归宗爆发。", starter_card_id="charge_sword"),
    ArchetypeDefinition(id="fire", name="业火", description="用燃烧和天谴换取更高输出。", starter_card_id="fire_seed"),
    ArchetypeDefinition(id="talisman", name="符箓", description="依靠护盾、反伤和引雷掌控节奏。", starter_card_id="golden_bell"),
]


@lru_cache(maxsize=1)
def get_catalog() -> CatalogResponse:
    """返回完整只读目录；无入参、无副作用，目录缺失时由模型校验报错。"""
    return CatalogResponse(cards=CARDS, relics=RELICS, enemies=ENEMIES, archetypes=ARCHETYPES)


def get_card(card_id: str) -> CardDefinition:
    """按 ID 返回卡牌定义；找不到时抛出 KeyError。"""
    return next(card for card in CARDS if card.id == card_id)


def get_enemy(enemy_id: str) -> EnemyDefinition:
    """按 ID 返回敌人定义；找不到时抛出 KeyError。"""
    return next(enemy for enemy in ENEMIES if enemy.id == enemy_id)


def get_archetype(archetype_id: str) -> ArchetypeDefinition:
    """按 ID 返回流派定义；找不到时抛出 KeyError。"""
    return next(item for item in ARCHETYPES if item.id == archetype_id)
