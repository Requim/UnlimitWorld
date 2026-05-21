"""
FastAPI 应用工厂 + 生命周期管理

M2 网络层入口，挂载 WebSocket 路由。
通过 lifespan 管理连接管理器（ConnectionManager）的全服生命周期。
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.interface.ws import ConnectionManager, router as ws_router


# 全服单例连接管理器（在 lifespan 中初始化）
_connection_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _connection_manager
    _connection_manager = ConnectionManager()
    yield
    # 关闭所有活跃连接
    await _connection_manager.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="天道不正经", version="M2", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ws_router)

    return app


app = create_app()
