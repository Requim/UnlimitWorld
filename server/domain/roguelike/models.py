"""M5 卡牌肉鸽内部状态与公共协议模型。"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, RootModel


ArchetypeId = Literal["sword", "fire", "talisman"]
RunMode = Literal["classic", "myth_bifang"]
EventSource = Literal["player", "enemy", "heaven", "system"]
EventVisual = Literal["sword", "fire", "shield", "thunder", "hit", "defeat", "idle"]
NodeKind = Literal["combat", "elite", "event", "shop", "rest", "boss"]
RunPhase = Literal[
    "map",
    "combat",
    "battle_won",
    "reward",
    "event",
    "shop",
    "rest",
    "rest_upgrade",
    "completed",
    "game_over",
]


class CardDefinition(BaseModel):
    id: str
    name: str
    archetype: Literal["common", "sword", "fire", "talisman"]
    cost: int
    upgraded_cost: int
    target: Literal["enemy", "self", "none"]
    description: str
    upgrade_text: str
    exhaust: bool = False


class RelicDefinition(BaseModel):
    id: str
    name: str
    description: str


class EnemyDefinition(BaseModel):
    id: str
    name: str
    rank: Literal["normal", "elite", "boss"]
    max_hp: int
    intent_pattern: list[tuple[str, int]]
    description: str


class ArchetypeDefinition(BaseModel):
    id: ArchetypeId
    name: str
    description: str
    starter_card_id: str


class CatalogResponse(BaseModel):
    cards: list[CardDefinition]
    relics: list[RelicDefinition]
    enemies: list[EnemyDefinition]
    archetypes: list[ArchetypeDefinition]


class CardInstance(BaseModel):
    uid: str
    card_id: str
    upgraded: bool = False


class PlayerState(BaseModel):
    hp: int = 60
    max_hp: int = 60
    block: int = 0
    wrath: int = 0
    stones: int = 60
    reflect: int = 0


class EnemyIntent(BaseModel):
    kind: Literal["attack", "defend", "burn", "multi"]
    value: int = Field(description="已计入虚弱和挑衅的每段最终伤害，防御时为护盾值")
    hits: int = Field(default=1, description="该意图的攻击段数")
    wrath_change: int = Field(default=0, description="意图命中且双方存活时造成的天谴变化")
    text: str


class EnemyState(BaseModel):
    id: str
    name: str
    hp: int
    max_hp: int
    block: int = 0
    burn: int = 0
    weak: int = 0
    intent_index: int = 0
    intent: EnemyIntent


class CombatState(BaseModel):
    turn: int = 1
    energy: int = 3
    max_energy: int = 3
    hand: list[CardInstance] = Field(default_factory=list)
    draw_pile: list[CardInstance] = Field(default_factory=list)
    discard_pile: list[CardInstance] = Field(default_factory=list)
    exhaust_pile: list[CardInstance] = Field(default_factory=list)
    enemy: EnemyState
    taunt_used: bool = False
    pending_attack_bonus: int = 0
    sword_intent: int = 0
    lightning_redirect: bool = False


class TauntPreview(BaseModel):
    available: bool
    energy_gain: int = Field(description="提交挑衅后立即获得的灵力")
    wrath_change: int = Field(description="计入法宝后的实际天谴变化")
    next_attack_bonus: int = Field(description="敌人下一次真实攻击的每段伤害加成")
    text: str = Field(description="前端可直接展示的完整效果说明")


class CombatView(BaseModel):
    turn: int
    energy: int
    max_energy: int
    hand: list[CardInstance]
    draw_count: int
    discard_count: int
    exhaust_count: int
    enemy: EnemyState
    taunt_used: bool
    taunt_preview: TauntPreview
    sword_intent: int
    lightning_redirect: bool
    thunder_count: int
    thunder_damage: int = 8


class MapNode(BaseModel):
    id: str
    layer: int
    lane: int
    kind: NodeKind
    links_from: list[str] = Field(default_factory=list)
    available: bool = False
    completed: bool = False


class RunMap(BaseModel):
    nodes: list[MapNode]
    current_node_id: str | None = None


class RewardCard(BaseModel):
    card_id: str
    upgraded: bool = False


class RewardState(BaseModel):
    cards: list[RewardCard]
    stones: int
    source: Literal["normal", "elite"]


class EventChoice(BaseModel):
    id: str
    label: str
    description: str


class StoryChoice(BaseModel):
    id: str
    label: str
    consequence: str


class StoryView(BaseModel):
    id: str
    version: str
    title: str
    body: str
    choices: list[StoryChoice]
    selected_choice: str | None = None


class ShopItem(BaseModel):
    id: str
    kind: Literal["card", "relic"]
    ref_id: str
    price: int
    purchased: bool = False


class ShopState(BaseModel):
    items: list[ShopItem]
    removal_price: int = 45
    removal_used: bool = False


class HistoryEntry(BaseModel):
    revision: int
    kind: str
    text: str


class PlayerPresentationState(BaseModel):
    hp: int
    block: int
    wrath: int
    reflect: int


class EnemyPresentationState(BaseModel):
    hp: int
    block: int
    burn: int
    weak: int


class CombatPresentationSnapshot(BaseModel):
    player: PlayerPresentationState
    enemy: EnemyPresentationState
    turn: int | None = None
    energy: int | None = None


class GameEvent(BaseModel):
    kind: str
    text: str
    amount: int | None = None
    target: str | None = None
    source: EventSource | None = None
    card_id: str | None = None
    visual: EventVisual | None = None
    absorbed: int | None = None
    state_after: CombatPresentationSnapshot | None = None


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    profile_id: str
    revision: int = 0
    archetype: ArchetypeId
    mode: RunMode = "classic"
    phase: RunPhase = "map"
    layer: int = 0
    player: PlayerState = Field(default_factory=PlayerState)
    deck: list[CardInstance]
    relics: list[str] = Field(default_factory=list)
    map: RunMap
    combat: CombatState | None = None
    reward: RewardState | None = None
    choices: list[EventChoice] = Field(default_factory=list)
    shop: ShopState | None = None
    history: list[HistoryEntry] = Field(default_factory=list)
    epitaph: str | None = None
    story_id: str | None = None
    story_version: str | None = None
    story_selected_choice: str | None = None
    rng_seed: int
    rng_counter: int = 0
    causal_epitaphs: list[str] = Field(default_factory=list)


class RunView(BaseModel):
    run_id: str
    revision: int
    archetype: ArchetypeId
    mode: RunMode = "classic"
    phase: RunPhase
    layer: int
    player: PlayerState
    deck: list[CardInstance]
    relics: list[str]
    map: RunMap
    combat: CombatView | None
    reward: RewardState | None
    choices: list[EventChoice]
    shop: ShopState | None
    history: list[HistoryEntry]
    epitaph: str | None
    story: StoryView | None = None


class RunResponse(BaseModel):
    run: RunView
    events: list[GameEvent]


class CreateRunResponse(RunResponse):
    access_token: str


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archetype: ArchetypeId
    mode: RunMode = "classic"


class ActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)


class ChooseNodeAction(ActionBase):
    kind: Literal["choose_node"]
    node_id: str


class PlayCardAction(ActionBase):
    kind: Literal["play_card"]
    card_uid: str
    target_id: str | None = None


class EndTurnAction(ActionBase):
    kind: Literal["end_turn"]


class TauntAction(ActionBase):
    kind: Literal["taunt"]


class ChooseRewardAction(ActionBase):
    kind: Literal["choose_reward"]
    option_index: int = Field(ge=0, le=2)


class SkipRewardAction(ActionBase):
    kind: Literal["skip_reward"]


class ChooseEventAction(ActionBase):
    kind: Literal["choose_event"]
    choice_id: str


class BuyAction(ActionBase):
    kind: Literal["buy"]
    item_id: str


class RemoveCardAction(ActionBase):
    kind: Literal["remove_card"]
    card_uid: str


class RestAction(ActionBase):
    kind: Literal["rest"]
    mode: Literal["heal", "upgrade"]


class UpgradeCardAction(ActionBase):
    kind: Literal["upgrade_card"]
    card_uid: str


class LeaveShopAction(ActionBase):
    kind: Literal["leave_shop"]


ActionData = Annotated[
    Union[
        ChooseNodeAction,
        PlayCardAction,
        EndTurnAction,
        TauntAction,
        ChooseRewardAction,
        SkipRewardAction,
        ChooseEventAction,
        BuyAction,
        RemoveCardAction,
        RestAction,
        UpgradeCardAction,
        LeaveShopAction,
    ],
    Field(discriminator="kind"),
]


class ActionRequest(RootModel[ActionData]):
    """扁平动作 JSON 的判别联合根模型。"""
