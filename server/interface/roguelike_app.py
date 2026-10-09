"""M5 独立浏览器样板的 FastAPI 入口。"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server.application.roguelike.service import RoguelikeService
from server.domain.roguelike.catalog import get_catalog
from server.domain.roguelike.errors import (
    InvalidAction,
    RevisionConflict,
    RoguelikeError,
    RunNotFound,
    Unauthorized,
)
from server.domain.roguelike.models import (
    ActionRequest,
    CatalogResponse,
    CreateRunRequest,
    CreateRunResponse,
    RunResponse,
)
from server.infrastructure.roguelike.repository import SQLiteRunRepository


bearer = HTTPBearer(auto_error=False)


def create_app(db_path: str | Path = ".data/m5.sqlite3") -> FastAPI:
    """创建独立 M5 应用；仅保存路径，不创建文件，真实请求时才初始化 SQLite。"""
    api = FastAPI(title="天道不正经 M5 卡牌肉鸽 API", version="2.0.0")
    service = RoguelikeService(SQLiteRunRepository(db_path))
    _register_error_handlers(api)

    @api.get("/health")
    def health() -> dict[str, str]:
        """返回进程健康状态；无入参、无存储副作用。"""
        return {"status": "ok"}

    @api.get("/api/v2/catalog", response_model=CatalogResponse)
    def catalog() -> CatalogResponse:
        """返回完整卡牌、法宝、敌人与流派目录；无存储副作用。"""
        return get_catalog()

    @api.post("/api/v2/runs", response_model=CreateRunResponse, status_code=status.HTTP_201_CREATED)
    def create_run(
        body: CreateRunRequest,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> CreateRunResponse:
        """创建匿名局面；可用既有 Bearer 归属同档案，错误凭证返回 401。"""
        token = credentials.credentials if credentials else None
        return service.create_run(body.archetype, token)

    @api.get("/api/v2/runs/{run_id}", response_model=RunResponse)
    def get_run(
        run_id: str,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> RunResponse:
        """读取 Bearer 所属权威局面；无写副作用，缺失或错误凭证返回 401。"""
        return service.get_run(run_id, _required_token(credentials))

    @api.post("/api/v2/runs/{run_id}/actions", response_model=RunResponse)
    def perform_action(
        run_id: str,
        body: ActionRequest,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> RunResponse:
        """原子提交类型化动作；成功推进 revision，非法动作不落盘。"""
        return service.perform_action(run_id, _required_token(credentials), body.root)

    return api


def _required_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None:
        raise Unauthorized("缺少 Bearer 匿名访问凭证")
    return credentials.credentials


def _register_error_handlers(api: FastAPI) -> None:
    mappings = {
        Unauthorized: 401,
        RunNotFound: 404,
        RevisionConflict: 409,
        InvalidAction: 422,
    }
    for error_type, code in mappings.items():
        api.add_exception_handler(error_type, _handler(code))


def _handler(status_code: int):
    async def handle(request: Request, exc: RoguelikeError) -> JSONResponse:
        """将领域错误转换为稳定 JSON HTTP 错误响应。"""
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handle


app = create_app()
