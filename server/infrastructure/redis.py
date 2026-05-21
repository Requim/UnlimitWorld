"""
Redis 异步连接池封装

提供 M2 三大 Redis 数据结构的高层访问方法：
  - player:session:{pid}  Hash   — 玩家实时状态快照
  - dead:resentment:set   Set    — 精品怨念死因集合
  - dead:resentment:candidates  List — 待评分候选死因
"""

import redis.asyncio as aioredis

from server.config import settings


class RedisClient:
    def __init__(self):
        self._pool: aioredis.ConnectionPool | None = None
        self._client: aioredis.Redis | None = None

    async def connect(self):
        if self._client is None:
            self._pool = aioredis.ConnectionPool(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                db=settings.redis_db,
                decode_responses=True,
                max_connections=20,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)

    async def disconnect(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._pool = None

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis 未连接，请先调用 connect()")
        return self._client

    # ── player:session:{pid} ──

    @staticmethod
    def _session_key(player_id: str) -> str:
        return f"player:session:{player_id}"

    async def save_session(self, player_id: str, data: dict):
        """写入玩家会话快照（HMSET）"""
        await self.client.hset(self._session_key(player_id), mapping=data)

    async def get_session(self, player_id: str) -> dict:
        """读取玩家会话快照"""
        return await self.client.hgetall(self._session_key(player_id))

    async def delete_session(self, player_id: str):
        """删除玩家会话"""
        await self.client.delete(self._session_key(player_id))

    # ── dead:resentment:candidates (List) ──

    async def push_resentment_candidate(self, dead_title: str):
        """追加候选死因到待评分列表"""
        await self.client.rpush("dead:resentment:candidates", dead_title)

    async def pop_resentment_candidates(self, count: int = -1) -> list:
        """
        取出并清空候选列表（原子操作：RENAME → LRANGE → DEL）。
        count=-1 表示全部取出。
        """
        tmp_key = "dead:resentment:candidates:bak"
        # 原子重命名，避免并发写入丢失
        renamed = await self.client.rename("dead:resentment:candidates", tmp_key)
        if not renamed:
            return []
        items = await self.client.lrange(tmp_key, 0, count if count > 0 else -1)
        await self.client.delete(tmp_key)
        return items

    # ── dead:resentment:set (Set) ──

    async def replace_resentment_set(self, items: list[str]):
        """全量替换怨念 Set（先 DEL 再 SADD）"""
        key = "dead:resentment:set"
        await self.client.delete(key)
        if items:
            await self.client.sadd(key, *items)

    async def random_resentment(self) -> str | None:
        """随机抽取一条怨念死因"""
        return await self.client.srandmember("dead:resentment:set")

    # ── 分布式锁（怨念池清洗防重） ──

    async def acquire_lock(self, lock_name: str, ttl: int = 120) -> bool:
        """尝试获取分布式锁，返回是否成功"""
        return await self.client.set(
            f"lock:{lock_name}", "1", nx=True, ex=ttl
        )

    async def release_lock(self, lock_name: str):
        """释放分布式锁"""
        await self.client.delete(f"lock:{lock_name}")
