"""
WebSocket 路由 + 连接管理 + 每连接 tick loop

M2 网络层核心：Action Frame 协议路由、自动挂机循环、LLM 流式推送。
每个 WebSocket 连接拥有独立的 GameEngine 实例（session 隔离）。

Phase 2D：注入 SharedState + 超时检测 + 断线重连 + 会话持久化。
Phase 3A：msgSecCheck 内容安全审查。
"""

import asyncio
import json
import logging
import random
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from server.config import REALM_CONFIG, settings
from server.domain.player import PlayerState, ActiveSession, get_realm_name
from server.domain.event import EventTrigger, EventSettlement
from server.application.game_engine import GameEngine, Stage, TickResult
from server.infrastructure.llm_client import LLMOrchestrator

router = APIRouter()
logger = logging.getLogger("uvicorn")


# ═══════════════════════════════════════════════════════════════
# Action Frame 常量
# ═══════════════════════════════════════════════════════════════

class Action:
    CS_START_GAME = "CS_START_GAME"
    CS_SELECT_DESTINY_SIGN = "CS_SELECT_DESTINY_SIGN"
    CS_SELECT_AMBITION = "CS_SELECT_AMBITION"
    CS_CHOOSE_MAP_NODE = "CS_CHOOSE_MAP_NODE"
    CS_GET_RUN_MAP = "CS_GET_RUN_MAP"
    CS_PING = "CS_PING"
    CS_PLAYER_DECISION = "CS_PLAYER_DECISION"
    SC_DESTINY_OFFER = "SC_DESTINY_OFFER"
    SC_AMBITION_OFFER = "SC_AMBITION_OFFER"
    SC_RUN_MAP = "SC_RUN_MAP"
    SC_GAME_LOG = "SC_GAME_LOG"
    SC_HEAVEN_EVENT_TRIGGER = "SC_HEAVEN_EVENT_TRIGGER"
    SC_STORY_STREAM = "SC_STORY_STREAM"
    SC_EVENT_SETTLEMENT = "SC_EVENT_SETTLEMENT"
    SC_PONG = "SC_PONG"
    SC_ERROR = "SC_ERROR"


def _get_sin_max_by_realm_name(realm_name: str) -> int:
    for cfg in REALM_CONFIG.values():
        if cfg["name"] == realm_name:
            return cfg["sin_max"]
    return REALM_CONFIG[1]["sin_max"]


# ═══════════════════════════════════════════════════════════════
# 连接管理器
# ═══════════════════════════════════════════════════════════════

