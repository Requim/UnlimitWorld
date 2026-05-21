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

from server.config import settings
from server.interface.ws import ConnectionManager, router as ws_router
from server.infrastructure.wechat import WeChatClient

logger = logging.getLogger("uvicorn")

# 全服单例（在 lifespan 中初始化）
_connection_manager: ConnectionManager | None = None
_karma_pool_task: asyncio.Task | None = None
_wechat_client: WeChatClient | None = None


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
    except Exception:
        pass  # MySQL 不可用时降级运行

    if session_factory:
        from server.infrastructure.storage import (
            DeadRegistryRepository,
            ImmortalHallRepository,
            HeavenOverlordPoolRepository,
            ActiveSessionRepository,
        )
        dead_repo = DeadRegistryRepository(session_factory)
        hall_repo = ImmortalHallRepository(session_factory)
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

    # ── 创建 ConnectionManager（注入 SharedState） ──
    _connection_manager = ConnectionManager(
        dead_registry=dead_registry,
        immortal_hall=immortal_hall,
        redis_client=redis_client,
        active_session_repo=active_session_repo,
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

    return app


app = create_app()
