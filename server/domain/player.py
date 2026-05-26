"""
领域层：玩家属性矩阵与暴毙公式

纯 Pydantic 模型，不依赖任何框架或外部 IO。
提供 to_dict() / from_dict() 用于 M2 持久化无缝对接。
"""

import random
import math
from datetime import datetime
from pydantic import BaseModel, Field
from server.config import REALM_CONFIG, settings


# ═══════════════════════════════════════════════════════════════
# 境界判定（纯函数）
# ═══════════════════════════════════════════════════════════════

def get_realm_by_cultivation(cultivation: int) -> int:
    """根据当前修为值判定境界代号"""
    for code in range(6, 0, -1):  # 从高到低遍历
        cfg = REALM_CONFIG[code]
        if cultivation >= cfg["cultivation_base"]:
            return code
    return 1


def get_realm_name(realm_code: int) -> str:
    return REALM_CONFIG[realm_code]["name"]


def get_realm_config(realm_code: int) -> dict:
    return REALM_CONFIG[realm_code]


def is_breakthrough(cultivation: int, realm_code: int) -> bool:
    """判断当前修为是否达到当前境界的突破门槛"""
    cap = REALM_CONFIG[realm_code]["cultivation_cap"]
    return cultivation >= cap and realm_code < 7


# ═══════════════════════════════════════════════════════════════
# 暴毙公式（纯函数）
# ═══════════════════════════════════════════════════════════════

def compute_death_rate(
    realm_code: int,
    sin_current: int,
    foundation: int,
    alpha: float = settings.alpha,
) -> float:
    """
    计算最终暴毙率 P_final。

    P_final = P_base + (1 - P_base) * (S_current / S_max) ^ (alpha * beta)
    其中 beta(F) = 1 + F / 100
    """
    cfg = REALM_CONFIG[realm_code]
    p_base = cfg["base_death_rate"]
    s_max = cfg["sin_max"]

    if s_max <= 0:
        return 0.0

    sin_ratio = max(0.0, min(1.0, sin_current / s_max))
    beta = 1.0 + foundation / 100.0
    exponent = alpha * beta

    p_final = p_base + (1.0 - p_base) * (sin_ratio ** exponent)
    return p_final


def roll_death_check(
    realm_code: int,
    sin_current: int,
    foundation: int,
) -> bool:
    """掷骰判定是否暴毙。True = 死亡，False = 存活。"""
    cfg = REALM_CONFIG[realm_code]
    if sin_current >= cfg["sin_max"]:
        return True
    p = compute_death_rate(realm_code, sin_current, foundation)
    roll = random.random()
    return roll < p


# ═══════════════════════════════════════════════════════════════
# 玩家属性矩阵（Pydantic 模型）
# ═══════════════════════════════════════════════════════════════

class PlayerState(BaseModel):
    """当局玩家实时状态"""
    player_id: str = ""
    player_name: str = "无名修士"
    realm_code: int = 1
    cultivation: int = 100          # 当前修为值
    luck: int = 50                  # 0-100
    foundation: int = 50            # 0-100
    sin_value: int = 0              # 天谴值
    heaven_persona: str = "混沌乐子人"  # 当局天道人格
    prd_counter: int = 0            # PRD 累加计数器
    survival_seconds: int = 0       # 当局存活秒数

    # 局外资产（跨局保留，挂载在 PlayerState 上方便传递）
    heaven_points: int = 0          # 天道点余额
    deafness_protocol: int = 0      # 天道失聪协议剩余局数
    karma_shield: int = 0           # 因果遮蔽卡数量
    talent_bonus: dict = Field(default_factory=dict)  # 先天气运加成
    destiny_sign_id: str = ""
    destiny_sign_title: str = ""
    destiny_mods: dict = Field(default_factory=dict)
    ambition_id: str = ""
    ambition_title: str = ""
    ambition_progress: int = 0
    ambition_target: int = 0
    ambition_progress_label: str = ""

    def apply_talent_bonus(self):
        """在开局时应用天赋加成到初始属性"""
        if "luck" in self.talent_bonus:
            self.luck = min(100, self.luck + self.talent_bonus["luck"])
        if "foundation" in self.talent_bonus:
            self.foundation = min(100, self.foundation + self.talent_bonus["foundation"])

    def apply_destiny_sign(self):
        """在开局时应用命格签初始修正。"""
        self.luck = max(0, min(100, self.luck + int(self.destiny_mods.get("initial_luck", 0))))
        self.foundation = max(
            0,
            min(100, self.foundation + int(self.destiny_mods.get("initial_foundation", 0))),
        )
        cfg = REALM_CONFIG[self.realm_code]
        self.sin_value = max(
            0,
            min(cfg["sin_max"], self.sin_value + int(self.destiny_mods.get("initial_sin", 0))),
        )

    def apply_deafness_protocol(self):
        """应用天道失聪协议：逻辑 luck +10"""
        if self.deafness_protocol > 0:
            self.deafness_protocol -= 1
            return 10
        return 0

    def effective_luck(self) -> int:
        """返回逻辑气运值（含失聪协议加成）"""
        bonus = 10 if self.deafness_protocol > 0 else 0
        return min(100, self.luck + bonus)

    def destiny_prd_step_delta(self) -> int:
        return int(self.destiny_mods.get("prd_step_delta", 0))

    def destiny_custom_heaven_points_bonus(self) -> int:
        return int(self.destiny_mods.get("custom_heaven_points_bonus", 0))

    def destiny_custom_sin_bonus(self) -> int:
        return int(self.destiny_mods.get("custom_sin_bonus", 0))

    def destiny_heaven_points_multiplier(self) -> float:
        return float(self.destiny_mods.get("heaven_points_multiplier", 1.0))

    def sin_phase(self) -> str:
        """天谴值阶段"""
        cfg = REALM_CONFIG[self.realm_code]
        s_max = cfg["sin_max"]
        ratio = self.sin_value / s_max if s_max > 0 else 0
        if ratio < 0.5:
            return "safe"
        elif ratio < 0.8:
            return "warning"
        else:
            return "danger"

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerState":
        return cls.model_validate(data)


class PlayerAccount(BaseModel):
    """局外玩家账号（M2 持久化到 MySQL player_account 表）"""
    player_id: str
    wechat_openid: str = ""
    player_name: str = "无名修士"
    avatar_url: str = ""
    heaven_points: int = 0
    deafness_protocol: int = 0
    karma_shield: int = 0
    pending_sin_reset: bool = False   # 功德洗白券标记，下个 tick 清零 sin_value
    talent_bonus: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: datetime = Field(default_factory=datetime.now)


class DeadRecord(BaseModel):
    """死亡因果池记录（M2 持久化到 dead_registry 表）"""
    player_id: str
    player_name: str
    realm: str                    # 死亡时境界名称
    realm_code: int               # 境界代号
    dead_title: str               # LLM 生成的死因
    sin_value: int = 0
    survived_seconds: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class ActiveSession(BaseModel):
    """活跃会话快照（M2 持久化到 active_session 表，支持断线重连）"""
    player_id: str
    session_json: str = ""        # PlayerState.model_dump_json()
    stage: str = "IDLE"           # 当前状态机阶段
    trigger_json: str | None = None  # 若在 AWAIT_DECISION，保存 EventTrigger JSON
    updated_at: datetime = Field(default_factory=datetime.now)
