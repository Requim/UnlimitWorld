from __future__ import annotations

"""
游戏核心引擎：状态机编排、事件路由、暴毙结算

纯业务逻辑，不依赖 FastAPI、WebSocket、MySQL 等外部框架。
通过 interface 层适配器（CLI / WebSocket）驱动。

Phase 2D 改造：注入 SharedState + 怨念路由 + 断线重连 + 超时处理。
CLI 兼容：不传 dead_registry / immortal_hall 时回退到 M1 内存模式。
"""

import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Awaitable, TYPE_CHECKING

from server.config import REALM_CONFIG, settings
from server.domain.player import (
    PlayerState,
    DeadRecord,
    get_realm_by_cultivation,
    get_realm_name,
    get_realm_config,
    is_breakthrough,
    compute_death_rate,
    roll_death_check,
)
from server.domain.run_map import (
    RunMapNode,
    choose_run_node,
    complete_current_node,
    generate_run_map,
    open_chapter_choices,
    snapshot_run_map,
)
from server.domain.destiny import draw_destiny_offers, find_destiny_sign
from server.domain.ambition import draw_ambition_offers, find_ambition
from server.domain.event import (
    LocalEventResult,
    LLMInputContext,
    LLMOutput,
    PlayerContextForLLM,
    EventTrigger,
    EventSettlement,
    AttributeChanges,
)
from server.application.heaven_persona import (
    PERSONA_NAMES,
    get_persona_prompt,
    build_system_prompt,
)
from server.infrastructure.event_config import generate_local_event
from server.infrastructure.llm_client import LLMOrchestrator

if TYPE_CHECKING:
    from server.infrastructure.shared_state import DeadRegistryManager, ImmortalHallManager


# ═══════════════════════════════════════════════════════════════
# 阶段常量
# ═══════════════════════════════════════════════════════════════

class Stage:
    INIT = "INIT"
    IDLE = "IDLE"
    EVENT_TRIGGER = "EVENT_TRIGGER"
    AWAIT_DECISION = "AWAIT_DECISION"
    LLM_PROCESSING = "LLM_PROCESSING"
    SETTLEMENT = "SETTLEMENT"
    GAME_OVER = "GAME_OVER"


class EventType:
    FORCE_HEAVEN_KILL = "FORCE_HEAVEN_KILL"
    PRD_LLM_EVENT = "PRD_LLM_EVENT"
    BREAKTHROUGH_EVENT = "BREAKTHROUGH_EVENT"
    ASCENSION_EVENT = "ASCENSION_EVENT"
    LOCAL_EVENT = "LOCAL_EVENT"
    RESENTMENT_LLM_EVENT = "RESENTMENT_LLM_EVENT"    # 5% 怨念心魔试炼
    RESENTMENT_LOCAL_EVENT = "RESENTMENT_LOCAL_EVENT"  # 10% 怨念血红日志


# ═══════════════════════════════════════════════════════════════
# 优先级链路由（纯函数，可独立测试）
# ═══════════════════════════════════════════════════════════════

def determine_next_event(
    realm_code: int,
    cultivation: int,
    sin_value: int,
    prd_counter: int,
) -> str:
    """
    纯函数：根据玩家状态判定下一个事件类型。

    优先级：飞升 > 天谴满100 > PRD触发 > 大境界突破 > 本地日常
    PRD 在突破之前——作为"命运拦截器"，在突破前夕可能插入意外奇遇。
    """
    realm_cfg = REALM_CONFIG[realm_code]

    # 1. 飞升
    if realm_code == 6 and cultivation >= settings.ascension_cultivation:
        return EventType.ASCENSION_EVENT

    # 2. 天谴满值
    sin_max = realm_cfg["sin_max"]
    if sin_value >= sin_max and sin_max > 0:
        return EventType.FORCE_HEAVEN_KILL

    # 3. PRD 触发（命运拦截器）
    prd_threshold = realm_cfg.get("prd_threshold", 80)
    if prd_counter >= prd_threshold:
        return EventType.PRD_LLM_EVENT

    # 4. 大境界突破
    if is_breakthrough(cultivation, realm_code):
        return EventType.BREAKTHROUGH_EVENT

    # 5. 降级到本地日常（Phase 2D：内部再做怨念判定）
    return EventType.LOCAL_EVENT


def compose_story_text(reason_text: str, verdict_text: str) -> str:
    reason = (reason_text or "").strip()
    verdict = (verdict_text or "").strip()
    if reason and verdict:
        return f"{reason}\n\n{verdict}"
    return reason or verdict


def build_run_epitaph(
    session: PlayerState,
    backend_is_dead: bool,
    is_ascension: bool,
    used_custom_input: bool,
    trigger_type: str,
) -> tuple[str, str, int, str]:
    """生成盖棺定论的最小榜单候选信息。"""
    sin_max = get_realm_config(session.realm_code)["sin_max"]
    sin_ratio = session.sin_value / sin_max if sin_max > 0 else 0
    realm_name = get_realm_name(session.realm_code)

    if is_ascension and not backend_is_dead:
        score = int(session.heaven_points + session.foundation + session.survival_seconds / 10)
        return "飞升案首", "ascension", score, "下局可挑战嘴硬榜或赌命榜，给天道一点新麻烦。"

    if backend_is_dead:
        score = int(session.realm_code * 100 + sin_ratio * 100 + session.survival_seconds / 10)
        if used_custom_input:
            return "雷劫嘴硬体验官", "taunt", score + 30, "继续挑战嘴硬榜：话越硬，死法越有机会出圈。"
        if trigger_type == "ASCENSION":
            return "飞升门口摔跤仙", "death", score + 40, "下局可以先选苟活执念，把飞升门槛踩稳。"
        return "天道重点观察对象", "death", score, "下局可挑战暴毙榜：死不可怕，没记忆点才可怕。"

    if used_custom_input:
        return "在逃嘴硬修士", "taunt", 30 + int(sin_ratio * 50), "本局嘴硬已被天道记账，继续活下去才更有节目效果。"

    return "", "", 0, ""


