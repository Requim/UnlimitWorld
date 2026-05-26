"""
Repository 抽象层

封装 MySQL（SQLAlchemy）与 Redis 的读写操作，向上层（GameEngine / ws.py）提供统一接口。
所有方法均为 async，遵循 DDD 依赖方向：infrastructure → application。
"""

from datetime import datetime

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.domain.player import PlayerState, PlayerAccount, DeadRecord, ActiveSession
from server.infrastructure.models import (
    PlayerAccountModel,
    DeadRegistryModel,
    ImmortalHallModel,
    LeaderboardEntryModel,
    KarmaTraceModel,
    ActiveSessionModel,
    HeavenOverlordPoolModel,
)
from server.infrastructure.redis import RedisClient


# ═══════════════════════════════════════════════════════════════
# PlayerAccountRepository
# ═══════════════════════════════════════════════════════════════

class PlayerAccountRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def get_or_create(self, player_id: str, player_name: str = "无名修士") -> PlayerAccount:
        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, player_id)
            if row is None:
                row = PlayerAccountModel(
                    player_id=player_id,
                    player_name=player_name,
                    created_at=datetime.now(),
                    last_login=datetime.now(),
                )
                sess.add(row)
                await sess.commit()
                await sess.refresh(row)
            else:
                row.last_login = datetime.now()
                await sess.commit()
            return _account_from_orm(row)

    async def update_heaven_points(self, player_id: str, delta: int):
        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, player_id)
            if row:
                row.heaven_points = max(0, row.heaven_points + delta)
                await sess.commit()

    async def consume_deafness_protocol(self, player_id: str) -> bool:
        """消费 1 次天道失聪协议库存。"""
        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, player_id)
            if row is None or row.deafness_protocol <= 0:
                return False
            row.deafness_protocol -= 1
            await sess.commit()
            return True

    async def consume_karma_shield(self, player_id: str) -> bool:
        """消费 1 张因果遮蔽卡库存。"""
        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, player_id)
            if row is None or row.karma_shield <= 0:
                return False
            row.karma_shield -= 1
            await sess.commit()
            return True

    async def get(self, player_id: str) -> PlayerAccount | None:
        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, player_id)
            if row is None:
                return None
            return _account_from_orm(row)

    async def save(self, account: PlayerAccount):
        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, account.player_id)
            if row is None:
                row = PlayerAccountModel(**account.model_dump())
                sess.add(row)
            else:
                for k, v in account.model_dump().items():
                    setattr(row, k, v)
            await sess.commit()

    # ── Phase 3B：商店购买操作 ──

    async def _clear_sin_reset(self, player_id: str):
        """Phase 3B：消费功德洗白券标记"""
        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, player_id)
            if row:
                row.pending_sin_reset = 0
                await sess.commit()

    async def buy_item(self, player_id: str, item_id: str, cost: int) -> bool:
        """扣除天道点并应用道具效果。返回是否购买成功。"""
        from server.domain.shop import find_item
        item = find_item(item_id)
        if item is None:
            return False

        async with self._sf() as sess:
            row = await sess.get(PlayerAccountModel, player_id)
            if row is None:
                return False
            if row.heaven_points < cost:
                return False

            row.heaven_points -= cost

            if item.effect == "karma_shield":
                row.karma_shield += item.value
            elif item.effect == "deafness_protocol":
                row.deafness_protocol += item.value
            elif item.effect == "sin_reset":
                row.pending_sin_reset = 1

            await sess.commit()
            return True


# ═══════════════════════════════════════════════════════════════
# DeadRegistryRepository
# ═══════════════════════════════════════════════════════════════

class DeadRegistryRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def insert(self, record: DeadRecord) -> int:
        """插入死亡记录，返回自增 ID"""
        async with self._sf() as sess:
            row = DeadRegistryModel(**record.model_dump())
            sess.add(row)
            await sess.commit()
            await sess.refresh(row)
            return row.id

    async def random_dead_title(self, limit: int = 1) -> list[dict]:
        """随机获取死因记录（ORDER BY RAND()，怨念池 fallback）"""
        async with self._sf() as sess:
            from sqlalchemy import func
            stmt = select(DeadRegistryModel).order_by(func.rand()).limit(limit)
            result = await sess.execute(stmt)
            rows = result.scalars().all()
            return [
                {"player_name": r.player_name, "dead_title": r.dead_title, "realm": r.realm}
                for r in rows
            ]

    async def count(self) -> int:
        async with self._sf() as sess:
            from sqlalchemy import func
            stmt = select(func.count()).select_from(DeadRegistryModel)
            result = await sess.execute(stmt)
            return result.scalar() or 0


