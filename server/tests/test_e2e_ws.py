"""Phase 2A 端到端测试：完整 Action Frame 协议流程 + 多连接隔离 + 错误处理

测试范围：
1. 连接 → 开局 → Tick → 心跳 完整链路
2. 7 种 Action Frame 消息路由验证
3. 下行帧字段级校验（与前端 game.ts 期望对齐）
4. 多连接 session 隔离
5. 错误处理（非法 action、乱序决策、超时等）
"""

import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

import pytest
from fastapi.testclient import TestClient
from server.interface.app import app
from server.application.game_engine import TickResult, Stage
from server.domain.event import EventSettlement, AttributeChanges
from server.config import REALM_CONFIG, settings


# ── 测试辅助 ─────────────────────────────────────────

@pytest.fixture
def fast_tick(monkeypatch):
    """加速 tick 以缩短测试时间"""
    monkeypatch.setattr(settings, "tick_interval", 1)


@pytest.fixture
def client():
    """返回 FastAPI TestClient"""
    return TestClient(app)


def _start_game_with_destiny(ws, player_name="测试修士", include_name=True):
    payload = {"action": "CS_START_GAME"}
    if include_name:
        payload["player_name"] = player_name
    ws.send_json(payload)

    first = ws.receive_json()
    if first["action"] == "SC_DESTINY_OFFER":
        offers = first.get("offers", [])
        assert isinstance(offers, list)
        assert len(offers) == 3
        sign_id = offers[0]["id"]
        select_payload = {
            "action": "CS_SELECT_DESTINY_SIGN",
            "sign_id": sign_id,
        }
        if include_name:
            select_payload["player_name"] = player_name
        ws.send_json(select_payload)
        started = ws.receive_json()
        assert started["action"] == "SC_GAME_LOG"
        return started, first

    assert first["action"] == "SC_GAME_LOG"
    return first, None


# ═══════════════════════════════════════════════════
# 1. 连接 + 开局
# ═══════════════════════════════════════════════════

class TestConnectAndStart:
    """连接建立与开局流程"""

    def test_connect_and_start_game(self, client, fast_tick):
        """CS_START_GAME 应先返回命格签，再进入正式开局帧"""
        with client.websocket_connect("/ws/game?player_id=e2e_p1") as ws:
            resp, offer = _start_game_with_destiny(ws, "端到端测试修士")

            assert resp["action"] == "SC_GAME_LOG"
            assert offer is not None
            assert offer["action"] == "SC_DESTINY_OFFER"
            assert "开局" in resp["log_text"] or "success" in resp["log_text"].lower()

            # 字段级校验：前端 game.ts _onGameLog 依赖这些字段
            assert isinstance(resp["cultivation"], int)
            assert isinstance(resp["sin_value"], int)
            assert isinstance(resp["luck"], int)
            assert isinstance(resp["foundation"], int)
            assert isinstance(resp["realm"], str), f"realm 必须为字符串，实际: {type(resp['realm'])}"
            assert resp["realm"] == "练气期"
            assert resp["sin_phase"] in ("safe", "warning", "danger")
            assert resp["stage"] in ("IDLE", "INIT")

    def test_empty_player_name_defaults(self, client, fast_tick):
        """不传 player_name 应使用默认值"""
        with client.websocket_connect("/ws/game?player_id=e2e_default_name") as ws:
            resp, _ = _start_game_with_destiny(ws, include_name=False)
            assert resp["action"] == "SC_GAME_LOG"

    def test_missing_player_id_autogenerates(self, client, fast_tick):
        """空 player_id 应自动分配并正常开局"""
        with client.websocket_connect("/ws/game?player_id=") as ws:
            resp, _ = _start_game_with_destiny(ws, "无名")
            assert resp["action"] == "SC_GAME_LOG"

    def test_invalid_destiny_selection_returns_error(self, client, fast_tick):
        with client.websocket_connect("/ws/game?player_id=e2e_bad_destiny") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": "命格测试"})
            offer = ws.receive_json()
            assert offer["action"] == "SC_DESTINY_OFFER"

            ws.send_json({"action": "CS_SELECT_DESTINY_SIGN", "sign_id": "not_exists"})
            err = ws.receive_json()
            assert err["action"] == "SC_ERROR"
            assert "命格" in err["message"]