# ═══════════════════════════════════════════════════════════════
# Tick 返回结果
# ═══════════════════════════════════════════════════════════════

@dataclass
class TickResult:
    """一次 tick() 调用的返回结果"""
    stage: str
    log_text: str = ""
    event_type: str = "LOCAL"
    cultivation: int = 0
    sin_value: int = 0
    luck: int = 0
    foundation: int = 0
    realm: str = ""
    sin_phase: str = "safe"
    trigger: Optional[EventTrigger] = None
    settlement: Optional[EventSettlement] = None
    is_dead: bool = False
    heaven_points_earned: int = 0
    waiting_for_decision: bool = False
    game_over: bool = False
    event_pool: str = ""
    risk_level: str = ""
    chosen_choice: Optional[dict] = None
    ambition_progress: int = 0
    ambition_target: int = 0
    ambition_progress_label: str = ""
    leaderboard_score_delta: int = 0
    taunt_count: int = 0
    gamble_survive_count: int = 0
    karma_pollution_score: int = 0
    death_drama_score: int = 0
    karma_trace_hook: str = ""
    node_id: str = ""
    node_type: str = ""
    route_label: str = ""
    route_notice: str = ""
    route_notice_level: str = ""


@dataclass
class SettlementDraft:
    """LLM 裁决结算过程中的临时文本与奖励状态。"""
    reason_text: str
    verdict_text: str
    story_text: str
    backend_is_dead: bool
    intercepted: bool = False
    heaven_points_earned: int = 0


# ═══════════════════════════════════════════════════════════════
# 游戏引擎
# ═══════════════════════════════════════════════════════════════

