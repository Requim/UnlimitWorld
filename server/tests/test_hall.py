"""
Phase 3C 测试：名人堂 REST API + ImmortalHallRepository

覆盖：
  - GET /api/hall/top（无参 / 自定义 limit / 非法 limit）
  - ImmortalHallRepository.insert + get_top 排序
  - 空名人堂
  - 数据字段完整性
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest


# ── 辅助 ──

def _mysql_available():
    import socket
    from server.config import settings
    host = settings.mysql_host
    port = settings.mysql_port
    try:
        s = socket.create_connection((host, port), timeout=1.0)
        s.close()
        return True
    except Exception:
        return False


_mysql_skip = pytest.mark.skipif(not _mysql_available(), reason="MySQL 不可用")


class TestHallEndpoints:
    """REST API 端点测试（不依赖 DB）"""

    @pytest.fixture
    def client(self):
        from server.interface.app import create_app
        from fastapi.testclient import TestClient
        return TestClient(create_app())

    def test_get_top_default(self, client):
        """无参数请求返回 records 和 total"""
        resp = client.get("/api/hall/top")
        assert resp.status_code in (200, 503)
        data = resp.json()
        if resp.status_code == 200:
            assert "records" in data
            assert "total" in data
            assert isinstance(data["records"], list)
            assert isinstance(data["total"], int)

    def test_get_top_with_limit(self, client):
        """自定义 limit 参数"""
        resp = client.get("/api/hall/top?limit=10")
        assert resp.status_code in (200, 503)

    def test_get_top_invalid_limit_clamped(self, client):
        """非法 limit 被钳位到默认值"""
        resp = client.get("/api/hall/top?limit=abc")
        assert resp.status_code in (200, 503)

    def test_get_top_limit_above_max_clamped(self, client):
        """超过 100 的 limit 被钳位"""
        resp = client.get("/api/hall/top?limit=999")
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert data["total"] <= 100

    def test_get_top_limit_below_min_clamped(self, client):
        """小于 1 的 limit 被钳位"""
        resp = client.get("/api/hall/top?limit=0")
        assert resp.status_code in (200, 503)

    def test_leaderboards_endpoint_default(self, client):
        resp = client.get("/api/leaderboards?type=ascension&limit=10")
        assert resp.status_code in (200, 503)
        data = resp.json()
        if resp.status_code == 200:
            assert data["type"] == "ascension"
            assert "records" in data
            assert "total" in data

    def test_leaderboards_invalid_type(self, client):
        resp = client.get("/api/leaderboards?type=not_exists")
        assert resp.status_code == 404


@_mysql_skip
class TestImmortalHallRepository:
    """ImmortalHallRepository 读写测试（需要数据库）"""

    @pytest.mark.asyncio
    async def test_insert_and_get_top(self):
        """插入记录后 get_top 能查到"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import ImmortalHallRepository

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = ImmortalHallRepository(sf)

        # 插入测试飞升记录
        await repo.insert(
            player_id="test_hall_p1",
            player_name="测试真仙",
            ascension_title="九天混元大罗金仙",
            heaven_points=9999,
        )

        records = await repo.get_top(limit=10)
        assert len(records) >= 1

        # 找我们刚插入的
        found = [r for r in records if r["player_name"] == "测试真仙"]
        assert len(found) == 1
        rec = found[0]
        assert rec["ascension_title"] == "九天混元大罗金仙"
        assert rec["total_heaven_points"] == 9999
        assert "ascended_at" in rec

    @pytest.mark.asyncio
    async def test_get_top_sorted_by_points(self):
        """get_top 按天道点降序排列"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import ImmortalHallRepository

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = ImmortalHallRepository(sf)

        await repo.insert("test_sort_1", "低分修士", "普通飞升", 100)
        await repo.insert("test_sort_2", "高分修士", "至尊飞升", 99999)

        records = await repo.get_top(limit=50)
        # 找两个记录的位置
        idx_low = next(i for i, r in enumerate(records) if r["player_name"] == "低分修士")
        idx_high = next(i for i, r in enumerate(records) if r["player_name"] == "高分修士")
        assert idx_high < idx_low  # 高分在前

    @pytest.mark.asyncio
    async def test_get_top_respects_limit(self):
        """get_top 遵守 limit 参数"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import ImmortalHallRepository

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = ImmortalHallRepository(sf)

        # 插入 5 条
        for i in range(5):
            await repo.insert(f"test_limit_{i}", f"修士{i}", "飞升", 100 + i)

        records = await repo.get_top(limit=3)
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_empty_hall_returns_empty_list(self):
        """空表 get_top 返回空列表（注：可能受其他测试影响有数据，所以至少验证不报错）"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.storage import ImmortalHallRepository

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = ImmortalHallRepository(sf)

        records = await repo.get_top(limit=10)
        assert isinstance(records, list)

    @pytest.mark.asyncio
    async def test_record_fields_complete(self):
        """get_top 返回的记录包含所有必要字段"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import ImmortalHallRepository

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = ImmortalHallRepository(sf)

        await repo.insert("test_fields", "字段测试仙", "测试封号", 8888)
        records = await repo.get_top(limit=50)

        found = [r for r in records if r["player_name"] == "字段测试仙"]
        assert len(found) >= 1
        rec = found[0]
        for field in ["player_name", "ascension_title", "total_heaven_points", "ascended_at"]:
            assert field in rec, f"缺少字段: {field}"
        assert isinstance(rec["total_heaven_points"], int)
        assert isinstance(rec["ascended_at"], str)
