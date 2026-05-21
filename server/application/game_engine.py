"""
游戏核心引擎：状态机编排、事件路由、暴毙结算

纯业务逻辑，不依赖 FastAPI、WebSocket、MySQL 等外部框架。
通过 interface 层适配器（CLI / WebSocket）驱动。
"""

import random
import time
import uuid
from datetime import datetime
from typing import Callable, Optional, Awaitable

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
    FORCE_HEAVEN_KILL = "FORCE_HEAVEN_KILL"      # 天谴满值神罚
    PRD_LLM_EVENT = "PRD_LLM_EVENT"              # PRD 触发天道事件
    BREAKTHROUGH_EVENT = "BREAKTHROUGH_EVENT"    # 大境界突破
    ASCENSION_EVENT = "ASCENSION_EVENT"          # 飞升大考
    LOCAL_EVENT = "LOCAL_EVENT"                  # 本地日常

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
    PRD 触发后归零由调用方负责，不会导致死循环。
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

    # 5. 降级到本地日常
    return EventType.LOCAL_EVENT


# ═══════════════════════════════════════════════════════════════
# Tick 返回结果
# ═══════════════════════════════════════════════════════════════

class TickResult:
    """一次 tick() 调用的返回结果"""

    def __init__(
        self,
        stage: str,
        log_text: str = "",
        event_type: str = "LOCAL",
        cultivation: int = 0,
        sin_value: int = 0,
        luck: int = 0,
        foundation: int = 0,
        realm: str = "",
        sin_phase: str = "safe",
        # 天道事件相关
        trigger: Optional[EventTrigger] = None,
        settlement: Optional[EventSettlement] = None,
        is_dead: bool = False,
        heaven_points_earned: int = 0,
        # 标志位
        waiting_for_decision: bool = False,
        game_over: bool = False,
    ):
        self.stage = stage
        self.log_text = log_text
        self.event_type = event_type
        self.cultivation = cultivation
        self.sin_value = sin_value
        self.luck = luck
        self.foundation = foundation
        self.realm = realm
        self.sin_phase = sin_phase
        self.trigger = trigger
        self.settlement = settlement
        self.is_dead = is_dead
        self.heaven_points_earned = heaven_points_earned
        self.waiting_for_decision = waiting_for_decision
        self.game_over = game_over


# ═══════════════════════════════════════════════════════════════
# 游戏引擎
# ═══════════════════════════════════════════════════════════════

