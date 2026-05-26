"""
领域层：事件模型与 LLM 契约

定义本地事件、LLM 输入/输出 的 Pydantic 模型。
LLMOutput 是后端校验 DeepSeek 返回 JSON 的唯一标准。
"""

from typing import Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 本地事件模型
# ═══════════════════════════════════════════════════════════════

class LocalEventResult(BaseModel):
    """本地轨道事件的组装结果"""
    event_id: str
    log_text: str
    cultivation_delta: int
    sin_delta: int = 0
    luck_delta: int = 0
    foundation_delta: int = 0
    flavor: str = "normal"  # normal / warning / danger
    special_item: Optional[str] = None


# ═══════════════════════════════════════════════════════════════
# LLM 输入上下文
# ═══════════════════════════════════════════════════════════════

class PlayerContextForLLM(BaseModel):
    """发送给大模型的玩家状态快照"""
    player_name: str
    realm: str
    realm_code: int
    cultivation: int
    luck: int
    foundation: int
    sin_value: int
    effective_luck: int = 0


class LLMInputContext(BaseModel):
    """后端 → LLM 的完整请求上下文"""
    system_context: dict = Field(default_factory=dict)
    player_status: PlayerContextForLLM = Field(default_factory=lambda: PlayerContextForLLM(
        player_name="", realm="", realm_code=1, cultivation=0, luck=0, foundation=0, sin_value=0
    ))
    trigger_type: str = "IDLE_TICK"       # IDLE_TICK / BREAKTHROUGH / SIN_FULL / ASCENSION
    is_dead: bool = False                  # 后端公式算完的结论，LLM 不可篡改
    historical_karma: str = ""             # 从 dead_registry 随机抓取的死因
    player_custom_input: str = ""          # 玩家的骚话（选项 C）
    chosen_option: str = ""                # A / B / C
    fixed_options: list = Field(default_factory=list)  # [{id: "A", text: "..."}, ...]
    heaven_persona: str = "混沌乐子人"


# ═══════════════════════════════════════════════════════════════
# LLM 输出契约（后端 Pydantic 校验唯一标准）
# ═══════════════════════════════════════════════════════════════

class AttributeChanges(BaseModel):
    cultivation: int = 0
    sin_value: int = 0
    luck: int = 0
    foundation: int = 0


class LLMOutput(BaseModel):
    """大模型必须严格返回此结构，否则触发 Retry"""
    reason_text: str = ""
    verdict_text: str = ""
    event_title: str = ""
    story_text: str = ""
    is_dead: bool = False
    dead_title: str = ""                   # is_dead=true 时必须提供
    attribute_changes: AttributeChanges = Field(default_factory=AttributeChanges)
    next_action_required: str = "IDLE"     # IDLE / GAME_OVER


# ═══════════════════════════════════════════════════════════════
# 事件触发模型
# ═══════════════════════════════════════════════════════════════

class EventTrigger(BaseModel):
    """一次事件的触发信息"""
    event_id: str
    trigger_type: str                      # LOCAL / HEAVEN / BREAKTHROUGH / SIN_FULL / ASCENSION
    karma_brief: str = ""                  # 历史因果文本
    fixed_options: list = Field(default_factory=list)
    allow_custom_input: bool = True
    heaven_persona: str = ""


class EventSettlement(BaseModel):
    """事件结算结果"""
    event_id: str
    is_dead: bool
    dead_title: str = ""
    reason_text: str = ""
    verdict_text: str = ""
    event_title: str = ""
    story_text: str = ""                   # 完整剧情文本
    attribute_changes: AttributeChanges = Field(default_factory=AttributeChanges)
    intercepted_by_shield: bool = False    # 是否被因果遮蔽卡拦截
    heaven_points_earned: int = 0          # 若死亡/飞升，结算的天道点
    epitaph_title: str = ""                # 盖棺定论称号
    leaderboard_type: str = ""             # ascension / death / taunt / gamble 等候选榜
    leaderboard_score: int = 0
    next_goal_hint: str = ""
