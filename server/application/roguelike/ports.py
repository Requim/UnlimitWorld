"""应用层依赖的权威局面仓储端口。"""

from __future__ import annotations

from typing import Callable, Protocol

from server.domain.roguelike.models import GameEvent, RunResponse, RunState


ActionHandler = Callable[[RunState], list[GameEvent]]


class RunRepository(Protocol):
    """匿名档案、局面读取及原子动作提交契约。"""

    def prepare_profile(self, access_token: str | None) -> tuple[str, str]:
        """创建或验证匿名档案；返回档案 ID/凭证，错误凭证抛 Unauthorized。"""
        ...

    def list_epitaphs(self, profile_id: str) -> list[str]:
        """返回档案自己的已结束战报文本；只读，不泄露其他档案。"""
        ...

    def insert_run(self, run: RunState) -> None:
        """持久化新权威局面；重复标识由实现抛存储错误。"""
        ...

    def get_run(self, run_id: str, access_token: str) -> RunState:
        """按凭证读取所属局面；错误凭证或不存在局面分别抛领域错误。"""
        ...

    def transact_action(
        self,
        run_id: str,
        access_token: str,
        action_id: str,
        expected_revision: int,
        payload: str,
        handler: ActionHandler,
    ) -> RunResponse:
        """原子执行动作并缓存响应；版本或幂等冲突不得修改存档。"""
        ...
