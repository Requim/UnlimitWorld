"""
FastAPI 应用工厂 + 生命周期管理

M2 网络层入口，挂载 WebSocket 路由。
通过 lifespan 管理连接管理器、SharedState、怨念池清洗后台任务。

Phase 2D：SharedState 初始化 + KarmaPool 定时清洗 + ConnectionManager 注入。
Phase 3A：WeChat 客户端初始化 + /api/auth/login 端点。
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from server.config import settings
from server.interface.ws import ConnectionManager, router as ws_router
from server.infrastructure.wechat import WeChatClient

logger = logging.getLogger("uvicorn")

# 全服单例（在 lifespan 中初始化）
_connection_manager: ConnectionManager | None = None
_karma_pool_task: asyncio.Task | None = None
_wechat_client: WeChatClient | None = None
_session_factory = None  # Phase 3B：供 REST API 使用
_account_repo = None     # Phase 3B：PlayerAccountRepository
_hall_repo = None        # Phase 3C：ImmortalHallRepository
_leaderboard_repo = None # Phase 3I：多榜单 Repository


async def _ensure_player_account_columns(engine):
    """对旧库做幂等补列，避免 create_all 无法修改已有表结构。"""
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'player_account'
                """
            )
        )
        existing = {row[0] for row in result.fetchall()}

        if "pending_sin_reset" not in existing:
            await conn.execute(
                text(
                    """
                    ALTER TABLE player_account
                    ADD COLUMN pending_sin_reset INT NOT NULL DEFAULT 0
                    AFTER karma_shield
                    """
                )
            )
            logger.info("[DB] player_account 补列：pending_sin_reset")


def get_connection_manager() -> ConnectionManager:
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager


