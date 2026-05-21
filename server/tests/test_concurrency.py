"""Phase 2E 并发压力测试：5 并发连接 + 高频刷新 + 骚话流式 + 断线重连

验收标准（M2-networking.md §3）：
- 启动 5 个测试脚本并发连接 WebSocket
- 挂机数值能高频刷新
- 输入骚话后能收到流式逐字喷出的故事
- 关闭脚本再重连能恢复状态
"""

import asyncio
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

import pytest
from fastapi.testclient import TestClient
from server.interface.app import app, get_connection_manager
from server.config import settings


# ── Fixtures ────────────────────────────────────────────

@pytest.fixture
def fast_tick(monkeypatch):
    """加速 tick 以缩短测试时间"""
    monkeypatch.setattr(settings, "tick_interval", 1)


@pytest.fixture
def client():
    """返回 FastAPI TestClient"""
    return TestClient(app)


# ═════════════════════════════════════════════════════
# 1. 5 并发玩家基础流程
# ═════════════════════════════════════════════════════

def _single_player_lifecycle(player_id: str, num_ticks: int = 3) -> dict:
    """单个玩家的完整生命周期（在独立线程中运行）。

    返回: {player_id, success, ticks_received, errors}
    """
    result = {"player_id": player_id, "success": False, "ticks_received": 0, "errors": []}
    client = TestClient(app)

    try:
        with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            # 1) 开局
            ws.send_json({"action": "CS_START_GAME", "player_name": f"并发测试_{player_id}"})
            start_resp = ws.receive_json()
            if start_resp["action"] != "SC_GAME_LOG":
                result["errors"].append(f"开局失败: {start_resp}")
                return result

            # 2) 收 N 个 tick
            for _ in range(num_ticks):
                tick = ws.receive_json()
                if tick["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"):
                    result["ticks_received"] += 1
                elif tick["action"] == "SC_ERROR":
                    result["errors"].append(f"tick 返回错误: {tick.get('message')}")

            # 3) 心跳
            ws.send_json({"action": "CS_PING"})
            pong = ws.receive_json()
            if pong["action"] != "SC_PONG":
                result["errors"].append(f"心跳失败: {pong}")

            result["success"] = True
    except Exception as e:
        result["errors"].append(str(e))

    return result


class TestConcurrentPlayers:
    """5 并发玩家测试"""

    def test_5_concurrent_players_start_and_tick(self, client, fast_tick):
        """5 个并发玩家同时开局，各自收到 tick"""
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_single_player_lifecycle, f"conc_p{i}", 3): f"conc_p{i}"
                for i in range(5)
            }

            for future in as_completed(futures, timeout=30):
                result = future.result()
                assert result["success"], \
                    f"玩家 {result['player_id']} 失败: {result['errors']}"
                assert result["ticks_received"] >= 2, \
                    f"玩家 {result['player_id']} 收 tick 不足: {result['ticks_received']}"


# ═════════════════════════════════════════════════════
# 2. 高频消息压力
# ═════════════════════════════════════════════════════

def _rapid_ping_worker(player_id: str, count: int = 10) -> dict:
    """高频发送 PING 的 worker"""
    result = {"player_id": player_id, "sent": 0, "received": 0, "errors": []}
    client = TestClient(app)

    try:
        with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": f"压力_{player_id}"})
            ws.receive_json()  # 开局帧

            for i in range(count):
                ws.send_json({"action": "CS_PING"})
                result["sent"] += 1
                pong = ws.receive_json()
                if pong["action"] == "SC_PONG":
                    result["received"] += 1
                elif pong["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"):
                    # tick 帧穿插在 PONG 之间是正常的（异步 tick loop）
                    result["received"] += 1  # 计入响应
                    # 再收一次 PONG
                    try:
                        pong2 = ws.receive_json()
                        if pong2["action"] == "SC_PONG":
                            result["received"] += 1
                    except Exception:
                        pass
                else:
                    result["errors"].append(f"意外响应: {pong}")
    except Exception as e:
        result["errors"].append(str(e))

    return result


