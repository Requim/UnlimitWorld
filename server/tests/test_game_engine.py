"""
game_engine.py 单元测试：状态机、事件路由、暴毙结算
目标：100% 分支覆盖（mock LLM 控制所有路径）
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from server.application.game_engine import (
    GameEngine,
    Stage,
    EventType,
    TickResult,
    determine_next_event,
)
from server.domain.player import PlayerState, DeadRecord
from server.domain.event import (
    EventTrigger,
    EventSettlement,
    LocalEventResult,
    LLMOutput,
    LLMInputContext,
    AttributeChanges,
)
from server.application.heaven_persona import PERSONA_NAMES
from server.config import REALM_CONFIG, settings


# ══════════════════════════════════════════════════════════
# 测试辅助
# ══════════════════════════════════════════════════════════

async def _mock_async_gen(*args, **kwargs):
    for c in ["a", "b", "c"]:
        yield c


def _default_llm_output():
    return LLMOutput(
        event_title="测试事件",
        story_text="测试剧情文本。",
        is_dead=False,
        dead_title="",
        attribute_changes=AttributeChanges(cultivation=100),
        next_action_required="IDLE",
    )


async def _make_process_streaming(llm_output, should_raise=False):
    """模拟 LLMOrchestrator.process_streaming 的 async generator"""
    if should_raise:
        raise Exception("mock error")
    story = llm_output.story_text
    for char in story:
        yield char
    yield llm_output


def _make_mock_orchestrator(llm_output=None, should_raise=False):
    """构建 mock LLMOrchestrator，正确模拟 process_streaming"""
    mock = MagicMock()
    output = llm_output or _default_llm_output()
    mock.process_streaming = lambda *a, **kw: _make_process_streaming(output, should_raise)
    mock._fallback_resolve = MagicMock(return_value=output)
    mock.client = MagicMock()
    mock.client.chat_stream = _mock_async_gen
    return mock


# ══════════════════════════════════════════════════════════
# determine_next_event 补充测试
# ══════════════════════════════════════════════════════════

class TestDetermineNextEventEdgeCases:
    def test_prd_threshold_exact_match(self):
        result = determine_next_event(1, 100, 0, 60)  # realm_1 threshold=60
        assert result == EventType.PRD_LLM_EVENT

    def test_prd_above_threshold(self):
        result = determine_next_event(1, 100, 0, 100)
        assert result == EventType.PRD_LLM_EVENT

    def test_prd_below_threshold(self):
        result = determine_next_event(1, 100, 0, 30)
        assert result == EventType.LOCAL_EVENT

    def test_ascension_overrides_sin_full(self):
        result = determine_next_event(6, settings.ascension_cultivation, 100, 0)
        assert result == EventType.ASCENSION_EVENT

    def test_sin_full_overrides_prd(self):
        result = determine_next_event(1, 100, 50, 100)
        assert result == EventType.FORCE_HEAVEN_KILL

    def test_realm_7_never_triggers_anything(self):
        result = determine_next_event(7, 100_000_000, 0, 0)
        assert result == EventType.LOCAL_EVENT


# ══════════════════════════════════════════════════════════
# GameEngine.new_game
# ══════════════════════════════════════════════════════════

class TestNewGame:
    def test_default_params(self):
        engine = GameEngine()
        session = engine.new_game()
        assert session.player_name == "无名修士"
        assert session.realm_code == 1
        assert session.cultivation == 100
        assert session.sin_value == 0
        assert session.heaven_persona in PERSONA_NAMES
        assert engine.stage == Stage.IDLE

    def test_custom_name(self):
        engine = GameEngine()
        session = engine.new_game(player_name="张三")
        assert session.player_name == "张三"

    def test_custom_player_id(self):
        engine = GameEngine()
        session = engine.new_game(player_id="custom_123")
        assert session.player_id == "custom_123"

    def test_talent_bonus_applied(self):
        engine = GameEngine()
        session = engine.new_game(talent_bonus={"luck": 10})
        assert session.luck >= 40

    def test_deafness_protocol_stored(self):
        engine = GameEngine()
        session = engine.new_game(deafness_protocol=5)
        assert session.deafness_protocol == 5

    def test_karma_shield_stored(self):
        engine = GameEngine()
        session = engine.new_game(karma_shield=3)
        assert session.karma_shield == 3

    def test_heaven_points_stored(self):
        engine = GameEngine()
        session = engine.new_game(heaven_points=1000)
        assert session.heaven_points == 1000

    def test_resets_current_trigger(self):
        engine = GameEngine()
        engine._current_trigger = EventTrigger(event_id="old", trigger_type="HEAVEN")
        engine.new_game()
        assert engine._current_trigger is None

    def test_prepare_new_game_returns_three_unique_destiny_offers(self):
        engine = GameEngine()
        offers = engine.prepare_new_game("命格修士")
        assert len(offers) == 3
        assert len({item["id"] for item in offers}) == 3
        assert engine.has_pending_destiny_offer() is True

    def test_new_game_applies_destiny_sign_modifiers(self):
        engine = GameEngine()
        session = engine.new_game(destiny_sign_id="fortune_and_disaster")
        assert session.destiny_sign_id == "fortune_and_disaster"
        assert session.destiny_sign_title == "福祸同炉"
        assert session.foundation >= 36
        assert session.sin_value == 10

    def test_prepare_ambition_selection_returns_three_unique_offers(self):
        engine = GameEngine()
        destiny_offers = engine.prepare_new_game("执念修士")
        ambitions = engine.prepare_ambition_selection(destiny_offers[0]["id"])
        assert len(ambitions) == 3
        assert len({item["id"] for item in ambitions}) == 3
        assert engine.has_pending_ambition_offer() is True

    def test_new_game_stores_ambition(self):
        engine = GameEngine()
        session = engine.new_game(ambition_id="taunt_heaven")
        assert session.ambition_id == "taunt_heaven"
        assert session.ambition_title == "嘴硬十回合"
        assert session.ambition_progress == 0
        assert session.ambition_target == 3
        assert session.ambition_progress_label == "自由对线"

    def test_new_game_can_select_extended_persona_pool(self):
        engine = GameEngine()
        with patch("server.application.game_engine.random.choice", return_value="玉律监考官"):
            session = engine.new_game()
        assert session.heaven_persona == "玉律监考官"


# ══════════════════════════════════════════════════════════
# GameEngine.tick — 阶段守卫
# ══════════════════════════════════════════════════════════

class TestTickStageGuard:
    @pytest.mark.asyncio
    async def test_tick_not_in_idle_returns_early(self):
        engine = GameEngine()
        engine.stage = Stage.GAME_OVER
        result = await engine.tick()
        assert result.stage == Stage.GAME_OVER
        assert "不在挂机状态" in result.log_text

    @pytest.mark.asyncio
    async def test_tick_no_session_returns_early(self):
        engine = GameEngine()
        engine.stage = Stage.IDLE
        engine.session = None
        result = await engine.tick()
        assert result.stage == Stage.INIT
        assert "尚未创建" in result.log_text


# ══════════════════════════════════════════════════════════
# GameEngine.tick — 事件路由
# ══════════════════════════════════════════════════════════

class TestTickEventRouting:
    @pytest.mark.asyncio
    async def test_process_local_event(self):
        engine = GameEngine()
        engine.new_game(player_name="测试")
        engine.session.cultivation = 100
        engine.session.sin_value = 0
        engine.session.prd_counter = 0
        engine.session.realm_code = 1

        # Phase 2D 怨念路由有 15% 概率触发 resentment 事件，mock 走纯本地路径
        from unittest.mock import patch
        with patch("server.application.game_engine.random.randint", return_value=50):
            result = await engine.tick()
        assert result.event_type in ("LOCAL", "RESENTMENT_LOCAL")
        assert result.stage == Stage.IDLE
        assert result.cultivation > 0

    @pytest.mark.asyncio
    async def test_destiny_prd_step_delta_has_minimum_floor(self):
        engine = GameEngine()
        engine.new_game(destiny_sign_id="secluded_meditation")
        engine.session.prd_counter = 0

        with patch("server.application.game_engine.random.randint", return_value=2):
            result = await engine.tick()

        assert engine.session.prd_counter >= 1
        assert result.cultivation > 0 or result.event_type in ("RESENTMENT_LOCAL", "RESENTMENT_LLM")

    @pytest.mark.asyncio
    async def test_local_event_advances_survival_time(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 100
        engine.session.sin_value = 0
        engine.session.prd_counter = 0

        old_survival = engine.session.survival_seconds
        await engine.tick()
        assert engine.session.survival_seconds == old_survival + settings.tick_interval

    @pytest.mark.asyncio
    async def test_local_event_realm_change(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 950
        engine.session.realm_code = 1
        engine.session.sin_value = 0
        engine.session.prd_counter = 0

        with patch("server.application.game_engine.generate_local_event") as mock_gen, \
                patch("server.application.game_engine.random.randint", side_effect=[5, 50, 5]):
            mock_gen.return_value = type("LocalResult", (), {
                "log_text": "测试",
                "cultivation_delta": 200,
                "sin_delta": 0,
                "flavor": "normal",
            })()
            result = await engine.tick()
            assert result.cultivation >= 1150

    @pytest.mark.asyncio
    async def test_triggers_ascension(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.realm_code = 6
        engine.session.cultivation = settings.ascension_cultivation

        result = await engine.tick()
        assert result.waiting_for_decision
        assert result.event_type == "ASCENSION"
        assert result.trigger.trigger_type == "ASCENSION"
        assert engine.stage == Stage.EVENT_TRIGGER

    @pytest.mark.asyncio
    async def test_triggers_sin_full(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.sin_value = 100

        result = await engine.tick()
        assert result.waiting_for_decision
        assert result.event_type == "SIN_FULL"
        assert result.sin_phase == "danger"

    @pytest.mark.asyncio
    async def test_triggers_prd_heaven_event(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.prd_counter = 999

        result = await engine.tick()
        assert result.waiting_for_decision
        assert result.event_type == "HEAVEN"
        assert engine.session.prd_counter == 0

    @pytest.mark.asyncio
    async def test_triggers_breakthrough(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 2000
        engine.session.realm_code = 1

        result = await engine.tick()
        assert result.waiting_for_decision
        assert result.event_type == "BREAKTHROUGH"

    @pytest.mark.asyncio
    async def test_prd_increments_every_tick(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 100
        engine.session.sin_value = 0
        old_prd = engine.session.prd_counter

        await engine.tick()
        assert engine.session.prd_counter > old_prd

    @pytest.mark.asyncio
    async def test_local_event_advances_ambition_progress(self):
        engine = GameEngine()
        engine.new_game(ambition_id="taunt_heaven")
        engine.session.prd_counter = 0

        local = LocalEventResult(
            event_id="taunt_local",
            log_text="天道问你服不服。【嘴硬池抉择】你说不服。",
            cultivation_delta=0,
            sin_delta=1,
            event_pool="taunt",
            risk_level="medium",
            ambition_tags=["taunt_heaven"],
            taunt_count=1,
            ambition_progress_delta=1,
            leaderboard_score_delta=8,
        )

        with patch("server.application.game_engine.random.randint", side_effect=[1, 50, 1]), \
                patch("server.application.game_engine.generate_local_event", return_value=local):
            result = await engine.tick()

        assert result.event_type == "LOCAL"
        assert result.event_pool == "taunt"
        assert result.taunt_count == 1
        assert result.ambition_progress == 1
        assert engine.session.ambition_progress == 1


# ══════════════════════════════════════════════════════════
# GameEngine.submit_decision
# ══════════════════════════════════════════════════════════

class TestSubmitDecision:
    @pytest.mark.asyncio
    async def test_wrong_stage_returns_early(self):
        engine = GameEngine()
        engine.new_game()
        result = await engine.submit_decision("A", "")
        assert "没有待处理的事件" in result.log_text

    @pytest.mark.asyncio
    async def test_submit_ascension_survives(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.realm_code = 6
        engine.session.cultivation = settings.ascension_cultivation

        mock_orch = _make_mock_orchestrator()
        engine.orchestrator = mock_orch

        result = await engine.tick()
        assert result.waiting_for_decision

        with patch("random.random", return_value=0.10):
            result = await engine.submit_decision("A", "")
            assert result.settlement is not None

    @pytest.mark.asyncio
    async def test_submit_ascension_dies(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.realm_code = 6
        engine.session.cultivation = settings.ascension_cultivation

        mock_orch = _make_mock_orchestrator(llm_output=LLMOutput(
            event_title="飞升失败",
            story_text="陨落",
            is_dead=True,
            dead_title="飞升陨落",
            attribute_changes=AttributeChanges(),
            next_action_required="GAME_OVER",
        ))
        engine.orchestrator = mock_orch

        result = await engine.tick()
        assert result.waiting_for_decision

        with patch("random.random", return_value=0.01):
            result = await engine.submit_decision("B", "")
            assert result.is_dead is True
            assert result.game_over is True

    @pytest.mark.asyncio
    async def test_submit_normal_event_survives(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.sin_value = 0
        engine.session.foundation = 90

        mock_orch = _make_mock_orchestrator()
        engine.orchestrator = mock_orch
        engine.stage = Stage.EVENT_TRIGGER
        engine._start_time = __import__("time").time()
        engine._current_trigger = EventTrigger(
            event_id="t1", trigger_type="HEAVEN",
            fixed_options=[{"id": "A", "text": "opt"}],
        )

        result = await engine.submit_decision("A", "")
        assert result.settlement is not None

    @pytest.mark.asyncio
    async def test_submit_with_custom_input(self):
        engine = GameEngine()
        engine.new_game()

        mock_orch = _make_mock_orchestrator()
        engine.orchestrator = mock_orch
        engine.stage = Stage.EVENT_TRIGGER
        engine._current_trigger = EventTrigger(
            event_id="t1", trigger_type="HEAVEN",
            fixed_options=[{"id": "A", "text": "opt"}],
        )

        result = await engine.submit_decision("C", "这是我的自定义骚话")
        assert result.settlement is not None

    @pytest.mark.asyncio
    async def test_destiny_custom_text_bonus_applies(self, monkeypatch):
        engine = GameEngine()
        engine.new_game(destiny_sign_id="sharp_tongue")
        monkeypatch.setattr("server.application.game_engine.roll_death_check", lambda *_: False)

        mock_orch = _make_mock_orchestrator(
            LLMOutput(
                event_title="测试事件",
                story_text="测试剧情文本。",
                is_dead=False,
                dead_title="",
                attribute_changes=AttributeChanges(),
                next_action_required="IDLE",
            )
        )
        engine.orchestrator = mock_orch
        engine.stage = Stage.EVENT_TRIGGER
        engine._current_trigger = EventTrigger(
            event_id="t1", trigger_type="HEAVEN",
            fixed_options=[{"id": "A", "text": "opt"}],
        )

        result = await engine.submit_decision("C", "这是我的自定义骚话")
        assert result.heaven_points_earned == 3
        assert engine.session.sin_value == 5

    @pytest.mark.asyncio
    async def test_submit_streams_story_chunks_via_callback(self):
        engine = GameEngine()
        engine.new_game()

        mock_orch = _make_mock_orchestrator()
        engine.orchestrator = mock_orch
        engine.stage = Stage.EVENT_TRIGGER
        engine._current_trigger = EventTrigger(
            event_id="t1", trigger_type="HEAVEN",
            fixed_options=[{"id": "A", "text": "opt"}],
        )

        chunks = []

        async def on_chunk(segment: str, chunk: str):
            chunks.append((segment, chunk))

        result = await engine.submit_decision("A", "", on_chunk=on_chunk)

        assert result.settlement is not None
        assert "".join(piece for segment, piece in chunks if segment in ("reason_text", "story_text")) == result.settlement.reason_text

    @pytest.mark.asyncio
    async def test_submit_llm_exception_falls_back(self):
        engine = GameEngine()
        engine.new_game()

        mock_orch = _make_mock_orchestrator(should_raise=True)
        mock_orch._fallback_resolve = MagicMock(return_value=LLMOutput(
            event_title="降级事件",
            story_text="降级剧情",
            is_dead=False,
            dead_title="",
            attribute_changes=AttributeChanges(cultivation=50),
            next_action_required="IDLE",
        ))
        engine.orchestrator = mock_orch
        engine.stage = Stage.EVENT_TRIGGER
        engine._current_trigger = EventTrigger(
            event_id="t1", trigger_type="HEAVEN",
            fixed_options=[{"id": "A", "text": "opt"}],
        )

        result = await engine.submit_decision("A", "")
        assert result.settlement is not None

    @pytest.mark.asyncio
    async def test_internal_orch_exception_triggers_fallback(self):
        """submit_decision 中 process_streaming 抛异常 → llm_output 为 None → 调用 _fallback_resolve"""
        engine = GameEngine()
        engine.new_game()
        engine.stage = Stage.EVENT_TRIGGER
        engine._current_trigger = EventTrigger(
            event_id="t1", trigger_type="HEAVEN",
            fixed_options=[{"id": "A", "text": "opt"}],
        )

        bad_orch = _make_mock_orchestrator(should_raise=True)
        # should_raise 模式下 process_streaming 抛异常，_fallback_resolve 已在 helper 中设置

        engine.orchestrator = bad_orch

        result = await engine.submit_decision("A", "")
        assert result.settlement is not None
        assert bad_orch._fallback_resolve.called


# ══════════════════════════════════════════════════════════
# GameEngine._settle
# ══════════════════════════════════════════════════════════

class TestSettle:
    def _make_settle_inputs(self, backend_is_dead=False):
        trigger = EventTrigger(event_id="t1", trigger_type="HEAVEN")
        llm_output = LLMOutput(
            event_title="测试",
            story_text="测试故事",
            is_dead=backend_is_dead,
            dead_title="死因" if backend_is_dead else "",
            attribute_changes=AttributeChanges(cultivation=100, sin_value=5),
            next_action_required="GAME_OVER" if backend_is_dead else "IDLE",
        )
        return llm_output, trigger

    @pytest.mark.asyncio
    async def test_settle_alive_continues(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 500
        llm_output, trigger = self._make_settle_inputs(backend_is_dead=False)
        result = await engine._settle(llm_output, trigger, False, False, "测试故事", False)
        assert result.is_dead is False
        assert result.game_over is False
        assert engine.stage == Stage.IDLE
        assert engine.session.cultivation == 600

    @pytest.mark.asyncio
    async def test_settle_dead_game_over(self):
        engine = GameEngine()
        engine.new_game()
        llm_output, trigger = self._make_settle_inputs(backend_is_dead=True)
        result = await engine._settle(llm_output, trigger, True, False, "死了", False)
        assert result.is_dead is True
        assert result.game_over is True
        assert engine.stage == Stage.GAME_OVER
        assert len(engine._dead_list) == 1
        assert engine._dead_list[0].player_name == "无名修士"
        assert result.settlement.epitaph_title == "天道重点观察对象"
        assert result.settlement.leaderboard_type == "death"
        assert result.settlement.leaderboard_score > 0

    @pytest.mark.asyncio
    async def test_settle_ascension_success(self):
        engine = GameEngine()
        engine.new_game()
        llm_output, trigger = self._make_settle_inputs(backend_is_dead=False)
        result = await engine._settle(llm_output, trigger, False, True, "飞升成功", False)
        assert result.game_over is True
        assert result.is_dead is False
        assert result.heaven_points_earned > 0
        assert len(engine._hall_list) == 1
        assert result.settlement.epitaph_title == "飞升案首"
        assert result.settlement.leaderboard_type == "ascension"

    @pytest.mark.asyncio
    async def test_settle_ascension_dies(self):
        engine = GameEngine()
        engine.new_game()
        llm_output = LLMOutput(
            event_title="飞升陨落",
            story_text="陨落",
            is_dead=True,
            dead_title="渡劫失败",
            attribute_changes=AttributeChanges(),
            next_action_required="GAME_OVER",
        )
        trigger = EventTrigger(event_id="t1", trigger_type="ASCENSION")
        result = await engine._settle(llm_output, trigger, True, True, "飞升陨落", False)
        assert result.is_dead is True
        assert len(engine._dead_list) == 1
        assert len(engine._hall_list) == 0

    @pytest.mark.asyncio
    async def test_settle_karma_shield_intercepts_death(self):
        engine = GameEngine()
        engine.new_game(karma_shield=1)
        llm_output, trigger = self._make_settle_inputs(backend_is_dead=True)
        result = await engine._settle(llm_output, trigger, True, False, "原应死亡", False)
        assert result.is_dead is False
        assert result.settlement.intercepted_by_shield is True
        assert engine.session.karma_shield == 0
        assert "因果遮蔽卡" in result.settlement.story_text

    @pytest.mark.asyncio
    async def test_settle_attribute_clamping(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.sin_value = 95
        engine.session.luck = 95
        engine.session.foundation = 95

        llm_output = LLMOutput(
            event_title="测试",
            story_text="测试",
            is_dead=False,
            dead_title="",
            attribute_changes=AttributeChanges(sin_value=20, luck=20, foundation=20),
            next_action_required="IDLE",
        )
        trigger = EventTrigger(event_id="t1", trigger_type="HEAVEN")
        await engine._settle(llm_output, trigger, False, False, "测试", False)
        assert 0 <= engine.session.sin_value <= 100
        assert 0 <= engine.session.luck <= 100
        assert 0 <= engine.session.foundation <= 100

    @pytest.mark.asyncio
    async def test_settle_resets_prd_counter(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.prd_counter = 500
        llm_output, trigger = self._make_settle_inputs()
        await engine._settle(llm_output, trigger, False, False, "测试", False)
        assert engine.session.prd_counter == 0

    @pytest.mark.asyncio
    async def test_settle_clears_current_trigger(self):
        engine = GameEngine()
        engine.new_game()
        engine._current_trigger = EventTrigger(event_id="t1", trigger_type="HEAVEN")
        llm_output, trigger = self._make_settle_inputs()
        await engine._settle(llm_output, trigger, False, False, "测试", False)
        assert engine._current_trigger is None

    @pytest.mark.asyncio
    async def test_settle_realm_change_on_cultivation_gain(self):
        """属性变化导致跨境界"""
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 950
        engine.session.realm_code = 1
        llm_output = LLMOutput(
            event_title="突破",
            story_text="突破",
            is_dead=False,
            dead_title="",
            attribute_changes=AttributeChanges(cultivation=200),
            next_action_required="IDLE",
        )
        trigger = EventTrigger(event_id="t1", trigger_type="HEAVEN")
        await engine._settle(llm_output, trigger, False, False, "突破", False)
        assert engine.session.cultivation >= 1150


# ══════════════════════════════════════════════════════════
# GameEngine.handle_timeout
# ══════════════════════════════════════════════════════════

class TestHandleTimeout:
    def test_wrong_stage_returns_early(self):
        engine = GameEngine()
        result = engine.handle_timeout()
        assert result.stage != Stage.AWAIT_DECISION

    def test_deducts_10_percent_cultivation(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 1000
        engine.stage = Stage.EVENT_TRIGGER
        engine._current_trigger = EventTrigger(event_id="t1", trigger_type="HEAVEN")

        result = engine.handle_timeout()
        assert engine.session.cultivation == 900
        assert "道心蒙尘" in result.log_text

    def test_cultivation_does_not_go_negative(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.cultivation = 0
        engine.stage = Stage.EVENT_TRIGGER
        engine._current_trigger = EventTrigger(event_id="t1", trigger_type="HEAVEN")

        result = engine.handle_timeout()
        assert engine.session.cultivation == 0


# ══════════════════════════════════════════════════════════
# GameEngine 辅助方法
# ══════════════════════════════════════════════════════════

class TestFetchRandomKarma:
    @pytest.mark.asyncio
    async def test_empty_registry_returns_empty_string(self):
        engine = GameEngine()
        result = await engine._fetch_random_karma()
        assert result == ""

    @pytest.mark.asyncio
    async def test_non_empty_registry_returns_formatted_string(self):
        engine = GameEngine()
        engine._dead_list = [
            DeadRecord(
                player_id="p1", player_name="倒霉蛋", realm="练气期",
                realm_code=1, dead_title="摔死了",
            )
        ]
        result = await engine._fetch_random_karma()
        assert "倒霉蛋" in result
        assert "摔死了" in result


class TestCalcHeavenPoints:
    def test_returns_positive_integer(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.survival_seconds = 600
        engine.session.cultivation = 10000
        points = engine._calc_heaven_points(engine.session)
        assert isinstance(points, int)
        assert points > 0

    def test_zero_survival_zero_cultivation(self):
        engine = GameEngine()
        engine.new_game()
        engine.session.survival_seconds = 0
        engine.session.cultivation = 0
        points = engine._calc_heaven_points(engine.session)
        assert points == 0


class TestGetGameState:
    def test_no_session_returns_empty_dict(self):
        engine = GameEngine()
        assert engine.get_game_state() == {}

    def test_with_session_returns_full_state(self):
        engine = GameEngine()
        engine.new_game(player_name="测试")
        state = engine.get_game_state()
        assert state["stage"] == Stage.IDLE
        assert state["player"]["player_name"] == "测试"
        assert state["current_trigger"] is None

    def test_with_active_trigger(self):
        engine = GameEngine()
        engine.new_game()
        engine._current_trigger = EventTrigger(event_id="t1", trigger_type="HEAVEN")
        state = engine.get_game_state()
        assert state["current_trigger"] is not None
        assert state["current_trigger"]["event_id"] == "t1"