# ═══════════════════════════════════════════════════════════════
# ImmortalHallRepository
# ═══════════════════════════════════════════════════════════════

class ImmortalHallRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def insert(self, player_id: str, player_name: str, ascension_title: str, heaven_points: int):
        async with self._sf() as sess:
            row = ImmortalHallModel(
                player_id=player_id,
                player_name=player_name,
                ascension_title=ascension_title,
                total_heaven_points=heaven_points,
                ascended_at=datetime.now(),
            )
            sess.add(row)
            await sess.commit()

    async def get_top(self, limit: int = 50) -> list[dict]:
        async with self._sf() as sess:
            stmt = (
                select(ImmortalHallModel)
                .order_by(ImmortalHallModel.total_heaven_points.desc())
                .limit(limit)
            )
            result = await sess.execute(stmt)
            rows = result.scalars().all()
            return [
                {"player_name": r.player_name, "ascension_title": r.ascension_title,
                 "total_heaven_points": r.total_heaven_points, "ascended_at": r.ascended_at.isoformat()}
                for r in rows
            ]


# ═══════════════════════════════════════════════════════════════
# LeaderboardRepository
# ═══════════════════════════════════════════════════════════════

class LeaderboardRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def insert(
        self,
        leaderboard_type: str,
        player_id: str,
        player_name: str,
        title: str,
        score: int,
        realm: str = "",
        summary: str = "",
    ):
        async with self._sf() as sess:
            row = LeaderboardEntryModel(
                leaderboard_type=leaderboard_type,
                player_id=player_id,
                player_name=player_name,
                title=title,
                score=score,
                realm=realm,
                summary=summary,
                created_at=datetime.now(),
            )
            sess.add(row)
            await sess.commit()

    async def get_top(self, leaderboard_type: str, limit: int = 50) -> list[dict]:
        async with self._sf() as sess:
            stmt = (
                select(LeaderboardEntryModel)
                .where(LeaderboardEntryModel.leaderboard_type == leaderboard_type)
                .order_by(LeaderboardEntryModel.score.desc(), LeaderboardEntryModel.created_at.desc())
                .limit(limit)
            )
            result = await sess.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "leaderboard_type": r.leaderboard_type,
                    "player_name": r.player_name,
                    "title": r.title,
                    "score": r.score,
                    "realm": r.realm,
                    "summary": r.summary,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]


# ═══════════════════════════════════════════════════════════════
# KarmaTraceRepository
# ═══════════════════════════════════════════════════════════════

class KarmaTraceRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def insert(
        self,
        source_player_id: str,
        source_player_name: str,
        trace_type: str,
        effect_type: str,
        message: str,
        toxicity_score: int = 0,
        source_run_id: str = "",
        is_approved: bool = True,
    ) -> int:
        async with self._sf() as sess:
            row = KarmaTraceModel(
                source_player_id=source_player_id,
                source_player_name=source_player_name,
                source_run_id=source_run_id,
                trace_type=trace_type,
                effect_type=effect_type,
                message=message,
                toxicity_score=toxicity_score,
                is_approved=1 if is_approved else 0,
                created_at=datetime.now(),
            )
            sess.add(row)
            await sess.commit()
            await sess.refresh(row)
            return row.id

    async def get_recent(self, limit: int = 20) -> list[dict]:
        async with self._sf() as sess:
            stmt = (
                select(KarmaTraceModel)
                .where(KarmaTraceModel.is_approved == 1)
                .order_by(KarmaTraceModel.created_at.desc())
                .limit(limit)
            )
            result = await sess.execute(stmt)
            rows = result.scalars().all()
            return [
                {
                    "trace_id": r.id,
                    "source_player_name": r.source_player_name,
                    "trace_type": r.trace_type,
                    "effect_type": r.effect_type,
                    "message": r.message,
                    "toxicity_score": r.toxicity_score,
                    "trigger_count": r.trigger_count,
                    "harm_score": r.harm_score,
                    "death_caused_count": r.death_caused_count,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]


# ═══════════════════════════════════════════════════════════════
# ActiveSessionRepository
# ═══════════════════════════════════════════════════════════════

class ActiveSessionRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def upsert(self, session_data: ActiveSession):
        """写入或更新活跃会话"""
        async with self._sf() as sess:
            row = await sess.get(ActiveSessionModel, session_data.player_id)
            if row is None:
                row = ActiveSessionModel(
                    player_id=session_data.player_id,
                    session_json=session_data.session_json,
                    stage=session_data.stage,
                    trigger_json=session_data.trigger_json,
                    updated_at=datetime.now(),
                )
                sess.add(row)
            else:
                row.session_json = session_data.session_json
                row.stage = session_data.stage
                row.trigger_json = session_data.trigger_json
                row.updated_at = datetime.now()
            await sess.commit()

    async def get(self, player_id: str) -> ActiveSession | None:
        async with self._sf() as sess:
            row = await sess.get(ActiveSessionModel, player_id)
            if row is None:
                return None
            return ActiveSession(
                player_id=row.player_id,
                session_json=row.session_json,
                stage=row.stage,
                trigger_json=row.trigger_json,
                updated_at=row.updated_at,
            )

    async def delete(self, player_id: str):
        async with self._sf() as sess:
            await sess.execute(delete(ActiveSessionModel).where(ActiveSessionModel.player_id == player_id))
            await sess.commit()


# ═══════════════════════════════════════════════════════════════
# HeavenOverlordPoolRepository
# ═══════════════════════════════════════════════════════════════

class HeavenOverlordPoolRepository:
    def __init__(self, session_factory: async_sessionmaker):
        self._sf = session_factory

    async def insert(self, dead_registry_id: int, player_name: str, dead_title: str, realm_code: int):
        async with self._sf() as sess:
            row = HeavenOverlordPoolModel(
                dead_registry_id=dead_registry_id,
                player_name=player_name,
                dead_title=dead_title,
                realm_code=realm_code,
                created_at=datetime.now(),
            )
            sess.add(row)
            await sess.commit()

    async def fetch_unselected(self, limit: int = 500) -> list[dict]:
        """获取未选入怨念 Set 的候选记录"""
        async with self._sf() as sess:
            stmt = (
                select(HeavenOverlordPoolModel)
                .where(HeavenOverlordPoolModel.is_selected == 0)
                .order_by(HeavenOverlordPoolModel.created_at.desc())
                .limit(limit)
            )
            result = await sess.execute(stmt)
            rows = result.scalars().all()
            return [
                {"id": r.id, "dead_title": r.dead_title, "realm_code": r.realm_code}
                for r in rows
            ]

    async def mark_selected(self, ids: list[int]):
        """批量标记为已选入怨念 Set"""
        if not ids:
            return
        async with self._sf() as sess:
            await sess.execute(
                update(HeavenOverlordPoolModel)
                .where(HeavenOverlordPoolModel.id.in_(ids))
                .values(is_selected=1)
            )
            await sess.commit()


# ═══════════════════════════════════════════════════════════════
# 聚合仓储（便捷入口）
# ═══════════════════════════════════════════════════════════════

class GameRepository:
    """聚合仓储，封装所有子仓储，简化上层依赖注入"""

    def __init__(self, session_factory: async_sessionmaker, redis: RedisClient):
        self.accounts = PlayerAccountRepository(session_factory)
        self.dead_registry = DeadRegistryRepository(session_factory)
        self.immortal_hall = ImmortalHallRepository(session_factory)
        self.active_session = ActiveSessionRepository(session_factory)
        self.heaven_pool = HeavenOverlordPoolRepository(session_factory)
        self.redis = redis
        self._sf = session_factory


# ═══════════════════════════════════════════════════════════════
# ORM → Domain 映射
# ═══════════════════════════════════════════════════════════════

def _account_from_orm(row: PlayerAccountModel) -> PlayerAccount:
    return PlayerAccount(
        player_id=row.player_id,
        wechat_openid=row.wechat_openid,
        player_name=row.player_name,
        avatar_url=row.avatar_url,
        heaven_points=row.heaven_points,
        deafness_protocol=row.deafness_protocol,
        karma_shield=row.karma_shield,
        pending_sin_reset=bool(row.pending_sin_reset),
        talent_bonus=row.talent_bonus or {},
        created_at=row.created_at,
        last_login=row.last_login,
    )
