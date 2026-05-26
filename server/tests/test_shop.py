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


class TestSettlementAssetSync:
    """WebSocket 结算后局内资产同步回局外账号（无 DB 纯 mock）"""

    @pytest.mark.asyncio
    async def test_sync_consumes_shield_and_adds_points(self):
        from server.interface.ws import ConnectionManager, _sync_account_after_settlement
        from server.application.game_engine import GameEngine, TickResult, Stage
        from server.domain.event import EventSettlement, AttributeChanges

        class FakeAccountRepo:
            def __init__(self):
                self.shield_consumed = 0
                self.points_delta = 0

            async def consume_karma_shield(self, player_id):
                self.shield_consumed += 1
                return True

            async def update_heaven_points(self, player_id, delta):
                self.points_delta += delta

        class FakeLeaderboardRepo:
            def __init__(self):
                self.rows = []

            async def insert(self, **kwargs):
                self.rows.append(kwargs)

        class FakeKarmaTraceRepo:
            def __init__(self):
                self.rows = []

            async def insert(self, **kwargs):
                self.rows.append(kwargs)
                return 1

        repo = FakeAccountRepo()
        leaderboard_repo = FakeLeaderboardRepo()
        karma_trace_repo = FakeKarmaTraceRepo()
        mgr = ConnectionManager(
            account_repo=repo,
            leaderboard_repo=leaderboard_repo,
            karma_trace_repo=karma_trace_repo,
        )
        engine = GameEngine()
        engine.new_game(player_id="sync_p1")

        settlement = EventSettlement(
            event_id="evt_sync",
            is_dead=False,
            story_text="被捞回",
            attribute_changes=AttributeChanges(),
            intercepted_by_shield=True,
            heaven_points_earned=42,
            epitaph_title="天道重点观察对象",
            leaderboard_type="death",
            leaderboard_score=120,
            verdict_text="死得很响。",
        )
        result = TickResult(
            stage=Stage.IDLE,
            settlement=settlement,
            heaven_points_earned=42,
        )

        await _sync_account_after_settlement(mgr, "sync_p1", engine, result)

        assert repo.shield_consumed == 1
        assert repo.points_delta == 42
        assert leaderboard_repo.rows[0]["leaderboard_type"] == "death"
        assert leaderboard_repo.rows[0]["score"] == 120
        assert karma_trace_repo.rows[0]["trace_type"] == "trap"
        assert karma_trace_repo.rows[0]["effect_type"] == "mislead"
        assert "因果遗毒" in karma_trace_repo.rows[0]["message"]

    @pytest.mark.asyncio
    async def test_sync_skips_when_no_settlement_effect(self):
        from server.interface.ws import ConnectionManager, _sync_account_after_settlement
        from server.application.game_engine import GameEngine, TickResult, Stage

        class FakeAccountRepo:
            def __init__(self):
                self.shield_consumed = 0
                self.points_delta = 0

            async def consume_karma_shield(self, player_id):
                self.shield_consumed += 1
                return True

            async def update_heaven_points(self, player_id, delta):
                self.points_delta += delta

        repo = FakeAccountRepo()
        mgr = ConnectionManager(account_repo=repo)
        engine = GameEngine()
        engine.new_game(player_id="sync_p2")
        result = TickResult(stage=Stage.IDLE, heaven_points_earned=0)

        await _sync_account_after_settlement(mgr, "sync_p2", engine, result)

        assert repo.shield_consumed == 0
        assert repo.points_delta == 0

    @pytest.mark.asyncio
    async def test_sync_penalty_deducts_points(self):
        from server.interface.ws import ConnectionManager, _sync_account_penalty

        class FakeAccountRepo:
            def __init__(self):
                self.points_delta = 0

            async def update_heaven_points(self, player_id, delta):
                self.points_delta += delta

        repo = FakeAccountRepo()
        mgr = ConnectionManager(account_repo=repo)

        await _sync_account_penalty(mgr, "sync_p3", 25)

        assert repo.points_delta == -25

    @pytest.mark.asyncio
    async def test_sync_penalty_skips_non_positive(self):
        from server.interface.ws import ConnectionManager, _sync_account_penalty

        class FakeAccountRepo:
            def __init__(self):
                self.points_delta = 0

            async def update_heaven_points(self, player_id, delta):
                self.points_delta += delta

        repo = FakeAccountRepo()
        mgr = ConnectionManager(account_repo=repo)

        await _sync_account_penalty(mgr, "sync_p4", 0)

        assert repo.points_delta == 0