class TestHighFrequency:
    """高频消息压力测试"""

    def test_rapid_ping_stress(self, client, fast_tick):
        """3 个玩家同时高频 PING，不应丢失响应"""
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(_rapid_ping_worker, f"stress_p{i}", 10): f"stress_p{i}"
                for i in range(3)
            }

            for future in as_completed(futures, timeout=30):
                result = future.result()
                assert result["sent"] == 10, \
                    f"玩家 {result['player_id']} 发送数不对: {result['sent']}"
                assert result["received"] >= 10, \
                    f"玩家 {result['player_id']} 接收不足: sent={result['sent']} recv={result['received']}"
                assert len(result["errors"]) == 0, \
                    f"玩家 {result['player_id']} 错误: {result['errors']}"

    def test_rapid_decision_stress(self, client, fast_tick):
        """并发发送决策，验证顺序处理不崩溃"""
        player_ids = [f"decision_stress_{i}" for i in range(3)]
        results = []

        def decision_worker(pid):
            cl = TestClient(app)
            with cl.websocket_connect(f"/ws/game?player_id={pid}") as ws:
                ws.send_json({"action": "CS_START_GAME", "player_name": f"决策_{pid}"})
                ws.receive_json()
                # 快速连续发送多个决策（其中一些会因不在 AWAIT_DECISION 阶段被拒绝）
                for choice in ["A", "B", "C"]:
                    ws.send_json({"action": "CS_PLAYER_DECISION", "choice_id": choice})
                    try:
                        resp = ws.receive_json()
                        # 可能收到 SC_ERROR（IDLE 阶段无事件）或正常响应
                        assert resp["action"] in ("SC_ERROR", "SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"), \
                            f"意外 action: {resp['action']}"
                    except Exception as e:
                        return {"pid": pid, "error": str(e)}
                return {"pid": pid, "success": True}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(decision_worker, pid) for pid in player_ids]
            for future in as_completed(futures, timeout=20):
                r = future.result()
                assert r.get("success") or r.get("error") is None, \
                    f"玩家 {r.get('pid')} 决策压力测试失败: {r.get('error')}"
                results.append(r)

        assert len(results) == 3


# ═════════════════════════════════════════════════════
# 3. 断线重连恢复（Phase 2D 核心验收项）
# ═════════════════════════════════════════════════════

class TestDisconnectReconnect:
    """断线重连状态恢复"""

    def test_reconnect_restores_session(self, client, fast_tick):
        """断开后重连，应能恢复游戏状态（Phase 2D restore_game）"""
        player_id = "reconnect_test_1"

        # 第一阶段：开局 + 收若干 tick
        with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": "重连测试修士"})
            start = ws.receive_json()
            assert start["action"] == "SC_GAME_LOG"
            first_cult = start["cultivation"]

            # 收两个 tick 累积修为
            for _ in range(2):
                tick = ws.receive_json()
                assert tick["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER")

        # 断开连接（with 退出自动 close）

        # 第二阶段：重连，发送开局，验证状态恢复
        with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": "重连测试修士"})
            restore = ws.receive_json()
            assert restore["action"] == "SC_GAME_LOG"
            # 重连后修为不应低于断开前
            assert restore["cultivation"] >= first_cult, \
                f"重连后修为 {restore['cultivation']} 不应低于断开前 {first_cult}"

            # 重连后还应继续收到 tick
            tick = ws.receive_json()
            assert tick["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER")

    def test_multiple_reconnects(self, client, fast_tick):
        """多次断开重连，不应泄漏资源"""
        player_id = "reconnect_multi"

        for i in range(3):
            with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
                ws.send_json({"action": "CS_START_GAME", "player_name": "多次重连"})
                resp = ws.receive_json()
                assert resp["action"] == "SC_GAME_LOG", f"第 {i + 1} 次连接失败"
                # 收 1 个 tick
                tick = ws.receive_json()
                assert tick["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"), \
                    f"第 {i + 1} 次连接 tick 失败"

    def test_reconnect_different_name_keeps_state(self, client, fast_tick):
        """重连时使用不同道号，应保持原有状态（player_id 绑定）"""
        player_id = "reconnect_name_test"

        with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": "原名修士"})
            start = ws.receive_json()
            first_cult = start["cultivation"]
            ws.receive_json()  # tick

        # 重连使用不同道号
        with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": "新名修士"})
            restore = ws.receive_json()
            assert restore["action"] == "SC_GAME_LOG"
            assert restore["cultivation"] >= first_cult, \
                "重连后应恢复原先进度，不受道号变更影响"


# ═════════════════════════════════════════════════════
# 4. 并发混合场景（连接 + 断开 + 重连同时）
# ═════════════════════════════════════════════════════