class ConnectionManager:
    """管理所有活跃 WebSocket 连接及其 GameEngine 实例。

    Phase 2D：持有 SharedState 引用，在创建 GameEngine 时注入。
    """

    def __init__(
        self,
        dead_registry=None,
        immortal_hall=None,
        redis_client=None,
        active_session_repo=None,
        account_repo=None,
        leaderboard_repo=None,
        karma_trace_repo=None,
    ):
        self._connections: dict[str, WebSocket] = {}
        self._engines: dict[str, GameEngine] = {}
        self._tick_tasks: dict[str, asyncio.Task] = {}

        # Phase 2D：全服共享状态引用
        self._dead_registry = dead_registry
        self._immortal_hall = immortal_hall
        self._redis = redis_client
        self._active_session_repo = active_session_repo
        self._account_repo = account_repo  # Phase 3B：商店道具生效
        self._leaderboard_repo = leaderboard_repo
        self._karma_trace_repo = karma_trace_repo

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def connect(self, player_id: str, ws: WebSocket) -> GameEngine:
        await ws.accept()
        engine = GameEngine(
            dead_registry=self._dead_registry,
            immortal_hall=self._immortal_hall,
        )
        self._connections[player_id] = ws
        self._engines[player_id] = engine
        return engine

    async def disconnect(self, player_id: str):
        # 取消 tick 任务
        task = self._tick_tasks.pop(player_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Phase 2D：断开前保存活跃会话（用于重连恢复）
        engine = self._engines.get(player_id)
        if engine and engine.session and engine.stage != Stage.GAME_OVER:
            await self._save_active_session(player_id, engine)

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

    # ── Phase 2D：会话持久化与重连 ──

    async def try_restore_session(self, player_id: str) -> dict | None:
        """尝试从 active_session 表恢复玩家会话快照。"""
        if self._active_session_repo:
            session = await self._active_session_repo.get(player_id)
            if session and session.session_json:
                try:
                    return json.loads(session.session_json)
                except (json.JSONDecodeError, TypeError):
                    pass
        return None

    async def _save_active_session(self, player_id: str, engine: GameEngine):
        """持久化当前游戏状态到 active_session 表"""
        if not self._active_session_repo:
            return
        state = engine.get_game_state()
        if not state:
            return
        try:
            session_data = ActiveSession(
                player_id=player_id,
                session_json=json.dumps(state, default=str),
                stage=engine.stage,
                trigger_json=json.dumps(state.get("current_trigger"), default=str)
                if state.get("current_trigger") else None,
            )
            await self._active_session_repo.upsert(session_data)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
# 下行帧构造（纯函数）
# ═══════════════════════════════════════════════════════════════

def _build_game_log(result: TickResult) -> dict:
    return {
        "action": Action.SC_GAME_LOG,
        "log_text": result.log_text,
        "cultivation": result.cultivation,
        "sin_value": result.sin_value,
        "sin_max": _get_sin_max_by_realm_name(result.realm),
        "luck": result.luck,
        "foundation": result.foundation,
        "realm": result.realm,
        "sin_phase": result.sin_phase,
        "stage": result.stage,
        "event_pool": result.event_pool,
        "risk_level": result.risk_level,
        "chosen_choice": result.chosen_choice,
        "ambition_progress": result.ambition_progress,
        "ambition_target": result.ambition_target,
        "ambition_progress_label": result.ambition_progress_label,
        "leaderboard_score_delta": result.leaderboard_score_delta,
        "taunt_count": result.taunt_count,
        "gamble_survive_count": result.gamble_survive_count,
        "karma_pollution_score": result.karma_pollution_score,
        "death_drama_score": result.death_drama_score,
        "karma_trace_hook": result.karma_trace_hook,
        "node_id": result.node_id,
        "node_type": result.node_type,
        "route_label": result.route_label,
    }


def _empty_phase3k_log_fields() -> dict:
    """补齐手写 SC_GAME_LOG 的 3K 可选字段。"""
    return {
        "event_pool": "",
        "risk_level": "",
        "chosen_choice": None,
        "leaderboard_score_delta": 0,
        "taunt_count": 0,
        "gamble_survive_count": 0,
        "karma_pollution_score": 0,
        "death_drama_score": 0,
        "karma_trace_hook": "",
        "node_id": "",
        "node_type": "",
        "route_label": "",
    }


def _build_run_map(engine: GameEngine) -> dict:
    """构造当前 roguelike 路线地图下行帧。"""
    return {
        "action": Action.SC_RUN_MAP,
        "run_map": engine.get_run_map_snapshot(),
    }


def _build_destiny_offer(offers: list[dict], player_name: str) -> dict:
    return {
        "action": Action.SC_DESTINY_OFFER,
        "player_name": player_name,
        "offers": offers,
    }


def _build_ambition_offer(offers: list[dict], player_name: str, destiny_sign_id: str) -> dict:
    return {
        "action": Action.SC_AMBITION_OFFER,
        "player_name": player_name,
        "destiny_sign_id": destiny_sign_id,
        "offers": offers,
    }


def _build_event_trigger(result: TickResult) -> dict:
    return {
        "action": Action.SC_HEAVEN_EVENT_TRIGGER,
        "trigger": result.trigger.model_dump(),
        "cultivation": result.cultivation,
        "sin_value": result.sin_value,
        "sin_max": _get_sin_max_by_realm_name(result.realm),
        "luck": result.luck,
        "foundation": result.foundation,
        "realm": result.realm,
        "sin_phase": result.sin_phase,
    }


def _build_story_stream(chunk: str, is_last: bool = False, segment: str = "reason_text") -> dict:
    return {
        "action": Action.SC_STORY_STREAM,
        "segment": segment,
        "chunk": chunk,
        "is_last": is_last,
    }


def _build_event_settlement(result: TickResult) -> dict:
    return {
        "action": Action.SC_EVENT_SETTLEMENT,
        "settlement": result.settlement.model_dump() if result.settlement else None,
        "cultivation": result.cultivation,
        "sin_value": result.sin_value,
        "sin_max": _get_sin_max_by_realm_name(result.realm),
        "luck": result.luck,
        "foundation": result.foundation,
        "realm": result.realm,
        "sin_phase": result.sin_phase,
        "game_over": result.game_over,
        "heaven_points_earned": result.heaven_points_earned,
    }


def _build_session_log(session: PlayerState, stage: str, log_text: str) -> dict:
    return {
        "action": Action.SC_GAME_LOG,
        "log_text": log_text,
        "cultivation": session.cultivation,
        "sin_value": session.sin_value,
        "sin_max": REALM_CONFIG[session.realm_code]["sin_max"],
        "luck": session.luck,
        "foundation": session.foundation,
        "realm": get_realm_name(session.realm_code),
        "sin_phase": session.sin_phase(),
        "stage": stage,
        "destiny_sign_title": session.destiny_sign_title,
        "ambition_title": session.ambition_title,
        "ambition_progress": session.ambition_progress,
        "ambition_target": session.ambition_target,
        "ambition_progress_label": session.ambition_progress_label,
        **_empty_phase3k_log_fields(),
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
    """处理单个玩家的完整生命周期：START（含重连）→ tick loop → decision → GAME_OVER"""
    await _wait_for_game_start(ws, engine, mgr, player_id)
    if engine.stage == Stage.INIT:
        return
    tick_task = asyncio.create_task(_tick_loop(ws, engine, mgr, player_id))
    mgr.set_tick_task(player_id, tick_task)
    try:
        while engine.stage != Stage.GAME_OVER:
            if await _handle_runtime_timeout(ws, engine, mgr, player_id):
                continue
            data = await _receive_runtime_frame(ws)
            if data is not None:
                await _handle_runtime_message(ws, engine, mgr, player_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        tick_task.cancel()
        try:
            await tick_task
        except asyncio.CancelledError:
            pass


async def _wait_for_game_start(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
):
    while engine.stage == Stage.INIT:
        data = await _receive_start_frame(ws)
        if data is None:
            return
        action = data.get("action")
        if action == Action.CS_PING:
            await ws.send_json({"action": Action.SC_PONG})
        elif action == Action.CS_START_GAME:
            await _handle_start_game(ws, engine, mgr, player_id, data)
        elif action == Action.CS_SELECT_DESTINY_SIGN:
            await _handle_select_destiny(ws, engine, data)
        elif action == Action.CS_SELECT_AMBITION:
            await _handle_select_ambition(ws, engine, mgr, player_id, data)
        else:
            await ws.send_json({"action": Action.SC_ERROR, "message": "请先发送 CS_START_GAME"})


async def _handle_runtime_timeout(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
) -> bool:
    if not engine.is_decision_timeout():
        return False
    result = await engine.auto_timeout_submit()
    await ws.send_json(_build_story_stream("", is_last=True))
    await ws.send_json(_build_event_settlement(result))
    await ws.send_json(_build_run_map(engine))
    await _sync_account_after_settlement(mgr, player_id, engine, result)
    await mgr._save_active_session(player_id, engine)
    return True


async def _receive_runtime_frame(ws: WebSocket) -> dict | None:
    try:
        return await asyncio.wait_for(ws.receive_json(), timeout=1.0)
    except asyncio.TimeoutError:
        return None


async def _receive_start_frame(ws: WebSocket) -> dict | None:
    try:
        return await asyncio.wait_for(ws.receive_json(), timeout=120.0)
    except asyncio.TimeoutError:
        await ws.send_json({"action": Action.SC_ERROR, "message": "等待开局超时，连接关闭"})
        return None


async def _handle_start_game(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
    data: dict,
):
    player_name = data.get("player_name", "无名修士")
    if await _try_send_restored_game(ws, engine, mgr, player_id):
        return
    offers = engine.get_pending_destiny_offers() or engine.prepare_new_game(player_name)
    await ws.send_json(_build_destiny_offer(offers, player_name))


async def _try_send_restored_game(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
) -> bool:
    saved_state = await mgr.try_restore_session(player_id)
    if not saved_state or saved_state.get("stage") in (Stage.GAME_OVER, Stage.INIT):
        return False
    restored = engine.restore_game(saved_state)
    if not restored:
        return False
    log_text = f"[重连成功] 欢迎回来，{restored.player_name}！天道人格：【{restored.heaven_persona}】"
    await ws.send_json(_build_session_log(restored, engine.stage, log_text))
    await ws.send_json(_build_run_map(engine))
    await _send_pending_trigger_if_needed(ws, engine, restored)
    return True


async def _send_pending_trigger_if_needed(
    ws: WebSocket,
    engine: GameEngine,
    restored: PlayerState,
):
    if engine.stage != Stage.EVENT_TRIGGER or not engine._current_trigger:
        return
    await ws.send_json(_build_event_trigger(TickResult(
        stage=engine.stage,
        trigger=engine._current_trigger,
        cultivation=restored.cultivation,
        sin_value=restored.sin_value,
        luck=restored.luck,
        foundation=restored.foundation,
        realm=get_realm_name(restored.realm_code),
        sin_phase=restored.sin_phase(),
        waiting_for_decision=True,
    )))


async def _handle_select_destiny(ws: WebSocket, engine: GameEngine, data: dict):
    sign_id = str(data.get("sign_id", "")).strip()
    if not engine.has_pending_destiny_offer():
        await ws.send_json({"action": Action.SC_ERROR, "message": "请先发送 CS_START_GAME"})
        return
    if not engine.is_valid_pending_destiny(sign_id):
        await ws.send_json({"action": Action.SC_ERROR, "message": "命格已失效，请重新开局"})
        return
    player_name = data.get("player_name") or engine._pending_player_name or "无名修士"
    offers = engine.prepare_ambition_selection(sign_id)
    await ws.send_json(_build_ambition_offer(offers, player_name, sign_id))


async def _handle_select_ambition(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
    data: dict,
):
    ambition_id = str(data.get("ambition_id", "")).strip()
    if not await _validate_ambition_choice(ws, engine, ambition_id):
        return
    player_name = data.get("player_name") or engine._pending_player_name or "无名修士"
    session = await _start_new_session(engine, mgr, player_id, player_name, ambition_id)
    await ws.send_json(_build_session_log(session, engine.stage, _start_log(session)))
    await ws.send_json(_build_run_map(engine))


async def _validate_ambition_choice(
    ws: WebSocket,
    engine: GameEngine,
    ambition_id: str,
) -> bool:
    if not engine.has_pending_ambition_offer():
        await ws.send_json({"action": Action.SC_ERROR, "message": "请先选择命格签"})
        return False
    if not engine.is_valid_pending_ambition(ambition_id):
        await ws.send_json({"action": Action.SC_ERROR, "message": "执念已失效，请重新开局"})
        return False
    return True


async def _start_new_session(
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
    player_name: str,
    ambition_id: str,
) -> PlayerState:
    account = await mgr._account_repo.get_or_create(player_id, player_name) if mgr._account_repo else None
    deafness_active = await _consume_deafness_protocol(mgr, player_id, account)
    return engine.new_game(
        player_name=player_name,
        player_id=player_id,
        karma_shield=account.karma_shield if account else 0,
        deafness_protocol=deafness_active,
        heaven_points=account.heaven_points if account else 0,
        destiny_sign_id=engine._pending_destiny_sign_id,
        ambition_id=ambition_id,
    )


async def _consume_deafness_protocol(mgr: ConnectionManager, player_id: str, account) -> int:
    if not account or account.deafness_protocol <= 0 or not mgr._account_repo:
        return 0
    if await mgr._account_repo.consume_deafness_protocol(player_id):
        account.deafness_protocol -= 1
        return 1
    return 0


def _start_log(session: PlayerState) -> str:
    log_text = (
        f"[开局成功] 天道人格：【{session.heaven_persona}】"
        f" 命格：【{session.destiny_sign_title or '无'}】"
        f" 执念：【{session.ambition_title or '无'}】"
    )
    if session.deafness_protocol:
        log_text += "【天道失聪协议生效：本局逻辑气运 +10，天道选择性装聋】"
    return log_text


async def _handle_runtime_message(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
    data: dict,
):
    action = data.get("action", "")
    if action == Action.CS_PING:
        await ws.send_json({"action": Action.SC_PONG})
    elif action == Action.CS_GET_RUN_MAP:
        await _handle_get_run_map(ws, engine)
    elif action == Action.CS_CHOOSE_MAP_NODE:
        await _handle_choose_map_node(ws, engine, mgr, player_id, data)
    elif action == Action.CS_PLAYER_DECISION:
        await _handle_player_decision(ws, engine, mgr, player_id, data)
    else:
        await ws.send_json({"action": Action.SC_ERROR, "message": f"未知 action: {action}"})


async def _handle_get_run_map(ws: WebSocket, engine: GameEngine):
    await ws.send_json(_build_run_map(engine))


async def _handle_choose_map_node(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
    data: dict,
):
    node_id = str(data.get("node_id", "")).strip()
    ok, message = engine.choose_run_map_node(node_id)
    if not ok:
        await ws.send_json({"action": Action.SC_ERROR, "message": message})
        return
    await ws.send_json(_build_run_map(engine))
    await mgr._save_active_session(player_id, engine)


async def _handle_player_decision(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
    data: dict,
):
    if engine.stage != Stage.EVENT_TRIGGER:
        await ws.send_json({"action": Action.SC_ERROR, "message": "当前没有待处理的事件"})
        return
    if await _reject_unsafe_custom_text(ws, engine, mgr, player_id, data):
        return
    result = await _submit_player_decision(ws, engine, player_id, data)
    await ws.send_json(_build_story_stream("", is_last=True))
    await ws.send_json(_build_event_settlement(result))
    await ws.send_json(_build_run_map(engine))
    await _sync_account_after_settlement(mgr, player_id, engine, result)
    await mgr._save_active_session(player_id, engine)


async def _reject_unsafe_custom_text(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
    data: dict,
) -> bool:
    custom_text = data.get("custom_text", "")
    if not custom_text.strip() or not settings.wechat_msg_sec_check_enabled:
        return False
    from server.interface.app import get_wechat_client
    wc = get_wechat_client()
    sec_started_at = time.perf_counter()
    sec_result = await wc.msg_sec_check(custom_text, openid=player_id)
    logger.info("[Decision] 内容安全审查耗时 %.0fms pass=%s",
                (time.perf_counter() - sec_started_at) * 1000, sec_result.get("pass"))
    if sec_result.get("pass"):
        return False
    await _send_content_penalty(ws, engine, mgr, player_id)
    return True


async def _send_content_penalty(
    ws: WebSocket,
    engine: GameEngine,
    mgr: ConnectionManager,
    player_id: str,
):
    penalty = _apply_content_penalty(engine)
    await _sync_account_penalty(mgr, player_id, penalty)
    if engine.session:
        await ws.send_json(_build_session_log(
            engine.session,
            engine.stage,
            f"[天道监察] 言行不端，天道震怒！扣除 {penalty} 功德。",
        ))


def _apply_content_penalty(engine: GameEngine) -> int:
    if not engine.session:
        return 5
    penalty = max(5, engine.session.heaven_points // 10)
    engine.session.heaven_points = max(0, engine.session.heaven_points - penalty)
    return penalty


async def _submit_player_decision(
    ws: WebSocket,
    engine: GameEngine,
    player_id: str,
    data: dict,
) -> TickResult:
    choice_id = data.get("choice_id", "A")
    custom_text = data.get("custom_text", "")
    started_at = time.perf_counter()
    logger.info("[Decision] 收到决策 player_id=%s choice=%s custom_len=%s",
                player_id, choice_id, len(custom_text.strip()))
    stream_state = {"story_chars": 0, "segments": {}}

    async def on_chunk(segment: str, chunk: str):
        _record_stream_chunk(stream_state, segment, chunk)
        await ws.send_json(_build_story_stream(chunk, is_last=False, segment=segment))

    result = await engine.submit_decision(choice_id, custom_text, on_chunk)
    await _backfill_story_stream(ws, player_id, result, stream_state)
    logger.info("[Decision] 结算完成 player_id=%s streamed_chars=%s total=%.0fms game_over=%s",
                player_id, stream_state["story_chars"],
                (time.perf_counter() - started_at) * 1000, result.game_over)
    return result


def _record_stream_chunk(stream_state: dict, segment: str, chunk: str):
    stream_state["segments"][segment] = stream_state["segments"].get(segment, 0) + len(chunk)
    if segment in ("reason_text", "story_text"):
        stream_state["story_chars"] += len(chunk)


async def _backfill_story_stream(
    ws: WebSocket,
    player_id: str,
    result: TickResult,
    stream_state: dict,
):
    if not result.settlement:
        return
    segments = stream_state["segments"]
    await _backfill_segment(ws, segments, "event_title", result.settlement.event_title)
    await _backfill_segment(ws, segments, "verdict_text", result.settlement.verdict_text)
    if stream_state["story_chars"] == 0:
        await _backfill_missing_story(ws, player_id, result)


async def _backfill_segment(ws: WebSocket, segments: dict, segment: str, text: str):
    if segments.get(segment, 0) == 0 and text:
        await ws.send_json(_build_story_stream(text, is_last=False, segment=segment))


async def _backfill_missing_story(ws: WebSocket, player_id: str, result: TickResult):
    if result.settlement.reason_text:
        logger.warning("[Decision] 未收到流式正文，改为补发因由 player_id=%s story_len=%s",
                       player_id, len(result.settlement.reason_text))
        await ws.send_json(_build_story_stream(result.settlement.reason_text, is_last=False))
    elif result.settlement.story_text:
        logger.warning("[Decision] 未收到流式正文，改为补发全文 player_id=%s story_len=%s",
                       player_id, len(result.settlement.story_text))
        await ws.send_json(_build_story_stream(result.settlement.story_text, is_last=False))


async def _tick_loop(ws: WebSocket, engine: GameEngine, mgr=None, player_id=None):
    """自动挂机循环 + 超时检测 + 会话持久化"""
    while engine.stage != Stage.GAME_OVER:
        if engine.stage == Stage.IDLE:
            await asyncio.sleep(settings.tick_interval)
            if engine.stage != Stage.IDLE:
                continue
            await _maybe_apply_pending_sin_reset(ws, engine, mgr, player_id)
            await _send_tick_result(ws, engine, mgr, player_id, await engine.tick())

        elif engine.stage == Stage.EVENT_TRIGGER:
            if not await _handle_tick_timeout(ws, engine, mgr, player_id):
                await asyncio.sleep(1.0)

        elif engine.stage == Stage.LLM_PROCESSING:
            await asyncio.sleep(0.1)

        else:
            await asyncio.sleep(0.1)


async def _maybe_apply_pending_sin_reset(ws: WebSocket, engine: GameEngine, mgr, player_id):
    if not player_id or not engine.session or not mgr or not mgr._account_repo:
        return
    account = await mgr._account_repo.get(player_id)
    if not account or not account.pending_sin_reset:
        return
    engine.session.sin_value = 0
    await mgr._account_repo._clear_sin_reset(player_id)
    await ws.send_json(_build_session_log(
        engine.session,
        engine.stage,
        "[功德洗白] 功德洗白券生效，天谴值归零！",
    ))


async def _send_tick_result(ws: WebSocket, engine: GameEngine, mgr, player_id, result: TickResult):
    if result.waiting_for_decision:
        await ws.send_json(_build_event_trigger(result))
        if mgr and player_id:
            await mgr._save_active_session(player_id, engine)
    elif result.game_over:
        await ws.send_json(_build_event_settlement(result))
        if mgr and player_id:
            await _sync_account_after_settlement(mgr, player_id, engine, result)
            await mgr._save_active_session(player_id, engine)
    else:
        if mgr and player_id:
            await _maybe_apply_karma_trace_event(mgr, engine, result)
        await ws.send_json(_build_game_log(result))
        await ws.send_json(_build_run_map(engine))


async def _handle_tick_timeout(ws: WebSocket, engine: GameEngine, mgr, player_id) -> bool:
    if not engine.is_decision_timeout():
        return False
    result = await engine.auto_timeout_submit()
    await ws.send_json(_build_story_stream("", is_last=True))
    await ws.send_json(_build_event_settlement(result))
    await ws.send_json(_build_run_map(engine))
    if mgr and player_id:
        await _sync_account_after_settlement(mgr, player_id, engine, result)
        await mgr._save_active_session(player_id, engine)
    return True


async def _sync_account_after_settlement(
    mgr: ConnectionManager,
    player_id: str,
    engine: GameEngine,
    result: TickResult,
):
    """将局内结算影响同步回局外账号资产。"""
    if not mgr or not player_id or not engine.session:
        return
    if mgr._account_repo and result.settlement and result.settlement.intercepted_by_shield:
        await mgr._account_repo.consume_karma_shield(player_id)
    if mgr._account_repo and result.heaven_points_earned:
        await mgr._account_repo.update_heaven_points(
            player_id, result.heaven_points_earned
        )
    settlement = result.settlement
    if settlement and settlement.leaderboard_type and mgr._leaderboard_repo:
        await mgr._leaderboard_repo.insert(
            leaderboard_type=settlement.leaderboard_type,
            player_id=player_id,
            player_name=engine.session.player_name,
            title=settlement.epitaph_title or settlement.dead_title or settlement.event_title,
            score=settlement.leaderboard_score,
            realm=get_realm_name(engine.session.realm_code),
            summary=settlement.verdict_text or settlement.reason_text or settlement.story_text,
        )
    if settlement and settlement.leaderboard_type and mgr._karma_trace_repo:
        trace_type = "gift" if settlement.leaderboard_type == "ascension" else "trap"
        effect_type = "blessing" if trace_type == "gift" else (
            "taunt_infection" if settlement.leaderboard_type == "taunt" else "mislead"
        )
        message = _build_karma_trace_message(engine, settlement, trace_type)
        await mgr._karma_trace_repo.insert(
            source_player_id=player_id,
            source_player_name=engine.session.player_name,
            trace_type=trace_type,
            effect_type=effect_type,
            message=message,
            toxicity_score=0 if trace_type == "gift" else max(1, settlement.leaderboard_score // 50),
        )


def _build_karma_trace_message(engine: GameEngine, settlement: EventSettlement, trace_type: str) -> str:
    player_name = engine.session.player_name if engine.session else "无名修士"
    if trace_type == "gift":
        return f"前人【{player_name}】飞升前留下一缕护道残念：{settlement.epitaph_title or '飞升案首'}。"
    title = settlement.dead_title or settlement.epitaph_title or "死得很有参考价值"
    return f"前人【{player_name}】在此留下因果遗毒：{title}。天道看完后笑了一声。"


def _karma_hook_label(hook: str) -> str:
    """把 3K 语义 hook 映射为玩家可读的投放标签。"""
    labels = {
        "taunt_inscription": "嘴硬碑文",
        "grave_warning": "墓碑警示",
        "corpse_note": "尸骸批注",
        "mislead_choice": "误导残响",
        "last_words": "前人遗言",
    }
    return labels.get(hook, "因果偷渡")


def _apply_hook_side_effect(engine: GameEngine, result: TickResult, hook: str) -> int:
    """按事件 hook 追加轻量差异化效果，返回额外 harm。"""
    session = engine.session
    if not session:
        return 0
    if hook == "taunt_inscription":
        result.taunt_count += 1
        result.karma_pollution_score += 1
        return 1
    if hook == "grave_warning":
        result.death_drama_score += 1
        return 0
    if hook == "corpse_note":
        result.karma_pollution_score += 1
        return 0
    if hook == "mislead_choice":
        result.gamble_survive_count += 1
        return 1
    if hook == "last_words":
        result.death_drama_score += 1
        session.foundation = min(100, session.foundation + 1)
        result.foundation = session.foundation
        return 0
    return 0


async def _maybe_apply_karma_trace_event(mgr: ConnectionManager, engine: GameEngine, result: TickResult):
    """普通挂机日志低概率触发前人因果痕迹。"""
    if not mgr._karma_trace_repo or not engine.session:
        return
    if result.event_type not in ("LOCAL", "RESENTMENT_LOCAL"):
        return
    if random.randint(1, 100) > 8:
        return

    trace = await mgr._karma_trace_repo.sample_for_event()
    if not trace:
        return

    session = engine.session
    trace_id = int(trace["trace_id"])
    trace_type = trace.get("trace_type", "trap")
    hook = result.karma_trace_hook or ""
    hook_label = _karma_hook_label(hook)
    if trace_type == "gift":
        session.foundation = min(100, session.foundation + 1)
        result.foundation = session.foundation
        _apply_hook_side_effect(engine, result, hook)
        result.log_text += f" 【{hook_label}·前人馈赠】{trace['message']} 根基 +1。"
        await mgr._karma_trace_repo.mark_triggered(trace_id, harm_delta=0)
        return

    harm = max(1, int(trace.get("toxicity_score", 1))) + _apply_hook_side_effect(engine, result, hook)
    sin_max = REALM_CONFIG[session.realm_code]["sin_max"]
    session.sin_value = min(sin_max, session.sin_value + harm)
    result.sin_value = session.sin_value
    result.sin_phase = session.sin_phase()
    result.log_text += f" 【{hook_label}】{trace['message']} 天谴 +{harm}。"
    await mgr._karma_trace_repo.mark_triggered(trace_id, harm_delta=harm)


async def _sync_account_penalty(
    mgr: ConnectionManager,
    player_id: str,
    penalty: int,
):
    """将内容安全等处罚同步回局外账号。"""
    if not mgr or not mgr._account_repo or not player_id or penalty <= 0:
        return
    await mgr._account_repo.update_heaven_points(player_id, -penalty)