class GameEngine:
    """核心游戏引擎，管理一整局游戏的生命周期"""

    def __init__(self, orchestrator: Optional[LLMOrchestrator] = None):
        self.orchestrator = orchestrator or LLMOrchestrator()
        self.session: Optional[PlayerState] = None
        self.stage: str = Stage.INIT
        self._current_trigger: Optional[EventTrigger] = None
        self._dead_registry: list[DeadRecord] = []  # M1 用内存模拟死亡因果池
        self._immortal_hall: list[dict] = []  # M1 用内存模拟名人堂
        self._start_time: float = 0.0

    # ── 开局 ─────────────────────────────────────────────

    def new_game(
        self,
        player_name: str = "无名修士",
        player_id: Optional[str] = None,
        talent_bonus: Optional[dict] = None,
        deafness_protocol: int = 0,
        karma_shield: int = 0,
        heaven_points: int = 0,
    ) -> PlayerState:
        """创建新一局游戏，随机分配天道人格"""
        player_id = player_id or f"p_{uuid.uuid4().hex[:8]}"
        persona = random.choice(PERSONA_NAMES[:3])  # M1 仅三大人格，M3 加入夺舍

        self.session = PlayerState(
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
        )

        self.session.apply_talent_bonus()
        self.stage = Stage.IDLE
        self._start_time = time.time()
        self._current_trigger = None

        return self.session

    # ── 主 tick ──────────────────────────────────────────

    async def tick(self) -> TickResult:
        """执行一次挂机 tick（10 秒）

        优先级链：飞升 > 天谴满100 > PRD触发 > 大境界突破 > 本地日常
        PRD 在突破之前：作为"命运拦截器"，在突破前夕插入意外奇遇。
        """
        if self.stage != Stage.IDLE:
            return TickResult(stage=self.stage, log_text="[系统] 当前不在挂机状态")

        if self.session is None:
            return TickResult(stage=Stage.INIT, log_text="[系统] 尚未创建游戏会话")

        session = self.session

        # PRD 累加（每次 tick 必定累加，无论最终触发什么）
        prd_step = random.randint(settings.prd_step_min, settings.prd_step_max)
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
            return self._trigger_sin_full()

        if event_type == EventType.PRD_LLM_EVENT:
            session.prd_counter = 0
            return self._trigger_heaven_event("PRD")

        if event_type == EventType.BREAKTHROUGH_EVENT:
            return self._trigger_breakthrough()

        # LOCAL_EVENT
        return self._process_local_event()

    # ── 事件处理 ─────────────────────────────────────────

    def _process_local_event(self) -> TickResult:
        """处理本地日常事件"""
        session = self.session

        # 基础修为增长（境界速率 × 10 秒）
        realm_cfg = get_realm_config(session.realm_code)
        base_rate = random.randint(
            realm_cfg["cultivation_rate_min"],
            realm_cfg["cultivation_rate_max"],
        )
        base_gain = base_rate * settings.tick_interval

        # 从事件池抽取渲染
        local = generate_local_event(session.realm_code, session.sin_value)

        total_gain = base_gain + local.cultivation_delta
        session.cultivation += total_gain

        # 更新境界
        new_realm = get_realm_by_cultivation(session.cultivation)
        if new_realm != session.realm_code:
            session.realm_code = new_realm

        # 更新存活时间
        session.survival_seconds += settings.tick_interval

        return TickResult(
            stage=Stage.IDLE,
            log_text=f"【平淡日常】{local.log_text}",
            event_type="LOCAL",
            cultivation=session.cultivation,
            sin_value=session.sin_value,
            luck=session.luck,
            foundation=session.foundation,
            realm=get_realm_name(session.realm_code),
            sin_phase=session.sin_phase(),
        )

    def _trigger_breakthrough(self) -> TickResult:
        """触发大境界突破事件"""
        session = self.session
        next_realm = session.realm_code + 1
        next_name = get_realm_name(next_realm)

        # 随机抓取一份死因
        karma_brief = self._fetch_random_karma()

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

    def _trigger_sin_full(self) -> TickResult:
        """触发天谴满值神罚事件"""
        session = self.session

        karma_brief = self._fetch_random_karma()

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

    def _trigger_heaven_event(self, trigger_source: str) -> TickResult:
        """触发天道因果轨道事件"""
        session = self.session

        karma_brief = self._fetch_random_karma()

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
        on_chunk: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> TickResult:
        """
        处理玩家的对线决策（选择 A/B 或自定义骚话 C）

        内部流程：
        1. 组装 LLM 输入上下文
        2. 后端本地计算 is_dead
        3. 调用 LLM 流式推演剧情
        4. 结算属性变化

        on_chunk: M2 WebSocket 流式回调，每收到一个字符即调用。
                  M1 CLI 不传此参数，保持向后兼容。
        """
        if self.stage != Stage.EVENT_TRIGGER:
            return TickResult(stage=self.stage, log_text="[系统] 当前没有待处理的事件")

        session = self.session
        trigger = self._current_trigger
        self.stage = Stage.LLM_PROCESSING

        # 1. 组装 LLM 上下文
        realm_cfg = get_realm_config(session.realm_code)
        player_ctx = PlayerContextForLLM(
            player_name=session.player_name,
            realm=get_realm_name(session.realm_code),
            realm_code=session.realm_code,
            cultivation=session.cultivation,
            luck=session.luck,
            foundation=session.foundation,
            sin_value=session.sin_value,
            effective_luck=session.effective_luck(),
        )

        # 2. 后端计算 is_dead
        is_ascension = trigger.trigger_type == "ASCENSION"
        is_dead = False

        if is_ascension:
            # 飞升：95% 成功率，但仍有可能陨落成为全服笑柄
            is_dead = random.random() < 0.05
        else:
            is_dead = roll_death_check(
                session.realm_code,
                session.sin_value,
                session.foundation,
            )

        # 3. 构建 LLM 输入
        llm_context = LLMInputContext(
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

        # 4. 调用 LLM（流式 + Retry + Fallback），一次 process_streaming() 完成
        system_prompt = get_persona_prompt(session.heaven_persona)
        full_story = ""
        llm_output = None

        try:
            async for chunk in self.orchestrator.process_streaming(system_prompt, llm_context):
                if isinstance(chunk, LLMOutput):
                    llm_output = chunk
                else:
                    full_story += chunk
        except Exception:
            pass  # streaming 基础设施故障，走 fallback

        if llm_output is None:
            llm_output = self.orchestrator._fallback_resolve(llm_context)

        # 5. 结算
        return self._settle(llm_output, trigger, is_dead, is_ascension, full_story)

    def _settle(
        self,
        llm_output: LLMOutput,
        trigger: EventTrigger,
        backend_is_dead: bool,
        is_ascension: bool,
        full_story: str,
    ) -> TickResult:
        """事件结算"""
        session = self.session
        intercepted = False
        story_text = llm_output.story_text or full_story

        # 因果遮蔽卡拦截
        if backend_is_dead and session.karma_shield > 0:
            session.karma_shield -= 1
            backend_is_dead = False
            intercepted = True
            story_text += "\n\n【因果遮蔽卡触发！宗门太上老祖跨越时空长河，一掌震碎天雷，强行将你捞回！】"

        # 应用属性变化
        if not backend_is_dead:
            changes = llm_output.attribute_changes
            session.cultivation += changes.cultivation
            session.sin_value = max(0, min(
                realm_cfg["sin_max"] if (realm_cfg := get_realm_config(session.realm_code)) else 100,
                session.sin_value + changes.sin_value,
            ))
            session.luck = max(0, min(100, session.luck + changes.luck))
            session.foundation = max(0, min(100, session.foundation + changes.foundation))

            # 更新境界
            new_realm = get_realm_by_cultivation(session.cultivation)
            if new_realm != session.realm_code:
                session.realm_code = new_realm

        # 更新存活时间
        session.survival_seconds += settings.tick_interval

        # 死亡/飞升结算
        heaven_points_earned = 0
        game_over = False

        if backend_is_dead or is_ascension:
            heaven_points_earned = self._calc_heaven_points(session)
            session.heaven_points += heaven_points_earned
            game_over = True

            if is_ascension and not backend_is_dead:
                # 飞升：写入名人堂
                self._immortal_hall.append({
                    "player_name": session.player_name,
                    "player_id": session.player_id,
                    "ascension_title": llm_output.event_title or "飞升大乘",
                    "total_heaven_points": session.heaven_points,
                    "ascended_at": datetime.now().isoformat(),
                })
            else:
                # 暴毙：写入死亡因果池
                dead_record = DeadRecord(
                    player_id=session.player_id,
                    player_name=session.player_name,
                    realm=get_realm_name(session.realm_code),
                    realm_code=session.realm_code,
                    dead_title=llm_output.dead_title or "死于天道裁决",
                    sin_value=session.sin_value,
                    survived_seconds=session.survival_seconds,
                )
                self._dead_registry.append(dead_record)

            self.stage = Stage.GAME_OVER

        else:
            self.stage = Stage.IDLE

        # 重置 PRD 计数器和当前触发
        session.prd_counter = 0
        self._current_trigger = None

        settlement = EventSettlement(
            event_id=trigger.event_id,
            is_dead=backend_is_dead,
            dead_title=llm_output.dead_title if backend_is_dead else "",
            story_text=story_text,
            attribute_changes=llm_output.attribute_changes,
            intercepted_by_shield=intercepted,
            heaven_points_earned=heaven_points_earned,
        )

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

    # ── 超时处理 ─────────────────────────────────────────

    def handle_timeout(self) -> TickResult:
        """
        处理对线超时：自动选 A + 扣除当前修为 10%（道心蒙尘）
        """
        if self.stage != Stage.EVENT_TRIGGER:
            return TickResult(stage=self.stage)

        session = self.session
        penalty = int(session.cultivation * 0.1)
        session.cultivation = max(0, session.cultivation - penalty)

        # 同步调用 submit_decision（简化版，CLI 中会单独处理）
        trigger = self._current_trigger
        trigger.karma_brief += f"\n（因沉默不语，天道降下'道心蒙尘'惩罚，扣除修为 {penalty}）"
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

    # ── 辅助方法 ─────────────────────────────────────────

    def _fetch_random_karma(self) -> str:
        """从死因池中随机抓取一条历史因果"""
        if not self._dead_registry:
            return ""
        record = random.choice(self._dead_registry)
        return f"此地曾有真实玩家【{record.player_name}】因【{record.dead_title}】而死。"

    def _calc_heaven_points(self, session: PlayerState) -> int:
        """结算天道点"""
        raw = (
            session.survival_seconds / settings.heaven_point_survive_divisor
            + session.cultivation * settings.heaven_point_cultivation_multiplier
        )
        return int(raw)

    def get_game_state(self) -> dict:
        """获取当前游戏的完整状态快照（用于断线重连）"""
        if not self.session:
            return {}
        return {
            "stage": self.stage,
            "player": self.session.to_dict(),
            "current_trigger": self._current_trigger.model_dump() if self._current_trigger else None,
        }