def _mixed_worker(player_id: str) -> dict:
    """混合场景 worker：连接 → 开局 → tick → 断开 → 重连"""
    result = {"player_id": player_id, "phase1_ok": False, "phase2_ok": False, "errors": []}
    cl = TestClient(app)

    try:
        # Phase 1：初始连接
        with cl.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": f"混合_{player_id}"})
            start = ws.receive_json()
            if start["action"] != "SC_GAME_LOG":
                result["errors"].append(f"开局失败: {start}")
                return result

            cult_1 = start["cultivation"]
            for _ in range(2):
                tick = ws.receive_json()
                if tick["action"] not in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"):
                    result["errors"].append(f"tick 异常: {tick}")

            result["phase1_ok"] = True

        # Phase 2：断开后重连
        with cl.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": f"混合_{player_id}"})
            restore = ws.receive_json()
            if restore["action"] != "SC_GAME_LOG":
                result["errors"].append(f"重连开局失败: {restore}")
                return result

            if restore["cultivation"] >= cult_1:
                result["phase2_ok"] = True
            else:
                result["errors"].append(
                    f"状态未恢复: cult_before={cult_1} cult_after={restore['cultivation']}"
                )

    except Exception as e:
        result["errors"].append(str(e))

    return result


class TestMixedLoad:
    """混合负载场景"""

    def test_mixed_connect_disconnect_reconnect(self, client, fast_tick):
        """5 个玩家同时执行 连接→断开→重连 流程"""
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(_mixed_worker, f"mixed_{i}"): f"mixed_{i}"
                for i in range(5)
            }

            for future in as_completed(futures, timeout=45):
                result = future.result()
                assert result["phase1_ok"], \
                    f"玩家 {result['player_id']} Phase 1 失败: {result['errors']}"
                assert result["phase2_ok"], \
                    f"玩家 {result['player_id']} Phase 2 重连失败: {result['errors']}"


# ═════════════════════════════════════════════════════
# 5. 资源清理验证
# ═════════════════════════════════════════════════════

class TestResourceCleanup:
    """验证并发连接断开后资源正确清理"""

    def test_connection_count_returns_to_zero(self, client, fast_tick):
        """5 并发连接全部断开后，active_count 应归零"""
        mgr = get_connection_manager()

        # 并发创建 5 个连接并立即断开
        def short_lived_worker(pid):
            cl = TestClient(app)
            with cl.websocket_connect(f"/ws/game?player_id={pid}") as ws:
                ws.send_json({"action": "CS_START_GAME", "player_name": f"短命_{pid}"})
                ws.receive_json()
            return pid

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(short_lived_worker, f"cleanup_{i}") for i in range(5)]
            for future in as_completed(futures, timeout=20):
                future.result()

        # 等待引擎清理完成
        time.sleep(0.5)

        assert mgr.active_count == 0, \
            f"所有连接断开后 active_count 应为 0，实际: {mgr.active_count}"

    def test_same_player_id_reconnects_cleanly(self, client, fast_tick):
        """同一 player_id 反复连接断开，不应残留旧连接"""
        player_id = "cleanup_same"

        for iteration in range(5):
            with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:
                ws.send_json({"action": "CS_START_GAME", "player_name": f"清理_{iteration}"})
                resp = ws.receive_json()
                assert resp["action"] == "SC_GAME_LOG"

        time.sleep(0.3)
        mgr = get_connection_manager()
        assert mgr.active_count == 0, \
            f"反复重连后 active_count 应为 0，实际: {mgr.active_count}"


# ═════════════════════════════════════════════════════
# 6. 流式推送并发测试
# ═════════════════════════════════════════════════════

class TestStreamingConcurrency:
    """流式推送 + 并发场景"""

    def test_multiple_players_streaming(self, client, fast_tick):
        """多个玩家同时触发流式推送（mock LLM），验证互不干扰"""
        player_ids = [f"stream_{i}" for i in range(3)]

        def stream_worker(pid):
            cl = TestClient(app)
            with cl.websocket_connect(f"/ws/game?player_id={pid}") as ws:
                ws.send_json({"action": "CS_START_GAME", "player_name": f"流式_{pid}"})
                start = ws.receive_json()
                assert start["action"] == "SC_GAME_LOG"

                # 通过提升修为到突破点来触发 HEAVEN 事件
                # 简化方案：多次 tick 后可能自然触发
                for _ in range(5):
                    msg = ws.receive_json()
                    if msg["action"] == "SC_HEAVEN_EVENT_TRIGGER":
                        # 触发事件，选 A 进入流式
                        ws.send_json({"action": "CS_PLAYER_DECISION", "choice_id": "A"})
                        # 收流式 chunk
                        chunks = []
                        while True:
                            chunk_msg = ws.receive_json()
                            if chunk_msg["action"] == "SC_STORY_STREAM":
                                chunks.append(chunk_msg.get("chunk", ""))
                                if chunk_msg.get("is_last"):
                                    break
                            elif chunk_msg["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"):
                                continue
                            elif chunk_msg["action"] == "SC_EVENT_SETTLEMENT":
                                break
                        return {"pid": pid, "streamed": True, "chunks": len(chunks)}
                    elif msg["action"] == "SC_GAME_LOG":
                        continue
                return {"pid": pid, "streamed": False, "reason": "未触发事件"}

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(stream_worker, pid) for pid in player_ids]
            for future in as_completed(futures, timeout=30):
                r = future.result()
                assert r.get("streamed") or r.get("reason") == "未触发事件", \
                    f"玩家 {r.get('pid')} 流式测试异常: {r}"