# ═══════════════════════════════════════════════════
# 2. Tick 自动推进
# ═══════════════════════════════════════════════════

class TestTickLoop:
    """自动挂机 tick 下行推送"""

    def test_receives_tick_frame_after_start(self, client, fast_tick):
        """开局后应收到自动 tick 下行帧，可能是普通日志，也可能直接触发天道事件"""
        with client.websocket_connect("/ws/game?player_id=e2e_tick") as ws:
            start_resp, _ = _start_game_with_destiny(ws, "tick 测试")
            assert start_resp["action"] == "SC_GAME_LOG"

            # 等待第一个 tick
            tick_resp = ws.receive_json()
            assert tick_resp["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER")
            assert tick_resp["cultivation"] > 0, f"修为字段异常，实际: {tick_resp['cultivation']}"

    def test_multiple_ticks_accumulate(self, client, fast_tick):
        """连续多个 tick 应持续收到有效帧，且修为不会异常为负"""
        with client.websocket_connect("/ws/game?player_id=e2e_multi_tick") as ws:
            _start_game_with_destiny(ws, "多 tick 测试")

            received = 0
            while received < 3:
                tick = ws.receive_json()
                if tick["action"] == "SC_HEAVEN_EVENT_TRIGGER":
                    ws.send_json({"action": "CS_PLAYER_DECISION", "choice_id": "A"})
                    received += 1
                    assert tick["cultivation"] >= 0, f"第 {received} 个 tick 修为异常"
                    continue
                if tick["action"] == "SC_GAME_LOG":
                    received += 1
                    assert tick["cultivation"] >= 0, f"第 {received} 个 tick 修为异常"
                    continue
                if tick["action"] in ("SC_STORY_STREAM", "SC_EVENT_SETTLEMENT"):
                    continue
                raise AssertionError(f"收到异常 action: {tick.get('action')}")

    def test_tick_fields_match_frontend_contract(self, client, fast_tick):
        """SC_GAME_LOG 字段名与前端 game.ts _onGameLog 期望一致"""
        from unittest.mock import patch

        with client.websocket_connect("/ws/game?player_id=e2e_contract") as ws:
            _start_game_with_destiny(ws, "契约测试")

            # Phase 2D 怨念路由有 15% 概率触发 resentment 事件，强制走正常本地路径
            with patch("server.application.game_engine.random.randint", return_value=50):
                tick = ws.receive_json()

            # 前端 game.ts _onGameLog 读取的字段名
            assert "log_text" in tick, "缺少 log_text"
            assert "cultivation" in tick, "缺少 cultivation"
            assert "sin_value" in tick, "缺少 sin_value"
            assert "sin_max" in tick, "缺少 sin_max"
            assert "luck" in tick, "缺少 luck"
            assert "foundation" in tick, "缺少 foundation"
            assert "realm" in tick, "缺少 realm"
            assert "sin_phase" in tick, "缺少 sin_phase"

            # 类型校验
            assert isinstance(tick["log_text"], str)
            assert isinstance(tick["cultivation"], int)
            assert isinstance(tick["sin_value"], int)
            assert isinstance(tick["sin_max"], int)
            assert isinstance(tick["luck"], int)
            assert isinstance(tick["foundation"], int)
            assert isinstance(tick["realm"], str)
            assert tick["sin_phase"] in ("safe", "warning", "danger")


# ═══════════════════════════════════════════════════
# 3. 心跳
# ═══════════════════════════════════════════════════

