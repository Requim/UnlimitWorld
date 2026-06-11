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
    CS_PING = "CS_PING"
    CS_PLAYER_DECISION = "CS_PLAYER_DECISION"
    SC_DESTINY_OFFER = "SC_DESTINY_OFFER"
    SC_AMBITION_OFFER = "SC_AMBITION_OFFER"
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

    # ── 等待开局（Phase 2D：支持断线重连） ──
    while engine.stage == Stage.INIT:
        try:
            data = await asyncio.wait_for(ws.receive_json(), timeout=120.0)
        except asyncio.TimeoutError:
            await ws.send_json({"action": Action.SC_ERROR, "message": "等待开局超时，连接关闭"})
            return

        action = data.get("action")

        if action == Action.CS_PING:
            await ws.send_json({"action": Action.SC_PONG})
            continue

        if action == Action.CS_START_GAME:
            player_name = data.get("player_name", "无名修士")

            # Phase 2D：检查是否有可恢复的会话
            saved_state = await mgr.try_restore_session(player_id)
            if saved_state and saved_state.get("stage") not in (Stage.GAME_OVER, Stage.INIT):
                restored = engine.restore_game(saved_state)
                if restored:
                    await ws.send_json({
                        "action": "SC_GAME_LOG",
                        "log_text": f"[重连成功] 欢迎回来，{restored.player_name}！天道人格：【{restored.heaven_persona}】",
                        "cultivation": restored.cultivation,
                        "sin_value": restored.sin_value,
                        "sin_max": REALM_CONFIG[restored.realm_code]["sin_max"],
                        "luck": restored.luck,
                        "foundation": restored.foundation,
                        "realm": get_realm_name(restored.realm_code),
                        "sin_phase": restored.sin_phase(),
                        "stage": engine.stage,
                        "ambition_title": restored.ambition_title,
                        "ambition_progress": restored.ambition_progress,
                        "ambition_target": restored.ambition_target,
                        "ambition_progress_label": restored.ambition_progress_label,
                        **_empty_phase3k_log_fields(),
                    })
                    if engine.stage == Stage.EVENT_TRIGGER and engine._current_trigger:
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
                    break  # 重连成功，跳出等待开局循环

            offers = engine.get_pending_destiny_offers()
            if not offers:
                offers = engine.prepare_new_game(player_name)
            await ws.send_json(_build_destiny_offer(offers, player_name))
            continue

        if action == Action.CS_SELECT_DESTINY_SIGN:
            sign_id = str(data.get("sign_id", "")).strip()
            if not engine.has_pending_destiny_offer():
                await ws.send_json({"action": Action.SC_ERROR, "message": "请先发送 CS_START_GAME"})
                continue
            if not engine.is_valid_pending_destiny(sign_id):
                await ws.send_json({"action": Action.SC_ERROR, "message": "命格已失效，请重新开局"})
                continue

            player_name = data.get("player_name") or engine._pending_player_name or "无名修士"
            offers = engine.prepare_ambition_selection(sign_id)
            await ws.send_json(_build_ambition_offer(offers, player_name, sign_id))
            continue

        if action == Action.CS_SELECT_AMBITION:
            ambition_id = str(data.get("ambition_id", "")).strip()
            if not engine.has_pending_ambition_offer():
                await ws.send_json({"action": Action.SC_ERROR, "message": "请先选择命格签"})
                continue
            if not engine.is_valid_pending_ambition(ambition_id):
                await ws.send_json({"action": Action.SC_ERROR, "message": "执念已失效，请重新开局"})
                continue

            player_name = data.get("player_name") or engine._pending_player_name or "无名修士"
            sign_id = engine._pending_destiny_sign_id

            # 新一局：从 PlayerAccount 加载局外资产，并消费按局生效的协议
            account = await mgr._account_repo.get_or_create(player_id, player_name) if mgr._account_repo else None
            deafness_active = 0
            if account and account.deafness_protocol > 0 and mgr._account_repo:
                if await mgr._account_repo.consume_deafness_protocol(player_id):
                    deafness_active = 1
                    account.deafness_protocol -= 1

            session = engine.new_game(
                player_name=player_name,
                player_id=player_id,
                karma_shield=account.karma_shield if account else 0,
                deafness_protocol=deafness_active,
                heaven_points=account.heaven_points if account else 0,
                destiny_sign_id=sign_id,
                ambition_id=ambition_id,
            )
            start_log = (
                f"[开局成功] 天道人格：【{session.heaven_persona}】"
                f" 命格：【{session.destiny_sign_title or '无'}】"
                f" 执念：【{session.ambition_title or '无'}】"
            )
            if deafness_active:
                start_log += "【天道失聪协议生效：本局逻辑气运 +10，天道选择性装聋】"
            await ws.send_json({
                "action": "SC_GAME_LOG",
                "log_text": start_log,
                "cultivation": session.cultivation,
                "sin_value": session.sin_value,
                "sin_max": REALM_CONFIG[session.realm_code]["sin_max"],
                "luck": session.luck,
                "foundation": session.foundation,
                "realm": get_realm_name(session.realm_code),
                "sin_phase": session.sin_phase(),
                "stage": engine.stage,
                "destiny_sign_title": session.destiny_sign_title,
                "ambition_title": session.ambition_title,
                "ambition_progress": session.ambition_progress,
                "ambition_target": session.ambition_target,
                "ambition_progress_label": session.ambition_progress_label,
                **_empty_phase3k_log_fields(),
            })
            continue

        await ws.send_json({"action": Action.SC_ERROR, "message": "请先发送 CS_START_GAME"})

    # ── 主循环：tick 自动推进 + 消息接收 + 超时检测 ──
    tick_task = asyncio.create_task(_tick_loop(ws, engine, mgr, player_id))
    mgr.set_tick_task(player_id, tick_task)

    try:
        while engine.stage != Stage.GAME_OVER:
            # Phase 2D：决策超时检测
            if engine.is_decision_timeout():
                result = await engine.auto_timeout_submit()
                await ws.send_json(_build_story_stream("", is_last=True))
                await ws.send_json(_build_event_settlement(result))
                await _sync_account_after_settlement(mgr, player_id, engine, result)
                await mgr._save_active_session(player_id, engine)
                continue

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
                decision_started_at = time.perf_counter()
                logger.info(
                    "[Decision] 收到决策 player_id=%s choice=%s custom_len=%s",
                    player_id,
                    choice_id,
                    len(custom_text.strip()),
                )

                # ── Phase 3A：内容安全审查 ──
                if custom_text.strip() and settings.wechat_msg_sec_check_enabled:
                    from server.interface.app import get_wechat_client
                    wc = get_wechat_client()
                    sec_started_at = time.perf_counter()
                    sec_result = await wc.msg_sec_check(custom_text, openid=player_id)
                    logger.info(
                        "[Decision] 内容安全审查耗时 %.0fms pass=%s",
                        (time.perf_counter() - sec_started_at) * 1000,
                        sec_result.get("pass"),
                    )
                    if not sec_result.get("pass"):
                        # 内容违规：扣除功德 + 警告日志，不调用 LLM
                        penalty = 5
                        if engine.session:
                            penalty = max(5, engine.session.heaven_points // 10)
                            engine.session.heaven_points = max(0, engine.session.heaven_points - penalty)
                        await _sync_account_penalty(mgr, player_id, penalty)
                        await ws.send_json({
                            "action": Action.SC_GAME_LOG,
                            "log_text": f"[天道监察] 言行不端，天道震怒！扣除 {penalty} 功德。",
                            "cultivation": engine.session.cultivation if engine.session else 0,
                            "sin_value": engine.session.sin_value if engine.session else 0,
                            "sin_max": REALM_CONFIG[engine.session.realm_code]["sin_max"] if engine.session else REALM_CONFIG[1]["sin_max"],
                            "luck": engine.session.luck if engine.session else 50,
                            "foundation": engine.session.foundation if engine.session else 50,
                            "realm": get_realm_name(engine.session.realm_code) if engine.session else "练气期",
                            "sin_phase": engine.session.sin_phase() if engine.session else "safe",
                            "stage": engine.stage,
                            "ambition_progress": engine.session.ambition_progress if engine.session else 0,
                            "ambition_target": engine.session.ambition_target if engine.session else 0,
                            "ambition_progress_label": engine.session.ambition_progress_label if engine.session else "",
                            **_empty_phase3k_log_fields(),
                        })
                        continue

                streamed_story_chars = 0
                streamed_segments: dict[str, int] = {}

                async def on_chunk(segment: str, chunk: str):
                    nonlocal streamed_story_chars
                    streamed_segments[segment] = streamed_segments.get(segment, 0) + len(chunk)
                    if segment in ("reason_text", "story_text"):
                        streamed_story_chars += len(chunk)
                    await ws.send_json(_build_story_stream(chunk, is_last=False, segment=segment))

                result = await engine.submit_decision(
                    choice_id=choice_id,
                    custom_text=custom_text,
                    on_chunk=on_chunk,
                )

                if result.settlement:
                    if streamed_segments.get("event_title", 0) == 0 and result.settlement.event_title:
                        await ws.send_json(_build_story_stream(result.settlement.event_title, is_last=False, segment="event_title"))
                    if streamed_story_chars == 0 and result.settlement.reason_text:
                        logger.warning(
                            "[Decision] 未收到流式正文，改为补发因由 player_id=%s story_len=%s",
                            player_id,
                            len(result.settlement.reason_text),
                        )
                        await ws.send_json(_build_story_stream(result.settlement.reason_text, is_last=False, segment="reason_text"))
                    if streamed_segments.get("verdict_text", 0) == 0 and result.settlement.verdict_text:
                        await ws.send_json(_build_story_stream(result.settlement.verdict_text, is_last=False, segment="verdict_text"))

                if streamed_story_chars == 0 and result.settlement and result.settlement.story_text:
                    logger.warning(
                        "[Decision] 未收到流式正文，改为补发全文 player_id=%s story_len=%s",
                        player_id,
                        len(result.settlement.story_text),
                    )
                    if not result.settlement.reason_text:
                        await ws.send_json(_build_story_stream(result.settlement.story_text, is_last=False, segment="reason_text"))

                logger.info(
                    "[Decision] 结算完成 player_id=%s streamed_chars=%s total=%.0fms game_over=%s",
                    player_id,
                    streamed_story_chars,
                    (time.perf_counter() - decision_started_at) * 1000,
                    result.game_over,
                )
                await ws.send_json(_build_story_stream("", is_last=True))
                await ws.send_json(_build_event_settlement(result))

                await _sync_account_after_settlement(mgr, player_id, engine, result)

                # 持久化状态变更
                await mgr._save_active_session(player_id, engine)

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


async def _tick_loop(ws: WebSocket, engine: GameEngine, mgr=None, player_id=None):
    """自动挂机循环 + 超时检测 + 会话持久化"""
    while engine.stage != Stage.GAME_OVER:
        if engine.stage == Stage.IDLE:
            await asyncio.sleep(settings.tick_interval)
            if engine.stage != Stage.IDLE:
                continue

            # Phase 3B：消费商店道具效果（功德洗白券 — 天谴清零）
            if player_id and engine.session and mgr and mgr._account_repo:
                account = await mgr._account_repo.get(player_id)
                if account and account.pending_sin_reset:
                    engine.session.sin_value = 0
                    await mgr._account_repo._clear_sin_reset(player_id)
                    await ws.send_json({
                        "action": "SC_GAME_LOG",
                        "log_text": "[功德洗白] 功德洗白券生效，天谴值归零！",
                        "cultivation": engine.session.cultivation,
                        "sin_value": 0,
                        "luck": engine.session.luck,
                        "foundation": engine.session.foundation,
                        "realm": get_realm_name(engine.session.realm_code),
                        "sin_phase": "safe",
                        "stage": engine.stage,
                        "ambition_progress": engine.session.ambition_progress,
                        "ambition_target": engine.session.ambition_target,
                        "ambition_progress_label": engine.session.ambition_progress_label,
                        **_empty_phase3k_log_fields(),
                    })

            result = await engine.tick()

            if result.waiting_for_decision:
                await ws.send_json(_build_event_trigger(result))
                # Phase 2D：进入决策阶段，立即持久化（含 trigger）
                if mgr and player_id:
                    await mgr._save_active_session(player_id, engine)
            elif result.game_over:
                await ws.send_json(_build_event_settlement(result))
                if mgr and player_id:
                    await _sync_account_after_settlement(mgr, player_id, engine, result)
                if mgr and player_id:
                    await mgr._save_active_session(player_id, engine)
            else:
                if mgr and player_id:
                    await _maybe_apply_karma_trace_event(mgr, engine, result)
                await ws.send_json(_build_game_log(result))

        elif engine.stage == Stage.EVENT_TRIGGER:
            # Phase 2D：超时检测（1s 粒度为 ws 消息循环，这里也保持一致）
            if engine.is_decision_timeout():
                result = await engine.auto_timeout_submit()
                await ws.send_json(_build_story_stream("", is_last=True))
                await ws.send_json(_build_event_settlement(result))
                if mgr and player_id:
                    await _sync_account_after_settlement(mgr, player_id, engine, result)
                    await mgr._save_active_session(player_id, engine)
            else:
                await asyncio.sleep(1.0)

        elif engine.stage == Stage.LLM_PROCESSING:
            await asyncio.sleep(0.1)

        else:
            await asyncio.sleep(0.1)


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
    if trace_type == "gift":
        session.foundation = min(100, session.foundation + 1)
        result.foundation = session.foundation
        result.log_text += f" 【前人馈赠】{trace['message']} 根基 +1。"
        await mgr._karma_trace_repo.mark_triggered(trace_id, harm_delta=0)
        return

    harm = max(1, int(trace.get("toxicity_score", 1)))
    sin_max = REALM_CONFIG[session.realm_code]["sin_max"]
    session.sin_value = min(sin_max, session.sin_value + harm)
    result.sin_value = session.sin_value
    result.sin_phase = session.sin_phase()
    result.log_text += f" 【因果偷渡】{trace['message']} 天谴 +{harm}。"
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