class TestKarmaTraceTickEvents:
    @pytest.mark.asyncio
    async def test_maybe_apply_karma_trace_trap(self, monkeypatch):
        from server.interface.ws import ConnectionManager, _maybe_apply_karma_trace_event
        from server.application.game_engine import GameEngine, TickResult, Stage

        class FakeKarmaTraceRepo:
            def __init__(self):
                self.marked = []

            async def sample_for_event(self):
                return {
                    "trace_id": 7,
                    "trace_type": "trap",
                    "effect_type": "mislead",
                    "message": "前人说第二个包飞升。",
                    "toxicity_score": 3,
                }

            async def mark_triggered(self, trace_id, harm_delta=0, death_caused=False):
                self.marked.append((trace_id, harm_delta, death_caused))

        monkeypatch.setattr("server.interface.ws.random.randint", lambda *_: 1)
        repo = FakeKarmaTraceRepo()
        mgr = ConnectionManager(karma_trace_repo=repo)
        engine = GameEngine()
        engine.new_game()
        result = TickResult(
            stage=Stage.IDLE,
            log_text="【平淡日常】打坐。",
            event_type="LOCAL",
            sin_value=0,
            foundation=engine.session.foundation,
        )

        await _maybe_apply_karma_trace_event(mgr, engine, result)

        assert "因果偷渡" in result.log_text
        assert engine.session.sin_value == 3
        assert repo.marked == [(7, 3, False)]

    @pytest.mark.asyncio
    async def test_maybe_apply_karma_trace_gift(self, monkeypatch):
        from server.interface.ws import ConnectionManager, _maybe_apply_karma_trace_event
        from server.application.game_engine import GameEngine, TickResult, Stage

        class FakeKarmaTraceRepo:
            def __init__(self):
                self.marked = []

            async def sample_for_event(self):
                return {
                    "trace_id": 8,
                    "trace_type": "gift",
                    "effect_type": "blessing",
                    "message": "前人留下护道残念。",
                    "toxicity_score": 0,
                }

            async def mark_triggered(self, trace_id, harm_delta=0, death_caused=False):
                self.marked.append((trace_id, harm_delta, death_caused))

        monkeypatch.setattr("server.interface.ws.random.randint", lambda *_: 1)
        repo = FakeKarmaTraceRepo()
        mgr = ConnectionManager(karma_trace_repo=repo)
        engine = GameEngine()
        engine.new_game()
        old_foundation = engine.session.foundation
        result = TickResult(
            stage=Stage.IDLE,
            log_text="【平淡日常】打坐。",
            event_type="LOCAL",
            sin_value=0,
            foundation=old_foundation,
        )

        await _maybe_apply_karma_trace_event(mgr, engine, result)

        assert "前人馈赠" in result.log_text
        assert engine.session.foundation == min(100, old_foundation + 1)
        assert repo.marked == [(8, 0, False)]


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

    @pytest.mark.asyncio
    async def test_consume_deafness_protocol_once(self):
        """失聪协议进入新局时消费 1 次库存"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        account = PlayerAccount(
            player_id="test_consume_deafness",
            player_name="失聪修士",
            deafness_protocol=2,
        )
        await repo.save(account)

        assert await repo.consume_deafness_protocol("test_consume_deafness") is True
        updated = await repo.get("test_consume_deafness")
        assert updated.deafness_protocol == 1

        assert await repo.consume_deafness_protocol("test_consume_deafness") is True
        updated2 = await repo.get("test_consume_deafness")
        assert updated2.deafness_protocol == 0

        assert await repo.consume_deafness_protocol("test_consume_deafness") is False

    @pytest.mark.asyncio
    async def test_consume_karma_shield_once(self):
        """因果遮蔽卡触发时消费 1 张库存"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        account = PlayerAccount(
            player_id="test_consume_shield",
            player_name="遮蔽修士",
            karma_shield=1,
        )
        await repo.save(account)

        assert await repo.consume_karma_shield("test_consume_shield") is True
        updated = await repo.get("test_consume_shield")
        assert updated.karma_shield == 0

        assert await repo.consume_karma_shield("test_consume_shield") is False

    @pytest.mark.asyncio
    async def test_update_heaven_points_clamped_at_zero(self):
        """账户扣点不会把天道点减成负数"""
        from server.infrastructure.db import get_engine, get_session_factory
        from server.infrastructure.models import Base
        from server.infrastructure.storage import PlayerAccountRepository
        from server.domain.player import PlayerAccount

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        sf = get_session_factory()
        repo = PlayerAccountRepository(sf)

        account = PlayerAccount(
            player_id="test_penalty_clamp",
            player_name="倒霉修士",
            heaven_points=8,
        )
        await repo.save(account)

        await repo.update_heaven_points("test_penalty_clamp", -50)
        updated = await repo.get("test_penalty_clamp")
        assert updated.heaven_points == 0