class TestHeartbeat:
    """CS_PING / SC_PONG 心跳机制"""

    def test_ping_pong(self, client, fast_tick):
        """CS_PING 应收到 SC_PONG"""
        with client.websocket_connect("/ws/game?player_id=e2e_heartbeat") as ws:
            _start_game_with_destiny(ws, "心跳测试")

            ws.send_json({"action": "CS_PING"})
            pong = ws.receive_json()
            assert pong["action"] == "SC_PONG"

    def test_ping_before_start_returns_error(self, client, fast_tick):
        """开局前发送 PING 应返回 SC_PONG（允许心跳先于开局）"""
        with client.websocket_connect("/ws/game?player_id=e2e_ping_early") as ws:
            ws.send_json({"action": "CS_PING"})
            resp = ws.receive_json()
            assert resp["action"] == "SC_PONG"

    def test_multiple_pings(self, client, fast_tick):
        """连续多次 PING 都应正常响应"""
        with client.websocket_connect("/ws/game?player_id=e2e_ping_multi") as ws:
            _start_game_with_destiny(ws, "多次心跳")

            for _ in range(3):
                ws.send_json({"action": "CS_PING"})
                pong = ws.receive_json()
                assert pong["action"] == "SC_PONG"


# ═══════════════════════════════════════════════════
# 4. 错误处理
# ═══════════════════════════════════════════════════

class TestErrorHandling:
    """非法消息和乱序操作的错误处理"""

    def test_unknown_action(self, client, fast_tick):
        """未知 action 应返回 SC_ERROR"""
        with client.websocket_connect("/ws/game?player_id=e2e_unknown") as ws:
            _start_game_with_destiny(ws, "错误测试")

            ws.send_json({"action": "UNKNOWN_ACTION"})
            err = ws.receive_json()
            assert err["action"] == "SC_ERROR"
            assert "message" in err

    def test_decision_without_event(self, client, fast_tick):
        """无事件时发送 CS_PLAYER_DECISION 应返回 SC_ERROR"""
        with client.websocket_connect("/ws/game?player_id=e2e_no_event") as ws:
            _start_game_with_destiny(ws, "错误决策")

            # 在 IDLE 阶段发送决策（无事件）
            ws.send_json({"action": "CS_PLAYER_DECISION", "choice_id": "A"})
            err = ws.receive_json()
            assert err["action"] == "SC_ERROR"
            assert "没有" in err.get("message", "") or "事件" in err.get("message", "")

    def test_wrong_before_start(self, client, fast_tick):
        """CS_START_GAME 前发送其他 action 应返回 SC_ERROR 提示"""
        with client.websocket_connect("/ws/game?player_id=e2e_wrong_order") as ws:
            ws.send_json({"action": "CS_PLAYER_DECISION", "choice_id": "A"})
            resp = ws.receive_json()
            assert resp["action"] == "SC_ERROR", f"应返回错误，实际: {resp}"
            assert "CS_START_GAME" in resp.get("message", "").upper() or "开局" in resp.get("message", "")

    def test_start_game_twice(self, client, fast_tick):
        """重复发送 CS_START_GAME 应被忽略（已在 IDLE 阶段，不在 INIT 循环中处理）"""
        with client.websocket_connect("/ws/game?player_id=e2e_double_start") as ws:
            start_resp, _ = _start_game_with_destiny(ws, "双开测试")
            assert start_resp["action"] == "SC_GAME_LOG"

            # 再次发送 CS_START_GAME —— 主循环会将其视为未知 action
            ws.send_json({"action": "CS_START_GAME"})
            err = ws.receive_json()
            assert err["action"] == "SC_ERROR", f"重复开局应返回错误，实际: {err}"


# ═══════════════════════════════════════════════════
# 5. 多连接 session 隔离
# ═══════════════════════════════════════════════════

