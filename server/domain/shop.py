"""
领域层：天道虚无黑市 — 商品定义与购买逻辑

局外系统，使用 REST API。道具效果在 GameEngine tick 中消费。
"""

from dataclasses import dataclass, field


@dataclass
class ShopItem:
    id: str
    name: str
    cost: int               # 天道点价格
    effect: str             # karma_shield | deafness_protocol | sin_reset
    value: int = 1          # 效果数值
    desc: str = ""
    icon: str = ""


# ── 黑市商品目录 ──

SHOP_CATALOG: list[ShopItem] = [
    ShopItem(
        id="karma_shield",
        name="因果遮蔽卡",
        cost=50,
        effect="karma_shield",
        value=1,
        desc="死亡时自动触发，强行逆转因果。宗门大能撕裂时空将你捞回！",
        icon="shield",
    ),
    ShopItem(
        id="deafness_protocol",
        name="天道失聪协议",
        cost=30,
        effect="deafness_protocol",
        value=1,
        desc="天道对你的骚话选择性失聪，当局气运+10。持续一整局。",
        icon="ear",
    ),
    ShopItem(
        id="sin_wash",
        name="功德洗白券",
        cost=80,
        effect="sin_reset",
        value=0,
        desc="天谴值立即清零。洗心革面，重新做人。",
        icon="wash",
    ),
]


def get_catalog() -> list[dict]:
    """返回商品列表（可 JSON 序列化）"""
    return [
        {
            "id": item.id,
            "name": item.name,
            "cost": item.cost,
            "effect": item.effect,
            "value": item.value,
            "desc": item.desc,
            "icon": item.icon,
        }
        for item in SHOP_CATALOG
    ]


def find_item(item_id: str) -> ShopItem | None:
    for item in SHOP_CATALOG:
        if item.id == item_id:
            return item
    return None
