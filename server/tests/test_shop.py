"""
Phase 3B 测试：商店领域模型 + REST API + 道具购买

覆盖：
  - ShopItem 目录定义
  - get_catalog / find_item
  - GET /api/shop/items（含余额）
  - POST /api/shop/buy（正常购买 / 余额不足 / 商品不存在）
  - PlayerAccountRepository buy_item 各道具效果
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest


# ── 辅助 ──

def _mysql_available():
    """检查本地是否有 MySQL 可用（避免无 DB 时全红）"""
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


class TestShopCatalog:
    """domain/shop.py — 商品目录"""

    def test_catalog_has_three_items(self):
        from server.domain.shop import get_catalog
        items = get_catalog()
        assert len(items) == 3

    def test_catalog_items_have_required_fields(self):
        from server.domain.shop import get_catalog
        for item in get_catalog():
            assert "id" in item
            assert "name" in item
            assert "cost" in item
            assert "effect" in item
            assert "desc" in item

    def test_find_item_exists(self):
        from server.domain.shop import find_item
        item = find_item("karma_shield")
        assert item is not None
        assert item.id == "karma_shield"
        assert item.cost == 50
        assert item.effect == "karma_shield"

    def test_find_item_not_exists(self):
        from server.domain.shop import find_item
        assert find_item("nonexistent") is None

    def test_sin_wash_has_zero_value(self):
        from server.domain.shop import find_item
        item = find_item("sin_wash")
        assert item is not None
        assert item.value == 0
        assert item.effect == "sin_reset"


class TestShopEndpoints:
    """REST API 端点测试"""

    @pytest.fixture
    def client(self):
        from server.interface.app import create_app
        from fastapi.testclient import TestClient
        return TestClient(create_app())

    def test_get_items_returns_catalog(self, client):
        resp = client.get("/api/shop/items")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "heaven_points" in data
        assert len(data["items"]) == 3
        # 无 player_id 时余额为 0
        assert data["heaven_points"] == 0

    def test_buy_missing_player_id(self, client):
        resp = client.post("/api/shop/buy", json={})
        assert resp.status_code == 400
        assert "player_id" in resp.json()["error"]

    def test_buy_missing_item_id(self, client):
        resp = client.post("/api/shop/buy", json={"player_id": "test_p1"})
        assert resp.status_code == 400
        assert "item_id" in resp.json()["error"]

    def test_buy_nonexistent_item(self, client):
        resp = client.post("/api/shop/buy", json={
            "player_id": "test_p1",
            "item_id": "fake_item",
        })
        # 无 DB 时返回 503，有 DB 时返回 404
        assert resp.status_code in (404, 503)

    def test_buy_no_account(self, client):
        """未开局的玩家购买"""
        resp = client.post("/api/shop/buy", json={
            "player_id": "no_such_player_xyz",
            "item_id": "karma_shield",
        })
        assert resp.status_code in (404, 503)


@_mysql_skip
class TestShopBuyItemLogic:
    """PlayerAccountRepository.buy_item 逻辑测试（需要数据库）"""

    @pytest.mark.asyncio
    async def test_buy_item_success_karma_shield(self):
        """购买因果遮蔽卡：扣点 + karma_shield+1"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        # 创建测试账号
        account = PlayerAccount(player_id="test_buy_1", player_name="测试修士", heaven_points=200)
        await repo.save(account)

        # 购买因果遮蔽卡
        success = await repo.buy_item("test_buy_1", "karma_shield", 50)
        assert success is True

        # 验证余额和道具
        updated = await repo.get("test_buy_1")
        assert updated is not None
        assert updated.heaven_points == 150
        assert updated.karma_shield == 1
        assert updated.deafness_protocol == 0

    @pytest.mark.asyncio
    async def test_buy_item_success_deafness(self):
        """购买失聪协议：deafness_protocol+1"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        account = PlayerAccount(player_id="test_buy_2", player_name="测试修士", heaven_points=100)
        await repo.save(account)

        success = await repo.buy_item("test_buy_2", "deafness_protocol", 30)
        assert success is True

        updated = await repo.get("test_buy_2")
        assert updated.heaven_points == 70
        assert updated.deafness_protocol == 1

    @pytest.mark.asyncio
    async def test_buy_item_success_sin_wash(self):
        """购买功德洗白券：设置 pending_sin_reset"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        account = PlayerAccount(player_id="test_buy_3", player_name="测试修士", heaven_points=200)
        await repo.save(account)

        success = await repo.buy_item("test_buy_3", "sin_wash", 80)
        assert success is True

        updated = await repo.get("test_buy_3")
        assert updated.heaven_points == 120
        assert updated.pending_sin_reset is True

        # 消费标记
        await repo._clear_sin_reset("test_buy_3")
        updated2 = await repo.get("test_buy_3")
        assert updated2.pending_sin_reset is False

    @pytest.mark.asyncio
    async def test_buy_item_insufficient_funds(self):
        """余额不足时购买失败"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        account = PlayerAccount(player_id="test_buy_4", player_name="穷修士", heaven_points=10)
        await repo.save(account)

        success = await repo.buy_item("test_buy_4", "karma_shield", 50)
        assert success is False

        # 余额不变
        updated = await repo.get("test_buy_4")
        assert updated.heaven_points == 10

    @pytest.mark.asyncio
    async def test_buy_item_no_account(self):
        """账号不存在时购买失败"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        success = await repo.buy_item("nonexistent", "karma_shield", 50)
        assert success is False

    @pytest.mark.asyncio
    async def test_buy_multiple_items(self):
        """连续购买多个道具"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        account = PlayerAccount(player_id="test_buy_5", player_name="土豪修士", heaven_points=500)
        await repo.save(account)

        # 买两个因果遮蔽卡
        assert await repo.buy_item("test_buy_5", "karma_shield", 50) is True
        assert await repo.buy_item("test_buy_5", "karma_shield", 50) is True
        # 买一个失聪协议
        assert await repo.buy_item("test_buy_5", "deafness_protocol", 30) is True

        updated = await repo.get("test_buy_5")
        assert updated.heaven_points == 370  # 500 - 100 - 30
        assert updated.karma_shield == 2
        assert updated.deafness_protocol == 1
