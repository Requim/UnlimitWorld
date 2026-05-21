"""
WebSocket 路由 + 连接管理 + 每连接 tick loop

M2 网络层核心：Action Frame 协议路由、自动挂机循环、LLM 流式推送。
每个 WebSocket 连接拥有独立的 GameEngine 实例（session 隔离）。
"""

import asyncio
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from server.config import settings
from server.domain.player import PlayerState, get_realm_name
from server.domain.event import EventTrigger, EventSettlement
from server.application.game_engine import GameEngine, Stage, TickResult
from server.infrastructure.llm_client import LLMOrchestrator

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
# Action Frame 常量
# ═══════════════════════════════════════════════════════════════

class Action:
    CS_START_GAME = "CS_START_GAME"
    CS_PING = "CS_PING"
    CS_PLAYER_DECISION = "CS_PLAYER_DECISION"
    SC_GAME_LOG = "SC_GAME_LOG"
    SC_HEAVEN_EVENT_TRIGGER = "SC_HEAVEN_EVENT_TRIGGER"
    SC_STORY_STREAM = "SC_STORY_STREAM"
    SC_EVENT_SETTLEMENT = "SC_EVENT_SETTLEMENT"
    SC_PONG = "SC_PONG"
    SC_ERROR = "SC_ERROR"


# ═══════════════════════════════════════════════════════════════
# 连接管理器
# ═══════════════════════════════════════════════════════════════