class TestMultiConnection:
    """多个 WebSocket 连接之间的 session 隔离"""

    def test_two_players_independent(self, client, fast_tick):
        """两个玩家应各自拥有独立的 engine，开局不互相干扰"""
        with (
            client.websocket_connect("/ws/game?player_id=e2e_multi_a") as ws_a,
            client.websocket_connect("/ws/game?player_id=e2e_multi_b") as ws_b,
        ):
            # 玩家 A 开局
            resp_a, _ = _start_game_with_destiny(ws_a, "玩家A")
            assert resp_a["action"] == "SC_GAME_LOG"

            # 玩家 B 开局
            resp_b, _ = _start_game_with_destiny(ws_b, "玩家B")
            assert resp_b["action"] == "SC_GAME_LOG"

            # 两玩家的初始属性应不同（运气、根基随机）
            assert resp_a["luck"] != resp_b["luck"] or resp_a["foundation"] != resp_b["foundation"], \
                "两个玩家的初始属性完全相同，疑似未隔离"

    def test_three_players_concurrent(self, client, fast_tick):
        """三个并发玩家均应正常开局并各自收到 tick"""
        with (
            client.websocket_connect("/ws/game?player_id=e2e_c1") as ws1,
            client.websocket_connect("/ws/game?player_id=e2e_c2") as ws2,
            client.websocket_connect("/ws/game?player_id=e2e_c3") as ws3,
        ):
            sockets = [ws1, ws2, ws3]
            for i, ws in enumerate(sockets):
                resp, _ = _start_game_with_destiny(ws, f"并发{i + 1}")
                assert resp["action"] == "SC_GAME_LOG", f"玩家 {i + 1} 开局失败"

            # 每人至少收到 1 个 tick（Phase 2D 怨念路由可能发送不同 action）
            for i, ws in enumerate(sockets):
                tick = ws.receive_json()
                assert tick["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"), \
                    f"玩家 {i + 1} 收到异常 action: {tick.get('action')}"
                assert tick["cultivation"] > 0

    def test_player_disconnect_cleanup(self, client, fast_tick):
        """玩家断开后，连接管理器应正确清理资源"""
        ws = client.websocket_connect("/ws/game?player_id=e2e_disconnect")
        with ws:
            resp, _ = _start_game_with_destiny(ws, "断开测试")
            assert resp["action"] == "SC_GAME_LOG"

        # with 块结束时 ws.close() 自动调用
        # 连接管理器应在 disconnect 中清理
        # 验证方式：同一 player_id 可以重新连接
        with client.websocket_connect("/ws/game?player_id=e2e_disconnect") as ws2:
            resp2, _ = _start_game_with_destiny(ws2, "重连测试")
            assert resp2["action"] == "SC_GAME_LOG"


# ═══════════════════════════════════════════════════
# 6. 下行帧结构校验（EventTrigger / EventSettlement）
# ═══════════════════════════════════════════════════