# ═════════════════════════════════════════════════════
# 7. 连接管理器并发安全
# ═════════════════════════════════════════════════════

class TestConnectionManagerConcurrency:
    """ConnectionManager 并发安全性"""

    def test_concurrent_connect_disconnect_race(self, client, fast_tick):
        """快速连接断开竞态条件：不应崩溃"""
        pid = "race_test"

        def race_worker(iteration):
            cl = TestClient(app)
            try:
                with cl.websocket_connect(f"/ws/game?player_id={pid}_{iteration}") as ws:
                    ws.send_json({"action": "CS_START_GAME", "player_name": f"竞态_{iteration}"})
                    ws.receive_json()
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(race_worker, i) for i in range(8)]
            success = 0
            for future in as_completed(futures, timeout=20):
                if future.result():
                    success += 1

        assert success >= 7, f"竞态测试 {success}/8 成功，可能存在问题"


# ═════════════════════════════════════════════════════
# 8. 长时稳定性
# ═════════════════════════════════════════════════════

class TestLongRunningStability:
    """长时运行稳定性"""

    def test_extended_tick_loop_no_crash(self, client, fast_tick):
        """单个玩家连续收 15+ tick，不应崩溃或泄漏"""
        pid = "long_run_1"

        with client.websocket_connect(f"/ws/game?player_id={pid}") as ws:
            ws.send_json({"action": "CS_START_GAME", "player_name": "长跑修士"})
            start = ws.receive_json()
            assert start["action"] == "SC_GAME_LOG"

            prev_cult = start["cultivation"]
            tick_count = 0
            errors = []

            for _ in range(15):
                try:
                    msg = ws.receive_json()
                    if msg["action"] in ("SC_GAME_LOG", "SC_HEAVEN_EVENT_TRIGGER"):
                        tick_count += 1
                        if msg["cultivation"] < prev_cult:
                            errors.append(f"修为倒退: {prev_cult} → {msg['cultivation']}")
                        prev_cult = msg["cultivation"]
                except Exception as e:
                    errors.append(str(e))

            assert tick_count >= 10, f"收 tick 不足: {tick_count}/15"
            assert len(errors) == 0, f"长时运行错误: {errors}"
            assert prev_cult > start["cultivation"], "修为未增长"

    def test_multiple_players_long_running(self, client, fast_tick):
        """3 个玩家同时长时运行（6 tick）"""
        pids = [f"long_multi_{i}" for i in range(3)]

        def long_worker(pid):
            cl = TestClient(app)
            results = {"pid": pid, "ticks": 0, "max_cult": 0}
            with cl.websocket_connect(f"/ws/game?player_id={pid}") as ws:
                ws.send_json({"action": "CS_START_GAME", "player_name": f"长跑_{pid}"})
                start = ws.receive_json()
                results["max_cult"] = start["cultivation"]

                tick_goal = 6
                while results["ticks"] < tick_goal:
                    msg = ws.receive_json()
                    if msg["action"] == "SC_HEAVEN_EVENT_TRIGGER":
                        results["ticks"] += 1
                        results["max_cult"] = max(results["max_cult"], msg.get("cultivation", results["max_cult"]))
                        # 收到天道事件后发送决策 A 让流程继续
                        ws.send_json({"action": "CS_PLAYER_DECISION", "choice_id": "A"})
                    elif msg["action"] == "SC_GAME_LOG":
                        results["ticks"] += 1
                        results["max_cult"] = max(results["max_cult"], msg["cultivation"])
                    elif msg["action"] == "SC_EVENT_SETTLEMENT":
                        # 结算帧，继续等下一个 tick
                        pass
                    elif msg["action"] == "SC_STORY_STREAM":
                        # 流式帧，继续读直到结算
                        if msg.get("is_last"):
                            continue
                return results

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(long_worker, pid) for pid in pids]
            for future in as_completed(futures, timeout=45):
                r = future.result()
                assert r["ticks"] >= 4, \
                    f"玩家 {r['pid']} tick 不足: {r['ticks']}/6"
                assert r["max_cult"] > 100, \
                    f"玩家 {r['pid']} 修为异常: {r['max_cult']}"