class ConnectionManager:
    """管理所有活跃 WebSocket 连接及其 GameEngine 实例"""

    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._engines: dict[str, GameEngine] = {}
        self._tick_tasks: dict[str, asyncio.Task] = {}

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def connect(self, player_id: str, ws: WebSocket) -> GameEngine:
        await ws.accept()
        engine = GameEngine()
        self._connections[player_id] = ws
        self._engines[player_id] = engine
        return engine

    async def disconnect(self, player_id: str):
        task = self._tick_tasks.pop(player_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        ws = self._connections.pop(player_id, None)
        if ws:
            try:
                await ws.close()
            except Exception:
                pass

        self._engines.pop(player_id, None)

    def get_engine(self, player_id: str) -> Optional[GameEngine]:
        return self._engines.get(player_id)

    def set_tick_task(self, player_id: str, task: asyncio.Task):
        self._tick_tasks[player_id] = task

    async def shutdown(self):
        for player_id in list(self._connections.keys()):
            await self.disconnect(player_id)


# ═══════════════════════════════════════════════════════════════
# 下行帧构造（纯函数）
# ═══════════════════════════════════════════════════════════════

def _build_game_log(result: TickResult) -> dict:
    return {
        "action": Action.SC_GAME_LOG,
        "log_text": result.log_text,
        "cultivation": result.cultivation,
        "sin_value": result.sin_value,
        "luck": result.luck,
        "foundation": result.foundation,
        "realm": result.realm,
        "sin_phase": result.sin_phase,
        "stage": result.stage,
    }


def _build_event_trigger(result: TickResult) -> dict:
    return {
        "action": Action.SC_HEAVEN_EVENT_TRIGGER,
        "trigger": result.trigger.model_dump(),
        "cultivation": result.cultivation,
        "sin_value": result.sin_value,
        "luck": result.luck,
        "foundation": result.foundation,
        "realm": result.realm,
        "sin_phase": result.sin_phase,
    }


def _build_story_stream(chunk: str, is_last: bool = False) -> dict:
    return {
        "action": Action.SC_STORY_STREAM,
        "chunk": chunk,
        "is_last": is_last,
    }


def _build_event_settlement(result: TickResult) -> dict:
    return {
        "action": Action.SC_EVENT_SETTLEMENT,
        "settlement": result.settlement.model_dump() if result.settlement else None,
        "cultivation": result.cultivation,
        "sin_value": result.sin_value,
        "luck": result.luck,
        "foundation": result.foundation,
        "realm": result.realm,
        "sin_phase": result.sin_phase,
        "game_over": result.game_over,
        "heaven_points_earned": result.heaven_points_earned,
    }


# ═══════════════════════════════════════════════════════════════
# WebSocket 路由
# ═══════════════════════════════════════════════════════════════

@router.websocket("/ws/game")
async def game_websocket(
    ws: WebSocket,
    player_id: str = Query("", description="玩家 ID，空则自动分配"),
):
    from server.interface.app import get_connection_manager

    mgr = get_connection_manager()
    engine = await mgr.connect(player_id, ws)

    try:
        # 阶段 0：等待 CS_START_GAME
        await _handle_lifecycle(ws, engine, mgr, player_id)
    except WebSocketDisconnect:
        pass
    finally:
        await mgr.disconnect(player_id)


async def _handle_lifecycle(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
):
    """处理单个玩家的完整生命周期：START → tick loop → decision → GAME_OVER"""

    # ── 等待开局 ──
    while engine.stage == Stage.INIT:
        try:
            data = await asyncio.wait_for(ws.receive_json(), timeout=120.0)
        except asyncio.TimeoutError:
            await ws.send_json({"action": Action.SC_ERROR, "message": "等待开局超时，连接关闭"})
            return

        if data.get("action") != Action.CS_START_GAME:
            await ws.send_json({"action": Action.SC_ERROR, "message": "请先发送 CS_START_GAME"})
            continue

        player_name = data.get("player_name", "无名修士")
        session = engine.new_game(player_name=player_name, player_id=player_id)

        await ws.send_json({
            "action": "SC_GAME_LOG",
            "log_text": f"[开局成功] 天道人格：【{session.heaven_persona}】",
            "cultivation": session.cultivation,
            "sin_value": session.sin_value,
            "luck": session.luck,
            "foundation": session.foundation,
            "realm": get_realm_name(session.realm_code),
            "sin_phase": session.sin_phase(),
            "stage": engine.stage,
        })

    # ── 主循环：tick 自动推进 + 消息接收 ──
    tick_task = asyncio.create_task(_tick_loop(ws, engine))
    mgr.set_tick_task(player_id, tick_task)

    try:
        while engine.stage != Stage.GAME_OVER:
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            action = data.get("action", "")

            if action == Action.CS_PING:
                await ws.send_json({"action": Action.SC_PONG})

            elif action == Action.CS_PLAYER_DECISION:
                if engine.stage != Stage.EVENT_TRIGGER:
                    await ws.send_json({"action": Action.SC_ERROR, "message": "当前没有待处理的事件"})
                    continue

                choice_id = data.get("choice_id", "A")
                custom_text = data.get("custom_text", "")

                # 流式推送 chunk → SC_STORY_STREAM
                async def on_chunk(chunk: str):
                    await ws.send_json(_build_story_stream(chunk, is_last=False))

                result = await engine.submit_decision(
                    choice_id=choice_id,
                    custom_text=custom_text,
                    on_chunk=on_chunk,
                )

                # 将结算中的 story_text 逐段流式推送给前端（打字机效果）
                story = result.settlement.story_text if result.settlement else ""
                if story:
                    chunk_size = 4
                    for i in range(0, len(story), chunk_size):
                        await ws.send_json(
                            _build_story_stream(story[i:i + chunk_size], is_last=False)
                        )
                        await asyncio.sleep(0.04)

                # 流式结束标记
                await ws.send_json(_build_story_stream("", is_last=True))

                # 发送结算帧
                await ws.send_json(_build_event_settlement(result))

            else:
                await ws.send_json({"action": Action.SC_ERROR, "message": f"未知 action: {action}"})

    except WebSocketDisconnect:
        pass
    finally:
        tick_task.cancel()
        try:
            await tick_task
        except asyncio.CancelledError:
            pass


async def _tick_loop(ws: WebSocket, engine: GameEngine):
    """自动挂机循环：每 tick_interval 秒推进一次 tick，下行推送 SC_GAME_LOG / SC_HEAVEN_EVENT_TRIGGER"""
    while engine.stage != Stage.GAME_OVER:
        if engine.stage == Stage.IDLE:
            await asyncio.sleep(settings.tick_interval)
            if engine.stage != Stage.IDLE:
                continue  # 休眠期间状态已改变（如收到决策消息）

            result = await engine.tick()

            if result.waiting_for_decision:
                await ws.send_json(_build_event_trigger(result))
            elif result.game_over:
                await ws.send_json(_build_event_settlement(result))
            else:
                await ws.send_json(_build_game_log(result))

        elif engine.stage == Stage.EVENT_TRIGGER:
            # 等待玩家决策，由消息接收协程处理
            await asyncio.sleep(1.0)

        elif engine.stage == Stage.LLM_PROCESSING:
            # submit_decision 正在处理中
            await asyncio.sleep(0.1)

        else:
            await asyncio.sleep(0.1)