class GameEngine:
    """核心游戏引擎，管理一整局游戏的生命周期

    Phase 2D：通过构造函数注入 SharedState（可选，CLI 兼容）。
    """

    def __init__(
        self,
        orchestrator: Optional[LLMOrchestrator] = None,
        dead_registry: Optional["DeadRegistryManager"] = None,
        immortal_hall: Optional["ImmortalHallManager"] = None,
    ):
        self.orchestrator = orchestrator or LLMOrchestrator()

        # Phase 2D：全服共享状态（可选，CLI 模式下为 None 回退内存）
        self._dead_registry = dead_registry
        self._immortal_hall = immortal_hall

        # M1 兼容：内存列表（CLI 模式或无 SharedState 时使用）
        self._dead_list: list[DeadRecord] = []
        self._hall_list: list[dict] = []
        self._init_runtime_state()
        self._init_pending_selection_state()

    def _init_runtime_state(self):
        self.session: Optional[PlayerState] = None
        self.stage: str = Stage.INIT
        self._current_trigger: Optional[EventTrigger] = None
        self._start_time: float = 0.0

        # 决策超时时间戳（秒，monotonic）
        self._decision_deadline: float = 0.0

    def _init_pending_selection_state(self, player_name: str = "无名修士"):
        self._pending_destiny_offers: list[str] = []
        self._pending_ambition_offers: list[str] = []
        self._pending_destiny_sign_id: str = ""
        self._pending_player_name: str = player_name

    # ── 开局 ─────────────────────────────────────────────

    def new_game(
        self,
        player_name: str = "无名修士",
        player_id: Optional[str] = None,
        talent_bonus: Optional[dict] = None,
        deafness_protocol: int = 0,
        karma_shield: int = 0,
        heaven_points: int = 0,
        destiny_sign_id: str = "",
        ambition_id: str = "",
    ) -> PlayerState:
        """创建新一局游戏，随机分配天道人格"""
        player_id = player_id or f"p_{uuid.uuid4().hex[:8]}"
        persona = random.choice(PERSONA_NAMES)
        destiny_sign = find_destiny_sign(destiny_sign_id) if destiny_sign_id else None
        ambition = find_ambition(ambition_id) if ambition_id else None
        self.session = self._create_player_state(
            player_id,
            player_name,
            persona,
            talent_bonus or {},
            deafness_protocol,
            karma_shield,
            heaven_points,
            destiny_sign,
            ambition,
        )

        self.session.apply_talent_bonus()
        self.session.apply_destiny_sign()
        self.stage = Stage.IDLE
        self._start_time = time.time()
        self._current_trigger = None
        self._decision_deadline = 0.0
        self._init_pending_selection_state(player_name)

        return self.session

    def _create_player_state(
        self,
        player_id: str,
        player_name: str,
        persona: str,
        talent_bonus: dict,
        deafness_protocol: int,
        karma_shield: int,
        heaven_points: int,
        destiny_sign,
        ambition,
    ) -> PlayerState:
        return PlayerState(
            player_id=player_id,
            player_name=player_name,
            realm_code=1,
            cultivation=100,
            luck=random.randint(30, 70),
            foundation=random.randint(30, 70),
            sin_value=0,
            heaven_persona=persona,
            prd_counter=0,
            survival_seconds=0,
            heaven_points=heaven_points,
            deafness_protocol=deafness_protocol,
            karma_shield=karma_shield,
            talent_bonus=talent_bonus or {},
            destiny_sign_id=destiny_sign.id if destiny_sign else "",
            destiny_sign_title=destiny_sign.title if destiny_sign else "",
            destiny_mods=destiny_sign.to_mods() if destiny_sign else {},
            ambition_id=ambition.id if ambition else "",
            ambition_title=ambition.title if ambition else "",
            ambition_progress=0,
            ambition_target=ambition.target if ambition else 0,
            ambition_progress_label=ambition.progress_label if ambition else "",
            run_map=generate_run_map(random.Random(uuid.uuid4().hex)),
        )

    def prepare_new_game(self, player_name: str = "无名修士") -> list[dict]:
        """生成本局开局可选命格签。"""
        offers = draw_destiny_offers(3)
        self._pending_player_name = player_name or "无名修士"
        self._pending_destiny_offers = [item.id for item in offers]
        return [item.to_offer() for item in offers]

    def get_pending_destiny_offers(self) -> list[dict]:
        offers = []
        for sign_id in self._pending_destiny_offers:
            sign = find_destiny_sign(sign_id)
            if sign:
                offers.append(sign.to_offer())
        return offers

    def has_pending_destiny_offer(self) -> bool:
        return bool(self._pending_destiny_offers)

    def is_valid_pending_destiny(self, sign_id: str) -> bool:
        return sign_id in self._pending_destiny_offers

    def prepare_ambition_selection(self, destiny_sign_id: str) -> list[dict]:
        """命格选定后，生成本局可选执念。"""
        self._pending_destiny_sign_id = destiny_sign_id
        offers = draw_ambition_offers(3)
        self._pending_ambition_offers = [item.id for item in offers]
        return [item.to_offer() for item in offers]

    def get_pending_ambition_offers(self) -> list[dict]:
        offers = []
        for ambition_id in self._pending_ambition_offers:
            ambition = find_ambition(ambition_id)
            if ambition:
                offers.append(ambition.to_offer())
        return offers

    def has_pending_ambition_offer(self) -> bool:
        return bool(self._pending_ambition_offers)

    def is_valid_pending_ambition(self, ambition_id: str) -> bool:
        return ambition_id in self._pending_ambition_offers

    def get_run_map_snapshot(self) -> dict:
        """获取当前路线地图快照。

        Returns:
            dict: 给接口层下发的 `SC_RUN_MAP` payload；没有会话时返回空字典。

        Side Effects:
            无副作用。
        """
        if not self.session or not self.session.run_map.run_map_id:
            return {}
        return snapshot_run_map(self.session.run_map)

    def choose_run_map_node(self, node_id: str) -> tuple[bool, str]:
        """选择当前可用的路线地图节点。

        Args:
            node_id: 前端提交的节点 ID。

        Returns:
            tuple[bool, str]: 是否成功，以及失败原因。

        Side Effects:
            成功时进入该节点并清空可选节点列表。
        """
        if not self.session:
            return False, "尚未开局"
        if self.stage != Stage.IDLE:
            return False, "当前状态不能选择路线"
        return choose_run_node(self.session.run_map, node_id)

    def current_run_node(self) -> RunMapNode | None:
        """返回当前执行中的路线节点，没有节点时返回 None。"""
        if not self.session:
            return None
        return self.session.run_map.node_by_id(self.session.run_map.current_node_id)

    # ── 状态恢复（断线重连） ──────────────────────────────

    def restore_game(self, state: dict) -> PlayerState | None:
        """从持久化的游戏快照恢复状态。

        state 格式与 get_game_state() 返回一致：
        { stage, player, current_trigger }
        """
        if not state or "player" not in state:
            return None

        self.session = PlayerState.from_dict(state["player"])
        self.stage = state.get("stage", Stage.IDLE)

        trigger_dict = state.get("current_trigger")
        self._current_trigger = EventTrigger.model_validate(trigger_dict) if trigger_dict else None

        self._start_time = time.time() - self.session.survival_seconds

        # 若处于 AWAIT_DECISION 阶段，检查是否超时
        if self.stage == Stage.EVENT_TRIGGER and self._current_trigger:
            self._decision_deadline = time.monotonic() + settings.decision_timeout
        else:
            self._decision_deadline = 0.0

        return self.session

    def is_decision_timeout(self) -> bool:
        """检查当前决策是否已超时"""
        if self.stage != Stage.EVENT_TRIGGER:
            return False
        if self._decision_deadline <= 0:
            return False
        return time.monotonic() > self._decision_deadline

    # ── 主 tick ──────────────────────────────────────────

    async def tick(self) -> TickResult:
        """执行一次挂机 tick（10 秒）

        优先级链：飞升 > 天谴满100 > PRD触发 > 大境界突破 > 本地日常（含怨念判定）
        """
        if self.stage != Stage.IDLE:
            return TickResult(stage=self.stage, log_text="[系统] 当前不在挂机状态")

        if self.session is None:
            return TickResult(stage=Stage.INIT, log_text="[系统] 尚未创建游戏会话")

        session = self.session
        current_node = self.current_run_node()
        if current_node is None:
            self._refresh_run_map_if_exhausted()
            return self._build_waiting_route_result()

        # PRD 累加
        prd_step = random.randint(settings.prd_step_min, settings.prd_step_max)
        prd_step = max(1, prd_step + session.destiny_prd_step_delta())
        session.prd_counter += prd_step

        # 路由判定
        event_type = determine_next_event(
            realm_code=session.realm_code,
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            prd_counter=session.prd_counter,
        )

        if event_type == EventType.ASCENSION_EVENT:
            return self._trigger_ascension()

        if event_type == EventType.FORCE_HEAVEN_KILL:
            return await self._trigger_sin_full()

        if event_type == EventType.PRD_LLM_EVENT:
            session.prd_counter = 0
            return await self._trigger_heaven_event("PRD")

        if event_type == EventType.BREAKTHROUGH_EVENT:
            return await self._trigger_breakthrough()

        if current_node.node_type == "heaven":
            return await self._trigger_heaven_event("RUN_MAP")

        # LOCAL_EVENT — Phase 2D：内部怨念判定
        return await self._process_local_event()

    # ── 事件处理 ─────────────────────────────────────────

    def _apply_local_event_result(
        self,
        local: LocalEventResult,
        base_gain: int,
        log_prefix: str,
    ) -> TickResult:
        """应用普通事件的本地数值与 3K 目标推进效果。"""
        session = self.session

        total_gain = base_gain + local.cultivation_delta
        session.cultivation += total_gain
        session.luck = max(0, min(100, session.luck + getattr(local, "luck_delta", 0)))
        session.foundation = max(0, min(100, session.foundation + getattr(local, "foundation_delta", 0)))
        sin_max = get_realm_config(session.realm_code)["sin_max"]
        session.sin_value = max(0, min(sin_max, session.sin_value + getattr(local, "sin_delta", 0)))

        ambition_delta = self._resolve_local_ambition_delta(local)
        if ambition_delta and session.ambition_target > 0:
            session.ambition_progress = min(
                session.ambition_target,
                max(0, session.ambition_progress + ambition_delta),
            )

        new_realm = get_realm_by_cultivation(session.cultivation)
        if new_realm != session.realm_code:
            session.realm_code = new_realm

        session.survival_seconds += settings.tick_interval
        self._advance_run_node_progress()

        return self._build_local_tick_result(local, log_prefix)

    def _build_local_tick_result(
        self,
        local: LocalEventResult,
        log_prefix: str,
    ) -> TickResult:
        """组装普通事件 tick 返回帧，集中维护 3K 字段映射。"""
        session = self.session
        return TickResult(
            stage=Stage.IDLE,
            log_text=f"{log_prefix}{local.log_text}",
            event_type="LOCAL",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            event_pool=getattr(local, "event_pool", "common"),
            risk_level=getattr(local, "risk_level", "low"),
            chosen_choice=(
                local.chosen_choice.model_dump()
                if getattr(local, "chosen_choice", None)
                else None
            ),
            ambition_progress=session.ambition_progress,
            ambition_target=session.ambition_target,
            ambition_progress_label=session.ambition_progress_label,
            leaderboard_score_delta=getattr(local, "leaderboard_score_delta", 0),
            taunt_count=getattr(local, "taunt_count", 0),
            gamble_survive_count=getattr(local, "gamble_survive_count", 0),
            karma_pollution_score=getattr(local, "karma_pollution_score", 0),
            death_drama_score=getattr(local, "death_drama_score", 0),
            karma_trace_hook=getattr(local, "karma_trace_hook", "") or "",
            node_id=getattr(local, "node_id", "") or "",
            node_type=getattr(local, "node_type", "") or "",
            route_label=getattr(local, "route_label", "") or "",
        )

    def _build_waiting_route_result(self) -> TickResult:
        """等待玩家选择路线节点时返回一帧轻提示。"""
        session = self.session
        notice, notice_level = self._consume_route_notice()
        return TickResult(
            stage=Stage.IDLE,
            log_text=notice or "【路线停驻】前路分作三脉，请先择一处节点继续修行。",
            event_type="RUN_MAP_WAITING",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            ambition_progress=session.ambition_progress,
            ambition_target=session.ambition_target,
            ambition_progress_label=session.ambition_progress_label,
            route_notice=notice,
            route_notice_level=notice_level,
        )

    def _refresh_run_map_if_exhausted(self):
        """路线走空时为当前境界重开一张路线图，避免挂机流程卡死。"""
        if not self.session:
            return
        run_map = self.session.run_map
        if run_map.current_node_id or run_map.available_next_nodes:
            return
        is_final_chapter = run_map.current_chapter >= 6
        visited_count = len(run_map.visited_nodes)
        self.session.run_map = generate_run_map(random.Random(uuid.uuid4().hex))
        open_chapter_choices(self.session.run_map, self.session.realm_code)
        self._set_refreshed_route_notice(is_final_chapter, visited_count)

    def _set_refreshed_route_notice(self, is_final_chapter: bool, visited_count: int):
        """刷新路线图后写入一次性引导文案。"""
        if not self.session:
            return
        if is_final_chapter:
            notice = "【终章回响】此卷路线已尽，天道又铺开一卷新图。择一处节点，继续把命往前推。"
            level = "finale"
        else:
            notice = f"【路线续卷】已踏过 {visited_count} 处节点，前路重新显影。请择一处节点继续修行。"
            level = "info"
        self.session.run_map.route_notice = notice
        self.session.run_map.route_notice_level = level

    def _consume_route_notice(self) -> tuple[str, str]:
        """读取当前路线提示；提示保留在地图快照中直到玩家选择新节点。"""
        if not self.session:
            return "", ""
        run_map = self.session.run_map
        return run_map.route_notice, run_map.route_notice_level

    def _advance_run_node_progress(self):
        """扣减当前路线节点预算，耗尽后完成节点并统计路线特征。"""
        node = self.current_run_node()
        if not self.session or not node:
            return
        node.tick_budget = max(0, node.tick_budget - 1)
        if node.tick_budget > 0:
            return
        completed = complete_current_node(self.session.run_map)
        if completed:
            self._record_run_node_stats(completed)

    def _record_run_node_stats(self, node: RunMapNode):
        """累计本局路线图特征，供终局身份与前端统计使用。"""
        if node.node_type == "gamble":
            self.session.run_route_gamble_count += 1
        elif node.node_type == "shop":
            self.session.run_route_shop_count += 1
        elif node.node_type == "karma_echo":
            self.session.run_route_karma_count += 1
        elif node.node_type == "heaven":
            self.session.run_route_heaven_count += 1

    def _resolve_local_ambition_delta(self, local: LocalEventResult) -> int:
        """按当前执念筛选普通事件进度，避免所有轻选择都推进任意执念。"""
        if not self.session or not self.session.ambition_id:
            return 0
        tags = set(getattr(local, "ambition_tags", []) or [])
        ambition_id = self.session.ambition_id
        if ambition_id in tags:
            return max(1, getattr(local, "ambition_progress_delta", 0))
        if ambition_id == "taunt_heaven" and getattr(local, "taunt_count", 0) > 0:
            return max(1, getattr(local, "ambition_progress_delta", 0))
        if ambition_id == "borrowed_fate_comeback" and getattr(local, "gamble_survive_count", 0) > 0:
            return max(1, getattr(local, "ambition_progress_delta", 0))
        if ambition_id == "pollute_karma" and getattr(local, "karma_pollution_score", 0) > 0:
            return max(1, getattr(local, "ambition_progress_delta", 0))
        if ambition_id == "beautiful_death" and getattr(local, "death_drama_score", 0) > 0:
            return max(1, getattr(local, "ambition_progress_delta", 0))
        if ambition_id == "clean_merit" and "merit" in (getattr(local, "leaderboard_tags", []) or []):
            return max(1, getattr(local, "ambition_progress_delta", 0))
        return 0

    async def _process_local_event(self) -> TickResult:
        """处理本地日常事件。Phase 2D：15% 概率插入怨念事件。"""
        session = self.session

        # Phase 2D 怨念路由判定
        roll = random.randint(1, 100)
        if roll <= 5:
            return await self._trigger_resentment_llm_event()
        elif roll <= 15:
            return self._trigger_resentment_local_event()

        # 基础修为增长
        realm_cfg = get_realm_config(session.realm_code)
        base_rate = random.randint(
            realm_cfg["cultivation_rate_min"],
            realm_cfg["cultivation_rate_max"],
        )
        base_gain = base_rate * settings.tick_interval

        local = self._generate_node_local_event()
        return self._apply_local_event_result(local, base_gain, "【平淡日常】")

    def _trigger_resentment_local_event(self) -> TickResult:
        """10% 怨念血红日志 —— 本地事件但日志带有全服怨念色彩"""
        session = self.session
        realm_cfg = get_realm_config(session.realm_code)
        base_rate = random.randint(
            realm_cfg["cultivation_rate_min"],
            realm_cfg["cultivation_rate_max"],
        )
        base_gain = base_rate * settings.tick_interval
        local = self._generate_node_local_event()

        # 尝试从怨念池获取一条死因，附加到日志中
        karma_text = "你感到空气中弥漫着不祥的因果之力。"
        if self._dead_list:
            karma_text = self._fetch_karma_from_list()

        result = self._apply_local_event_result(local, base_gain, "【血红日志】")
        result.event_type = "RESENTMENT_LOCAL"
        result.log_text = f"{result.log_text} {karma_text}"
        return result

    def _generate_node_local_event(self) -> LocalEventResult:
        """按当前路线节点生成本地事件，并写入节点元数据。"""
        session = self.session
        node = self.current_run_node()
        if not node:
            return generate_local_event(session.realm_code, session.sin_value)
        local = generate_local_event(
            session.realm_code,
            session.sin_value,
            heaven_persona=session.heaven_persona,
            preferred_pool=node.event_pool,
            reward_multiplier=node.reward_multiplier,
            risk_multiplier=node.risk_multiplier,
        )
        self._decorate_node_local_event(local, node)
        return local

    def _decorate_node_local_event(self, local: LocalEventResult, node: RunMapNode):
        """补充路线节点元数据和首版局内轻效果。"""
        local.node_id = node.node_id
        local.node_type = node.node_type
        local.route_label = node.route_label
        if node.node_type == "shop":
            local.log_text = f"{local.log_text}【黑市补给】你用零碎功德换来一口回气。"
            local.foundation_delta += 1
        elif node.node_type == "rest":
            local.log_text = f"{local.log_text}【歇脚调息】道心稍定，天谴余波散去。"
            local.sin_delta -= 2

    async def _trigger_resentment_llm_event(self) -> TickResult:
        """5% 怨念心魔试炼 —— 从全服怨念池抽取死因，触发 LLM 天道事件"""
        session = self.session
        session.survival_seconds += settings.tick_interval

        # 优先从共享怨念池获取，fallback 到本地列表
        karma_brief = await self._fetch_random_karma()

        trigger = EventTrigger(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            trigger_type="RESENTMENT",
            karma_brief=karma_brief or "一缕远古怨魂在你的神识中浮现……",
            fixed_options=[
                {"id": "A", "text": "凝神静气，以道心抵御心魔侵蚀"},
                {"id": "B", "text": "迎难而上，试图吞噬心魔化为己用"},
            ],
            allow_custom_input=True,
            heaven_persona=session.heaven_persona,
        )

        self._current_trigger = trigger
        self.stage = Stage.EVENT_TRIGGER
        self._decision_deadline = time.monotonic() + settings.decision_timeout

        return TickResult(
            stage=Stage.EVENT_TRIGGER,
            log_text=f"👻 一股怨念从全服因果池中涌出，心魔试炼降临！",
            event_type="RESENTMENT_LLM",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            trigger=trigger,
            waiting_for_decision=True,
        )

    async def _trigger_breakthrough(self) -> TickResult:
        """触发大境界突破事件"""
        session = self.session
        next_realm = session.realm_code + 1
        next_name = get_realm_name(next_realm)

        karma_brief = await self._fetch_random_karma()

        trigger = EventTrigger(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            trigger_type="BREAKTHROUGH",
            karma_brief=karma_brief,
            fixed_options=[
                {"id": "A", "text": f"稳健突破，步步为营冲击{next_name}"},
                {"id": "B", "text": f"孤注一掷，狂暴吸收天地灵力强行冲关"},
            ],
            allow_custom_input=True,
            heaven_persona=session.heaven_persona,
        )

        self._current_trigger = trigger
        self.stage = Stage.EVENT_TRIGGER
        self._decision_deadline = time.monotonic() + settings.decision_timeout

        return TickResult(
            stage=Stage.EVENT_TRIGGER,
            log_text=f"⚡ 境界突破！你尝试冲击 {next_name}！",
            event_type="BREAKTHROUGH",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            trigger=trigger,
            waiting_for_decision=True,
        )

    async def _trigger_sin_full(self) -> TickResult:
        """触发天谴满值神罚事件"""
        session = self.session
        karma_brief = await self._fetch_random_karma()

        trigger = EventTrigger(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            trigger_type="SIN_FULL",
            karma_brief=karma_brief,
            fixed_options=[
                {"id": "A", "text": "跪地求饶，向天道忏悔"},
                {"id": "B", "text": "狂妄大笑，怒骂天道不公"},
            ],
            allow_custom_input=True,
            heaven_persona=session.heaven_persona,
        )

        self._current_trigger = trigger
        self.stage = Stage.EVENT_TRIGGER
        self._decision_deadline = time.monotonic() + settings.decision_timeout

        return TickResult(
            stage=Stage.EVENT_TRIGGER,
            log_text="🔴 天谴值爆满！天道神罚降临！",
            event_type="SIN_FULL",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase="danger",
            trigger=trigger,
            waiting_for_decision=True,
        )

    async def _trigger_heaven_event(self, trigger_source: str) -> TickResult:
        """触发天道因果轨道事件"""
        session = self.session
        karma_brief = await self._fetch_random_karma()

        trigger = EventTrigger(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            trigger_type="HEAVEN",
            karma_brief=karma_brief,
            fixed_options=[
                {"id": "A", "text": "谨慎行事，循规蹈矩"},
                {"id": "B", "text": "富贵险中求，剑走偏锋"},
            ],
            allow_custom_input=True,
            heaven_persona=session.heaven_persona,
        )

        self._current_trigger = trigger
        self.stage = Stage.EVENT_TRIGGER
        self._decision_deadline = time.monotonic() + settings.decision_timeout

        return TickResult(
            stage=Stage.EVENT_TRIGGER,
            log_text=f"⚡ 天机异动！{session.heaven_persona} 的天道意志降临！",
            event_type="HEAVEN",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            trigger=trigger,
            waiting_for_decision=True,
        )

    def _trigger_ascension(self) -> TickResult:
        """触发飞升大考"""
        session = self.session

        trigger = EventTrigger(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            trigger_type="ASCENSION",
            karma_brief="九天十地为之震动，万古仙穹为你敞开大门。",
            fixed_options=[
                {"id": "A", "text": "顺应天命，从容飞升"},
                {"id": "B", "text": "逆天而上，与天道对轰一拳"},
            ],
            allow_custom_input=True,
            heaven_persona=session.heaven_persona,
        )

        self._current_trigger = trigger
        self.stage = Stage.EVENT_TRIGGER
        self._decision_deadline = time.monotonic() + settings.decision_timeout

        return TickResult(
            stage=Stage.EVENT_TRIGGER,
            log_text="🌟 修为圆满！九天十地无上大劫降临，飞升之门已开！",
            event_type="ASCENSION",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            trigger=trigger,
            waiting_for_decision=True,
        )

    # ── 玩家提交决策 ─────────────────────────────────────

    async def submit_decision(
        self,
        choice_id: str = "A",
        custom_text: str = "",
        on_chunk: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> TickResult:
        """处理玩家的对线决策（选择 A/B 或自定义骚话 C）

        内部流程：组装 LLM 上下文 → 后端计算 is_dead → LLM 流式推演 → 结算。
        on_chunk: M2 WebSocket 流式回调，每收到一个字符即调用。
        """
        if self.stage != Stage.EVENT_TRIGGER:
            return TickResult(stage=self.stage, log_text="[系统] 当前没有待处理的事件")

        session = self.session
        trigger = self._current_trigger
        self.stage = Stage.LLM_PROCESSING
        self._decision_deadline = 0.0

        is_ascension = trigger.trigger_type == "ASCENSION"
        is_dead = self._roll_backend_death(session, is_ascension)
        llm_context = self._build_llm_context(
            session,
            trigger,
            is_dead,
            choice_id,
            custom_text,
        )
        full_story, llm_output = await self._run_llm_stream(
            session.heaven_persona,
            llm_context,
            on_chunk,
        )
        used_custom_input = choice_id == "C" and bool(custom_text.strip())
        return await self._settle(
            llm_output, trigger, is_dead, is_ascension, full_story, used_custom_input
        )

    def _roll_backend_death(self, session: PlayerState, is_ascension: bool) -> bool:
        if is_ascension:
            return random.random() < 0.05
        return roll_death_check(
            session.realm_code,
            session.sin_value,
            session.foundation,
        )

    def _build_player_llm_context(self, session: PlayerState) -> PlayerContextForLLM:
        return PlayerContextForLLM(
            player_name=session.player_name,
            realm=get_realm_name(session.realm_code),
            realm_code=session.realm_code,
            cultivation=session.cultivation,
            luck=session.luck,
            foundation=session.foundation,
            sin_value=session.sin_value,
            effective_luck=session.effective_luck(),
        )

    def _build_llm_context(
        self,
        session: PlayerState,
        trigger: EventTrigger,
        is_dead: bool,
        choice_id: str,
        custom_text: str,
    ) -> LLMInputContext:
        player_ctx = self._build_player_llm_context(session)
        return LLMInputContext(
            system_context={
                "heaven_personality": session.heaven_persona,
                "global_rule": "玩家如果自定义发言极其搞笑、无耻且能自圆其说，给予生路；若无理取闹，直接神罚拍死。",
            },
            player_status=player_ctx,
            trigger_type=trigger.trigger_type,
            is_dead=is_dead,
            historical_karma=trigger.karma_brief,
            player_custom_input=custom_text if choice_id == "C" else "",
            chosen_option=choice_id,
            fixed_options=trigger.fixed_options,
            heaven_persona=session.heaven_persona,
        )

    async def _run_llm_stream(
        self,
        heaven_persona: str,
        llm_context: LLMInputContext,
        on_chunk: Optional[Callable[[str, str], Awaitable[None]]],
    ) -> tuple[str, LLMOutput]:
        system_prompt = get_persona_prompt(heaven_persona)
        full_story = ""
        llm_output = None
        try:
            async for chunk in self.orchestrator.process_streaming(system_prompt, llm_context):
                piece, llm_output = await self._consume_llm_chunk(chunk, llm_output, on_chunk)
                full_story += piece
        except Exception:
            pass
        if llm_output is None:
            llm_output = self.orchestrator._fallback_resolve(llm_context)
        return full_story, llm_output

    async def _consume_llm_chunk(
        self,
        chunk,
        current_output: LLMOutput | None,
        on_chunk: Optional[Callable[[str, str], Awaitable[None]]],
    ) -> tuple[str, LLMOutput | None]:
        if isinstance(chunk, LLMOutput):
            return "", chunk
        if isinstance(chunk, str):
            if on_chunk is not None:
                await on_chunk("reason_text", chunk)
            return chunk, current_output
        segment = str(chunk.get("segment", "reason_text"))
        piece = str(chunk.get("chunk", ""))
        if on_chunk is not None:
            await on_chunk(segment, piece)
        return piece if segment in ("reason_text", "story_text") else "", current_output

    async def _settle(
        self,
        llm_output: LLMOutput,
        trigger: EventTrigger,
        backend_is_dead: bool,
        is_ascension: bool,
        full_story: str,
        used_custom_input: bool,
    ) -> TickResult:
        """事件结算。Phase 2D：死亡/飞升写入全服共享状态。"""
        session = self.session
        if session is None:
            return TickResult(stage=Stage.INIT, log_text="[系统] 会话丢失")
        draft = self._apply_settlement_mutations(session, llm_output, backend_is_dead, full_story)
        game_over = draft.backend_is_dead or is_ascension
        draft.heaven_points_earned = self._settle_heaven_points(
            session,
            game_over,
            used_custom_input,
        )
        await self._apply_settlement_stage(session, llm_output, draft.backend_is_dead, is_ascension, game_over)
        session.prd_counter = 0
        self._current_trigger = None
        return self._build_settled_tick_result(
            session, llm_output, trigger, full_story, draft, is_ascension, used_custom_input, game_over
        )

    def _apply_settlement_mutations(
        self,
        session: PlayerState,
        llm_output: LLMOutput,
        backend_is_dead: bool,
        full_story: str,
    ) -> SettlementDraft:
        draft = self._prepare_settlement_draft(session, llm_output, backend_is_dead, full_story)
        if not draft.backend_is_dead:
            self._apply_llm_attribute_changes(session, llm_output.attribute_changes)
        session.survival_seconds += settings.tick_interval
        return draft

    def _build_settled_tick_result(
        self,
        session: PlayerState,
        llm_output: LLMOutput,
        trigger: EventTrigger,
        full_story: str,
        draft: SettlementDraft,
        is_ascension: bool,
        used_custom_input: bool,
        game_over: bool,
    ) -> TickResult:
        settlement = self._build_settlement(
            session,
            llm_output,
            trigger,
            draft.backend_is_dead,
            is_ascension,
            used_custom_input,
            draft,
        )
        return self._build_settlement_result(
            session,
            llm_output,
            trigger,
            full_story,
            settlement,
            draft.backend_is_dead,
            draft.heaven_points_earned,
            game_over,
        )

    def _prepare_settlement_draft(
        self,
        session: PlayerState,
        llm_output: LLMOutput,
        backend_is_dead: bool,
        full_story: str,
    ) -> SettlementDraft:
        reason_text, verdict_text, story_text = self._compose_settlement_texts(
            llm_output,
            full_story,
        )
        backend_is_dead, intercepted, verdict_text, story_text = self._apply_karma_shield(
            session,
            backend_is_dead,
            reason_text,
            verdict_text,
            story_text,
        )
        return SettlementDraft(
            reason_text=reason_text,
            verdict_text=verdict_text,
            story_text=story_text,
            backend_is_dead=backend_is_dead,
            intercepted=intercepted,
        )

    def _compose_settlement_texts(
        self,
        llm_output: LLMOutput,
        full_story: str,
    ) -> tuple[str, str, str]:
        reason_text = llm_output.reason_text or llm_output.story_text or full_story
        verdict_text = llm_output.verdict_text or llm_output.event_title
        story_text = llm_output.story_text or compose_story_text(reason_text, verdict_text)
        return reason_text, verdict_text, story_text

    def _apply_karma_shield(
        self,
        session: PlayerState,
        backend_is_dead: bool,
        reason_text: str,
        verdict_text: str,
        story_text: str,
    ) -> tuple[bool, bool, str, str]:
        if not backend_is_dead or session.karma_shield <= 0:
            return backend_is_dead, False, verdict_text, story_text
        session.karma_shield -= 1
        shield_line = "【因果遮蔽卡触发！宗门太上老祖跨越时空长河，一掌震碎天雷，强行将你捞回！】"
        return False, True, shield_line, compose_story_text(reason_text, shield_line)

    def _apply_llm_attribute_changes(self, session: PlayerState, changes: AttributeChanges):
        session.cultivation += changes.cultivation
        realm_cfg = get_realm_config(session.realm_code)
        session.sin_value = max(0, min(realm_cfg["sin_max"], session.sin_value + changes.sin_value))
        session.luck = max(0, min(100, session.luck + changes.luck))
        session.foundation = max(0, min(100, session.foundation + changes.foundation))
        new_realm = get_realm_by_cultivation(session.cultivation)
        if new_realm != session.realm_code:
            session.realm_code = new_realm

    def _settle_heaven_points(
        self,
        session: PlayerState,
        game_over: bool,
        used_custom_input: bool,
    ) -> int:
        earned = self._calc_heaven_points(session) if game_over else 0
        if used_custom_input:
            self._apply_custom_input_bonus(session)
            earned += session.destiny_custom_heaven_points_bonus()
        if earned <= 0:
            return 0
        earned = max(0, int(earned * session.destiny_heaven_points_multiplier()))
        session.heaven_points += earned
        return earned

    def _apply_custom_input_bonus(self, session: PlayerState):
        sin_max = get_realm_config(session.realm_code)["sin_max"]
        session.sin_value = max(
            0,
            min(sin_max, session.sin_value + session.destiny_custom_sin_bonus()),
        )

    async def _apply_settlement_stage(
        self,
        session: PlayerState,
        llm_output: LLMOutput,
        backend_is_dead: bool,
        is_ascension: bool,
        game_over: bool,
    ):
        if game_over:
            await self._record_final_outcome(session, llm_output, backend_is_dead, is_ascension)
            self.stage = Stage.GAME_OVER
            return
        self.stage = Stage.IDLE
        self._complete_current_run_node_after_settlement()

    async def _record_final_outcome(
        self,
        session: PlayerState,
        llm_output: LLMOutput,
        backend_is_dead: bool,
        is_ascension: bool,
    ):
        if is_ascension and not backend_is_dead:
            await self._record_ascension(session, llm_output)
            return
        await self._record_death(session, llm_output)

    async def _record_ascension(self, session: PlayerState, llm_output: LLMOutput):
        self._hall_list.append({
            "player_name": session.player_name,
            "player_id": session.player_id,
            "ascension_title": llm_output.event_title or "飞升大乘",
            "total_heaven_points": session.heaven_points,
            "ascended_at": datetime.now().isoformat(),
        })
        if self._immortal_hall:
            await self._immortal_hall.add_ascension(
                session.player_id,
                session.player_name,
                llm_output.event_title or "飞升大乘",
                session.heaven_points,
            )

    async def _record_death(self, session: PlayerState, llm_output: LLMOutput):
        dead_record = DeadRecord(
            player_id=session.player_id,
            player_name=session.player_name,
            realm=get_realm_name(session.realm_code),
            realm_code=session.realm_code,
            dead_title=llm_output.dead_title or "死于天道裁决",
            sin_value=session.sin_value,
            survived_seconds=session.survival_seconds,
        )
        self._dead_list.append(dead_record)
        if self._dead_registry:
            await self._dead_registry.add_record(dead_record)

    def _build_settlement(
        self,
        session: PlayerState,
        llm_output: LLMOutput,
        trigger: EventTrigger,
        backend_is_dead: bool,
        is_ascension: bool,
        used_custom_input: bool,
        draft: SettlementDraft,
    ) -> EventSettlement:
        epitaph_title, leaderboard_type, leaderboard_score, next_goal_hint = build_run_epitaph(
            session=session,
            backend_is_dead=backend_is_dead,
            is_ascension=is_ascension,
            used_custom_input=used_custom_input,
            trigger_type=trigger.trigger_type,
        )
        settlement = EventSettlement(
            event_id=trigger.event_id,
            is_dead=backend_is_dead,
            dead_title=llm_output.dead_title if backend_is_dead else "",
            reason_text=draft.reason_text,
            verdict_text=draft.verdict_text,
            event_title=llm_output.event_title,
            story_text=draft.story_text,
            attribute_changes=llm_output.attribute_changes,
            intercepted_by_shield=draft.intercepted,
            heaven_points_earned=draft.heaven_points_earned,
            epitaph_title=epitaph_title,
            leaderboard_type=leaderboard_type,
            leaderboard_score=leaderboard_score,
            next_goal_hint=next_goal_hint,
        )
        return settlement

    def _build_settlement_result(
        self,
        session: PlayerState,
        llm_output: LLMOutput,
        trigger: EventTrigger,
        full_story: str,
        settlement: EventSettlement,
        backend_is_dead: bool,
        heaven_points_earned: int,
        game_over: bool,
    ) -> TickResult:
        return TickResult(
            stage=self.stage,
            log_text=f"[{llm_output.event_title}] {full_story[:100]}...",
            event_type=trigger.trigger_type,
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            settlement=settlement,
            is_dead=backend_is_dead,
            heaven_points_earned=heaven_points_earned,
            game_over=game_over,
        )

    def _complete_current_run_node_after_settlement(self):
        """非终局天道裁决结束后完成当前路线节点。"""
        if not self.session or not self.session.run_map.current_node_id:
            return
        completed = complete_current_node(self.session.run_map)
        if completed:
            self._record_run_node_stats(completed)

    # ── 超时处理 ─────────────────────────────────────────

    def handle_timeout(self) -> TickResult:
        """处理对线超时：自动选 A + 扣除当前修为 10%（道心蒙尘）"""
        if self.stage != Stage.EVENT_TRIGGER:
            return TickResult(stage=self.stage)

        session = self.session
        penalty = int(session.cultivation * 0.1)
        session.cultivation = max(0, session.cultivation - penalty)

        trigger = self._current_trigger
        trigger.karma_brief += f"\n（因沉默不语，天道降下'道心蒙尘'惩罚，扣除修为 {penalty}）"

        self._decision_deadline = 0.0

        return TickResult(
            stage=Stage.AWAIT_DECISION,
            log_text=f"⏰ 对线超时！天道降下'道心蒙尘'惩罚，扣除修为 {penalty}。自动选择保守方案。",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
            waiting_for_decision=False,
        )

    async def auto_timeout_submit(self) -> TickResult:
        """超时自动提交：先执行超时惩罚，再以选项 A 提交 LLM 推演。"""
        if self._current_trigger is None:
            return TickResult(stage=self.stage, log_text="[系统] 超时但无活动事件")
        self.handle_timeout()
        return await self.submit_decision(choice_id="A", custom_text="")

    # ── 辅助方法 ─────────────────────────────────────────

    async def _fetch_random_karma(self) -> str:
        """从全服怨念池中随机抓取一条历史因果。

        Phase 2D 双轨：优先走 DeadRegistryManager（全服共享），
        fallback 到本地 _dead_list（CLI/M1 兼容）。
        """
        if self._dead_registry:
            result = await self._dead_registry.random_karma()
            if result:
                return result

        return self._fetch_karma_from_list()

    def _fetch_karma_from_list(self) -> str:
        """从本地内存列表中随机抓取一条死因（CLI/M1 fallback）"""
        if not self._dead_list:
            return ""
        record = random.choice(self._dead_list)
        return f"此地曾有真实玩家【{record.player_name}】因【{record.dead_title}】而死。"

    def _calc_heaven_points(self, session: PlayerState) -> int:
        """结算天道点"""
        raw = (
            session.survival_seconds / settings.heaven_point_survive_divisor
            + session.cultivation * settings.heaven_point_cultivation_multiplier
        )
        return int(raw)

    def get_game_state(self) -> dict:
        """获取当前游戏的完整状态快照（用于断线重连持久化）"""
        if not self.session:
            return {}
        return {
            "stage": self.stage,
            "player": self.session.to_dict(),
            "current_trigger": self._current_trigger.model_dump() if self._current_trigger else None,
        }