class TestDownstreamFrameStructure:
    """前端期望的下行帧字段完整性校验"""

    def test_sc_game_log_has_all_frontend_fields(self, client, fast_tick):
        """SC_GAME_LOG 字段覆盖前端 game.ts _onGameLog 所有读取路径"""
        with client.websocket_connect("/ws/game?player_id=e2e_struct_gl") as ws:
            resp, _ = _start_game_with_destiny(ws, "结构测试")
            assert resp["action"] == "SC_GAME_LOG"
            # _onGameLog 读取: log_text, cultivation, sin_value, sin_max, luck, foundation, realm, sin_phase, stage
            for key in ("log_text", "cultivation", "sin_value", "sin_max", "luck", "foundation", "realm", "sin_phase", "stage"):
                assert key in resp, f"SC_GAME_LOG 缺少字段: {key}"
            assert resp["sin_max"] == REALM_CONFIG[1]["sin_max"]

    def test_sc_pong_format(self, client, fast_tick):
        """SC_PONG 格式校验（需先开局再 PING）"""
        with client.websocket_connect("/ws/game?player_id=e2e_struct_pong") as ws:
            _start_game_with_destiny(ws, "PONG格式")
            ws.send_json({"action": "CS_PING"})
            pong = ws.receive_json()
            assert pong["action"] == "SC_PONG"

    def test_sc_error_format(self, client, fast_tick):
        """SC_ERROR 格式校验"""
        with client.websocket_connect("/ws/game?player_id=e2e_struct_err") as ws:
            ws.send_json({"action": "UNKNOWN"})
            err = ws.receive_json()
            assert err["action"] == "SC_ERROR"
            assert "message" in err
            assert isinstance(err["message"], str)

    def test_sc_heaven_event_trigger_structure(self, client, fast_tick):
        """SC_HEAVEN_EVENT_TRIGGER 结构校验（前端 _onEventTrigger 对齐）"""
        # 使用 TestClient 直接测试 engine，手动构造 trigger 帧
        from server.domain.event import EventTrigger
        from server.interface.ws import _build_event_trigger
        from server.application.game_engine import TickResult

        trigger = EventTrigger(
            event_id="evt_test001",
            trigger_type="HEAVEN",
            karma_brief="测试因果",
            fixed_options=[{"id": "A", "text": "选项A"}, {"id": "B", "text": "选项B"}],
            allow_custom_input=True,
            heaven_persona="混沌乐子人",
        )

        # 验证 trigger.model_dump() 字段与前端 _onEventTrigger 期望对齐
        dump = trigger.model_dump()
        assert "event_id" in dump
        assert "trigger_type" in dump
        assert "karma_brief" in dump
        assert "fixed_options" in dump, f"EventTrigger 字段应为 fixed_options，实际: {list(dump.keys())}"
        assert "heaven_persona" in dump

        # 前端读取: trigger.heaven_persona, trigger.trigger_type, trigger.karma_brief, trigger.fixed_options
        for opt in dump["fixed_options"]:
            assert "id" in opt, "fixed_options 每项必须有 id"
            assert "text" in opt, "fixed_options 每项必须有 text"

        result = TickResult(
            stage=Stage.AWAIT_DECISION,
            cultivation=234,
            sin_value=45,
            luck=67,
            foundation=89,
            realm=REALM_CONFIG[4]["name"],
            sin_phase="warning",
            trigger=trigger,
        )
        frame = _build_event_trigger(result)
        assert frame["sin_max"] == REALM_CONFIG[4]["sin_max"]

    def test_sc_event_settlement_structure(self, client, fast_tick):
        """SC_EVENT_SETTLEMENT 结构校验（前端 _onEventSettlement 对齐）"""
        from server.domain.event import EventSettlement, AttributeChanges
        from server.interface.ws import _build_event_settlement

        settlement = EventSettlement(
            event_id="evt_test002",
            is_dead=True,
            dead_title="测试死亡标题",
            story_text="测试剧情文本",
            attribute_changes=AttributeChanges(cultivation=100, sin_value=10),
            intercepted_by_shield=False,
            heaven_points_earned=50,
        )

        dump = settlement.model_dump()
        assert "dead_title" in dump, f"EventSettlement 缺少 dead_title，实际字段: {list(dump.keys())}"
        assert "reason_text" in dump
        assert "verdict_text" in dump
        assert "story_text" in dump
        assert "is_dead" in dump
        assert "attribute_changes" in dump
        assert "heaven_points_earned" in dump

        # 前端 game.ts _onEventSettlement 读取:
        #   settlement.story_text, settlement.dead_title, frame.game_over, frame.heaven_points_earned
        assert dump["dead_title"] == "测试死亡标题"

        result = TickResult(
            stage=Stage.SETTLEMENT,
            cultivation=456,
            sin_value=55,
            luck=40,
            foundation=60,
            realm=REALM_CONFIG[3]["name"],
            sin_phase="danger",
            settlement=settlement,
            heaven_points_earned=50,
        )
        frame = _build_event_settlement(result)
        assert frame["sin_max"] == REALM_CONFIG[3]["sin_max"]


