"""
全服共享状态管理器

持有跨连接的单例数据：死亡因果池、飞升名人堂。
GameEngine 通过构造函数依赖注入获取引用，替代 M1 的实例级 list。

设计原则：
- DeadRegistryManager：封装 MySQL dead_registry + Redis 怨念 Set/List
- ImmortalHallManager：封装 MySQL immortal_hall
- 两者均为全服单例，在 app 启动时创建，所有 WebSocket 连接共享
"""

from server.domain.player import DeadRecord
from server.infrastructure.storage import DeadRegistryRepository, ImmortalHallRepository
from server.infrastructure.redis import RedisClient


class DeadRegistryManager:
    """全服死亡因果池管理器"""

    def __init__(self, repo: DeadRegistryRepository, redis: RedisClient):
        self._repo = repo
        self._redis = redis

    async def add_record(self, record: DeadRecord) -> int:
        """插入死亡记录并推入怨念候选列表，返回自增 ID"""
        record_id = await self._repo.insert(record)
        await self._redis.push_resentment_candidate(record.dead_title)
        return record_id

    async def random_karma(self) -> str:
        """随机获取一条怨念死因。

        优先从 Redis 怨念 Set 抽取（精品缓存），
        fallback 到 MySQL 随机查询。
        """
        title = await self._redis.random_resentment()
        if title:
            return f"此地曾有真实修士因【{title}】而死。"

        rows = await self._repo.random_dead_title(limit=1)
        if rows:
            r = rows[0]
            return f"此地曾有真实玩家【{r['player_name']}】因【{r['dead_title']}】而死。"
        return ""

    async def count(self) -> int:
        return await self._repo.count()


class ImmortalHallManager:
    """全服飞升名人堂管理器"""

    def __init__(self, repo: ImmortalHallRepository):
        self._repo = repo

    async def add_ascension(
        self, player_id: str, player_name: str, ascension_title: str, heaven_points: int
    ):
        await self._repo.insert(player_id, player_name, ascension_title, heaven_points)

    async def get_top(self, limit: int = 50) -> list[dict]:
        return await self._repo.get_top(limit)
