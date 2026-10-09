"""独立 SQLite 局面、匿名档案与幂等动作仓储。"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from pathlib import Path
from uuid import uuid4

from server.application.roguelike.ports import ActionHandler
from server.application.roguelike.views import build_run_view
from server.domain.roguelike.errors import RevisionConflict, RunNotFound, Unauthorized
from server.domain.roguelike.models import RunResponse, RunState


class SQLiteRunRepository:
    """以独立 SQLite 文件保存匿名档案、权威局面和动作结果。"""

    def __init__(self, db_path: str | Path):
        self._path = Path(db_path)

    def prepare_profile(self, access_token: str | None) -> tuple[str, str]:
        """创建或验证匿名档案；返回 profile_id/token，会写库，错误凭证抛 Unauthorized。"""
        with self._connect() as connection:
            if access_token:
                return self._authenticate(connection, access_token), access_token
            token = secrets.token_urlsafe(32)
            profile_id = uuid4().hex
            connection.execute(
                "INSERT INTO profiles(profile_id, token_hash) VALUES (?, ?)",
                (profile_id, _token_hash(token)),
            )
            return profile_id, token

    def list_epitaphs(self, profile_id: str) -> list[str]:
        """读取档案自身已结束战报；无副作用，不会返回其他档案数据。"""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT state_json FROM runs WHERE profile_id = ? AND finished = 1",
                (profile_id,),
            ).fetchall()
        states = [RunState.model_validate_json(row[0]) for row in rows]
        return [state.epitaph for state in states if state.epitaph]

    def insert_run(self, run: RunState) -> None:
        """插入新权威局面；会写库，重复 run_id 由 SQLite 报完整性错误。"""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs(run_id, profile_id, revision, state_json, finished) VALUES (?, ?, ?, ?, 0)",
                (run.run_id, run.profile_id, run.revision, run.model_dump_json()),
            )

    def get_run(self, run_id: str, access_token: str) -> RunState:
        """按凭证读取所属局面；无写副作用，错误凭证抛 Unauthorized，不存在抛 RunNotFound。"""
        with self._connect() as connection:
            profile_id = self._authenticate(connection, access_token)
            return self._load_owned_run(connection, run_id, profile_id)

    def transact_action(
        self,
        run_id: str,
        access_token: str,
        action_id: str,
        expected_revision: int,
        payload: str,
        handler: ActionHandler,
    ) -> RunResponse:
        """原子执行动作并缓存结果；并发、版本或同编号异内容冲突抛 RevisionConflict。"""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            result = self._execute_locked(
                connection, run_id, access_token, action_id, expected_revision, payload, handler
            )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _execute_locked(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        access_token: str,
        action_id: str,
        expected_revision: int,
        payload: str,
        handler: ActionHandler,
    ) -> RunResponse:
        profile_id = self._authenticate(connection, access_token)
        run = self._load_owned_run(connection, run_id, profile_id)
        cached = self._cached_action(connection, run_id, action_id)
        if cached:
            return self._return_cached(cached, payload)
        if run.revision != expected_revision:
            raise RevisionConflict("局面版本已更新，请刷新后重试")
        events = handler(run)
        run.revision += 1
        response = RunResponse(run=build_run_view(run), events=events)
        self._persist_result(connection, run, action_id, payload, response)
        return response

    def _return_cached(self, row: sqlite3.Row, payload: str) -> RunResponse:
        if not hmac.compare_digest(row["payload_json"], payload):
            raise RevisionConflict("同一 action_id 不得提交不同内容")
        return RunResponse.model_validate_json(row["result_json"])

    def _persist_result(
        self,
        connection: sqlite3.Connection,
        run: RunState,
        action_id: str,
        payload: str,
        response: RunResponse,
    ) -> None:
        finished = int(run.phase in {"completed", "game_over"})
        connection.execute(
            "UPDATE runs SET revision = ?, state_json = ?, finished = ? WHERE run_id = ?",
            (run.revision, run.model_dump_json(), finished, run.run_id),
        )
        connection.execute(
            "INSERT INTO actions(run_id, action_id, payload_json, result_json) VALUES (?, ?, ?, ?)",
            (run.run_id, action_id, payload, response.model_dump_json()),
        )

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        self._initialize(connection)
        return connection

    def _initialize(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                finished INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(profile_id) REFERENCES profiles(profile_id)
            );
            CREATE TABLE IF NOT EXISTS actions (
                run_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY(run_id, action_id),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE INDEX IF NOT EXISTS idx_runs_profile ON runs(profile_id, finished);
            """
        )

    def _authenticate(self, connection: sqlite3.Connection, access_token: str) -> str:
        candidate = _token_hash(access_token)
        rows = connection.execute("SELECT profile_id, token_hash FROM profiles").fetchall()
        for row in rows:
            if hmac.compare_digest(row["token_hash"], candidate):
                return row["profile_id"]
        raise Unauthorized("匿名访问凭证无效")

    def _load_owned_run(
        self, connection: sqlite3.Connection, run_id: str, profile_id: str
    ) -> RunState:
        row = connection.execute(
            "SELECT profile_id, state_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise RunNotFound("局面不存在")
        if not hmac.compare_digest(row["profile_id"], profile_id):
            raise Unauthorized("该匿名档案无权访问此局面")
        return RunState.model_validate_json(row["state_json"])

    def _cached_action(
        self, connection: sqlite3.Connection, run_id: str, action_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT payload_json, result_json FROM actions WHERE run_id = ? AND action_id = ?",
            (run_id, action_id),
        ).fetchone()
def _token_hash(access_token: str) -> str:
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()