class TestStreamingFallback:
    def test_streaming_falls_back_to_full_story_when_no_chunks(self, client, fast_tick):
        from server.interface import ws as ws_module

        original_submit = ws_module.GameEngine.submit_decision

        async def fake_submit(self, choice_id="A", custom_text="", on_chunk=None):
            return TickResult(
                stage=Stage.IDLE,
                settlement=EventSettlement(
                    event_id="evt_stream_fallback",
                    is_dead=False,
                    dead_title="",
                    story_text="补发全文剧情",
                    attribute_changes=AttributeChanges(),
                    intercepted_by_shield=False,
                    heaven_points_earned=0,
                ),
                cultivation=self.session.cultivation if self.session else 0,
                sin_value=self.session.sin_value if self.session else 0,
                luck=self.session.luck if self.session else 0,
                foundation=self.session.foundation if self.session else 0,
                realm="练气期",
                sin_phase="safe",
                game_over=False,
            )

        try:
            ws_module.GameEngine.submit_decision = fake_submit
            with client.websocket_connect("/ws/game?player_id=e2e_stream_fallback") as ws:
                _start_game_with_destiny(ws, "流式补发")

                from server.interface.app import get_connection_manager
                from server.domain.event import EventTrigger

                engine = get_connection_manager().get_engine("e2e_stream_fallback")
                assert engine is not None
                engine.stage = Stage.EVENT_TRIGGER
                engine._current_trigger = EventTrigger(
                    event_id="evt_stream_fallback",
                    trigger_type="HEAVEN",
                    fixed_options=[{"id": "A", "text": "选项A"}],
                )

                ws.send_json({"action": "CS_PLAYER_DECISION", "choice_id": "A"})

                story_msg = ws.receive_json()
                assert story_msg["action"] == "SC_STORY_STREAM"
                assert story_msg["chunk"] == "补发全文剧情"
                assert story_msg["is_last"] is False

                end_msg = ws.receive_json()
                assert end_msg["action"] == "SC_STORY_STREAM"
                assert end_msg["is_last"] is True

                settlement_msg = ws.receive_json()
                assert settlement_msg["action"] == "SC_EVENT_SETTLEMENT"
        finally:
            ws_module.GameEngine.submit_decision = original_submit


# ═══════════════════════════════════════════════════
# 7. 连接管理器生命周期
# ═══════════════════════════════════════════════════

class TestConnectionManager:
    """连接管理器状态管理"""

    def test_active_count_tracks_connections(self, client, fast_tick):
        """活跃连接数应正确追踪"""
        ws1 = client.websocket_connect("/ws/game?player_id=e2e_count_1")
        ws2 = client.websocket_connect("/ws/game?player_id=e2e_count_2")

        with ws1, ws2:
            _start_game_with_destiny(ws1, "计数1")
            _start_game_with_destiny(ws2, "计数2")

            from server.interface.app import get_connection_manager
            mgr = get_connection_manager()
            assert mgr.active_count == 2, f"应有 2 个活跃连接，实际: {mgr.active_count}"

        # 退出 with 后连接断开
        from server.interface.app import get_connection_manager
        mgr = get_connection_manager()
        assert mgr.active_count == 0, f"清理后应无活跃连接，实际: {mgr.active_count}"


# ═══════════════════════════════════════════════════
# 8. 边界条件
# ═══════════════════════════════════════════════════

class TestEdgeCases:
    """边界条件与鲁棒性"""

    def test_very_long_player_name(self, client, fast_tick):
        """超长道号应正常处理"""
        with client.websocket_connect("/ws/game?player_id=e2e_longname") as ws:
            long_name = "道" * 50
            resp, _ = _start_game_with_destiny(ws, long_name)
            assert resp["action"] == "SC_GAME_LOG"

    def test_empty_json_body(self, client, fast_tick):
        """空 JSON 应返回错误而非崩溃"""
        with client.websocket_connect("/ws/game?player_id=e2e_empty") as ws:
            _start_game_with_destiny(ws, "空消息测试")

            # 发送缺少 action 的消息
            ws.send_json({})
            err = ws.receive_json()
            assert err["action"] == "SC_ERROR"

    def test_chinese_player_name(self, client, fast_tick):
        """中文道号应正常保留"""
        with client.websocket_connect("/ws/game?player_id=e2e_chinese") as ws:
            resp, _ = _start_game_with_destiny(ws, "天道逆修🌟")
            assert resp["action"] == "SC_GAME_LOG"
            assert "天道逆修" in resp["log_text"] or "天道" in resp["log_text"]

    def test_special_characters_in_player_id(self, client, fast_tick):
        """player_id 包含特殊字符应正常处理"""
        player_id = "test_user@domain.com"
        with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            resp, _ = _start_game_with_destiny(ws, "特殊ID")
            assert resp["action"] == "SC_GAME_LOG"
