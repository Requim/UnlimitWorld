"""Phase 2A WebSocket 冒烟测试：启动连接、开局、验证 tick 下行帧"""
import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_project_root))

from fastapi.testclient import TestClient
from server.interface.app import app


def main():
    client = TestClient(app)
    player_id = "smoke_p1"

    with client.websocket_connect(f"/ws/game?player_id={player_id}") as ws:

        # 1. 发送开局
        ws.send_json({"action": "CS_START_GAME", "player_name": "冒烟测试修士"})
        resp = ws.receive_json()
        assert resp["action"] == "SC_GAME_LOG"
        assert "success" in resp["log_text"].lower() or "开局" in resp["log_text"]
        print(f"[PASS] CS_START_GAME -> SC_GAME_LOG (stage={resp['stage']})")

        # 2. 验证自动 tick 下行帧（等待第一个 tick）
        try:
            tick_resp = ws.receive_json()
            assert tick_resp["action"] == "SC_GAME_LOG"
            assert tick_resp["cultivation"] > 100  # 修为应该有增长
            print(f"[PASS] Auto-tick → SC_GAME_LOG: cultivation={tick_resp['cultivation']}, sin={tick_resp['sin_value']}")
        except Exception as e:
            print(f"[FAIL] No tick frame received: {e}")

        # 3. 发送 PING 验证心跳
        ws.send_json({"action": "CS_PING"})
        pong = ws.receive_json()
        assert pong["action"] == "SC_PONG"
        print(f"[PASS] CS_PING → SC_PONG")

        # 4. 主动断开
        ws.close()
        print("[PASS] WebSocket disconnect clean")


if __name__ == "__main__":
    main()