def get_wechat_client() -> WeChatClient:
    global _wechat_client
    if _wechat_client is None:
        _wechat_client = WeChatClient()
    return _wechat_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _connection_manager, _karma_pool_task, _wechat_client

    # ── Phase 3A：微信客户端初始化 ──
    _wechat_client = WeChatClient()
    if _wechat_client.enabled:
        logger.info("[WeChat] 微信 API 客户端已启用")
    else:
        logger.info("[WeChat] 未配置 AppID/Secret，降级为 mock 模式")

    # ── Phase 2D：基础设施初始化 ──
    redis_client = None
    session_factory = None
    dead_registry = None
    immortal_hall = None
    karma_pool = None

    try:
        from server.infrastructure.redis import RedisClient
        redis_client = RedisClient()
        await redis_client.connect()
    except Exception:
        pass  # Redis 不可用时降级运行（CLI 兼容 + 生产韧性）

    try:
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        engine = get_engine()
        session_factory = get_session_factory()
        # 自动建表（幂等，不覆盖已有表）
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await _ensure_player_account_columns(engine)
    except Exception:
        pass  # MySQL 不可用时降级运行

    # Phase 3B：保存全局引用供 REST API
    global _session_factory, _account_repo, _hall_repo, _leaderboard_repo

    if session_factory:
        from server.infrastructure.storage import (
            DeadRegistryRepository,
            ImmortalHallRepository,
            HeavenOverlordPoolRepository,
            ActiveSessionRepository,
            PlayerAccountRepository,
            LeaderboardRepository,
        )
        _account_repo = PlayerAccountRepository(session_factory)
        dead_repo = DeadRegistryRepository(session_factory)
        hall_repo = ImmortalHallRepository(session_factory)
        _hall_repo = hall_repo  # Phase 3C：名人堂 REST API
        _leaderboard_repo = LeaderboardRepository(session_factory)
        heaven_pool_repo = HeavenOverlordPoolRepository(session_factory)
        active_session_repo = ActiveSessionRepository(session_factory)

        if redis_client:
            from server.infrastructure.shared_state import DeadRegistryManager, ImmortalHallManager
            dead_registry = DeadRegistryManager(dead_repo, redis_client)
            immortal_hall = ImmortalHallManager(hall_repo)

            from server.infrastructure.karma_pool import KarmaPoolManager
            karma_pool = KarmaPoolManager(redis_client, heaven_pool_repo, dead_repo)
    else:
        active_session_repo = None

    # ── 创建 ConnectionManager（注入 SharedState + Shop） ──
    _connection_manager = ConnectionManager(
        dead_registry=dead_registry,
        immortal_hall=immortal_hall,
        redis_client=redis_client,
        active_session_repo=active_session_repo,
        account_repo=_account_repo,
        leaderboard_repo=_leaderboard_repo,
    )

    # ── Phase 2D：怨念池清洗后台任务 ──
    if karma_pool:

        async def karma_clean_loop():
            while True:
                await asyncio.sleep(settings.karma_pool_clean_interval)
                try:
                    count = await karma_pool.clean_and_refill()
                    if count > 0:
                        import logging
                        logging.getLogger("uvicorn").info(
                            f"[KarmaPool] 清洗完成，注入 {count} 条怨念"
                        )
                except Exception:
                    pass

        _karma_pool_task = asyncio.create_task(karma_clean_loop())

    yield

    # ── 关闭清理 ──
    if _karma_pool_task:
        _karma_pool_task.cancel()
        try:
            await _karma_pool_task
        except asyncio.CancelledError:
            pass

    await _connection_manager.shutdown()

    if _wechat_client:
        await _wechat_client.close()

    if redis_client:
        try:
            await redis_client.disconnect()
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(title="天道不正经", version="M3", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ws_router)

    # ── Phase 3A：微信登录接口 ──
    @app.post("/api/auth/login")
    async def auth_login(request: Request):
        """wx.login code 换取 player_id。

        请求体：{"code": "wx.login 返回的 code"}
        响应体：{"player_id": str, "is_new": bool}
        """
        body = await request.json()
        code = body.get("code", "")
        if not code:
            return JSONResponse(
                {"error": "缺少 code 参数"}, status_code=400
            )

        wc = get_wechat_client()
        result = await wc.code2session(code)
        if "error" in result:
            return JSONResponse(
                {"error": result["error"]}, status_code=401
            )

        openid = result["openid"]
        # openid 直接作为 player_id 使用
        # PlayerAccount 由 GameEngine.new_game() 在 WebSocket 层创建
        return {"player_id": openid, "is_new": False}

    # ── Phase 3B：天道虚无黑市 REST API ──

    @app.get("/api/shop/items")
    async def shop_items(request: Request):
        """获取商品列表 + 玩家当前余额。

        Query: ?player_id=xxx
        响应: { "items": [...], "heaven_points": 0 }
        """
        from server.domain.shop import get_catalog

        player_id = request.query_params.get("player_id", "")
        items = get_catalog()
        heaven_points = 0

        if player_id and _account_repo:
            account = await _account_repo.get(player_id)
            if account:
                heaven_points = account.heaven_points

        return {"items": items, "heaven_points": heaven_points}

    @app.post("/api/shop/buy")
    async def shop_buy(request: Request):
        """购买道具。

        请求体：{"player_id": str, "item_id": str}
        响应：{"success": bool, "error": str, "heaven_points": int, "item": dict}
        """
        body = await request.json()
        player_id = body.get("player_id", "")
        item_id = body.get("item_id", "")

        if not player_id or not item_id:
            return JSONResponse({"error": "缺少 player_id 或 item_id"}, status_code=400)

        if _account_repo is None:
            return JSONResponse({"error": "商店服务暂不可用"}, status_code=503)

        from server.domain.shop import find_item
        item = find_item(item_id)
        if item is None:
            return JSONResponse({"error": "商品不存在"}, status_code=404)

        account = await _account_repo.get(player_id)
        if account is None:
            return JSONResponse({"error": "账号不存在，请先开始游戏"}, status_code=404)

        if account.heaven_points < item.cost:
            return JSONResponse(
                {"error": f"天道点不足，需要 {item.cost}，当前 {account.heaven_points}"},
                status_code=402,
            )

        success = await _account_repo.buy_item(player_id, item_id, item.cost)
        if not success:
            return JSONResponse({"error": "购买失败"}, status_code=500)

        # 重新查询最新余额
        account = await _account_repo.get(player_id)
        return {
            "success": True,
            "heaven_points": account.heaven_points if account else 0,
            "item": {
                "id": item.id,
                "name": item.name,
                "effect": item.effect,
                "value": item.value,
            },
        }

    # ── Phase 3C：仙尊名人堂 REST API ──

    @app.get("/api/hall/top")
    async def hall_top(request: Request):
        """名人堂排行榜。

        Query: ?limit=50（默认 50，最大 100）
        响应: { "records": [...], "total": int }
        """
        limit_str = request.query_params.get("limit", "50")
        try:
            limit = int(limit_str)
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 100))

        if _hall_repo is None:
            return JSONResponse({"error": "名人堂服务暂不可用"}, status_code=503)

        records = await _hall_repo.get_top(limit=limit)
        return {"records": records, "total": len(records)}

    @app.get("/api/leaderboards")
    async def leaderboards(request: Request):
        """多榜单读取。

        Query: ?type=ascension|death|taunt&limit=50
        """
        board_type = request.query_params.get("type", "ascension")
        if board_type not in {"ascension", "death", "taunt", "gamble", "karma_pollution"}:
            return JSONResponse({"error": "榜单类型不存在"}, status_code=404)
        limit_str = request.query_params.get("limit", "50")
        try:
            limit = int(limit_str)
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 100))

        if _leaderboard_repo is None:
            return JSONResponse({"error": "榜单服务暂不可用"}, status_code=503)

        records = await _leaderboard_repo.get_top(board_type, limit=limit)
        return {"type": board_type, "records": records, "total": len(records)}

    return app


app = create_app()
