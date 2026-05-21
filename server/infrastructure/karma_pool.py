"""
全服怨念池管理器

负责怨念候选的评分、清洗、定时注入 Redis 怨念 Set。
Phase 2D 将通过 FastAPI 后台任务调度 clean_and_refill()。

怨念抽取流程：
  每次 tick → _process_local_event():
    roll = random(1..100)
    if roll <= 5:   → _trigger_resentment_llm_event()   # 5% LLM 心魔试炼
    elif roll <= 15: → _trigger_resentment_local_event() # 10% 本地血红日志
    else: → 原有本地日常逻辑
"""

import re
from server.config import settings
from server.infrastructure.redis import RedisClient
from server.infrastructure.storage import HeavenOverlordPoolRepository, DeadRegistryRepository


# ── 死因精品评分关键词 ──

_SCORE_KEYWORDS = [
    # 高价值词（+15 分/词）
    (15, [
        "天谴", "神罚", "天道", "飞升", "陨落", "夺舍", "心魔",
        "因果", "轮回", "九天", "万古", "仙穹", "逆天", "天劫",
        "洪荒", "混沌", "大道", "涅槃", "化道",
    ]),
    # 中价值词（+8 分/词）
    (8, [
        "雷劫", "天魔", "血祭", "献祭", "破灭", "镇杀", "封印",
        "疯狂", "执念", "执迷", "妄念", "业火", "红尘", "杀伐",
        "禁忌", "上古", "远古", "仙帝", "魔帝", "剑仙",
    ]),
    # 趣味词（+5 分/词）
    (5, [
        "骚话", "对线", "怼", "嘴硬", "装逼", "翻车", "打脸",
        "作死", "浪", "苟", "躺平", "内卷", "摆烂", "摸鱼",
    ]),
]


def score_dead_title(title: str) -> float:
    """对死因标题进行精品评分（0-100）。

    评分维度：
    - 长度：5-80 字符最佳，过短或过长扣分
    - 关键词匹配：修仙/戏剧性词汇加分
    - 总分 clamp 到 [0, 100]
    """
    score = 50.0
    length = len(title)

    # 长度评分
    if 10 <= length <= 60:
        score += 15
    elif 5 <= length <= 80:
        score += 5
    elif length < 3:
        score -= 30
    elif length > 120:
        score -= 10

    # 关键词匹配
    for weight, keywords in _SCORE_KEYWORDS:
        for kw in keywords:
            if kw in title:
                score += weight

    return max(0.0, min(100.0, score))


class KarmaPoolManager:
    """怨念池全生命周期管理器"""

    def __init__(
        self,
        redis: RedisClient,
        heaven_pool_repo: HeavenOverlordPoolRepository,
        dead_registry_repo: DeadRegistryRepository,
    ):
        self._redis = redis
        self._heaven_pool = heaven_pool_repo
        self._dead_registry = dead_registry_repo

    async def clean_and_refill(self) -> int:
        """执行一次怨念池清洗 + 注入。

        流程：
        1. 获取分布式锁（防并发重复执行）
        2. 从 Redis List 原子弹出候选死因
        3. 从 MySQL heaven_overlord_pool 拉取未入选记录
        4. 合并评分，取 top N
        5. 替换 Redis 怨念 Set
        6. 标记 MySQL 记录为已入选
        7. 释放锁

        返回：本次注入怨念 Set 的数量。
        """
        lock_name = "karma_pool_clean"
        acquired = await self._redis.acquire_lock(lock_name, ttl=120)
        if not acquired:
            return 0

        try:
            # 1. 从 Redis 弹出候选
            redis_titles = await self._redis.pop_resentment_candidates()

            # 2. 从 MySQL 拉取未入选记录
            mysql_rows = await self._heaven_pool.fetch_unselected(limit=500)

            # 3. 合并 + 去重 + 评分
            scored: list[tuple[float, str, list[int] | None]] = []
            seen: set[str] = set()

            for title in redis_titles:
                title = title.strip()
                if title and title not in seen:
                    seen.add(title)
                    scored.append((score_dead_title(title), title, None))

            for row in mysql_rows:
                title = row["dead_title"].strip()
                if title and title not in seen:
                    seen.add(title)
                    scored.append((score_dead_title(title), title, [row["id"]]))

            if not scored:
                return 0

            # 4. 按评分降序，取 top N
            scored.sort(key=lambda x: x[0], reverse=True)
            top_n = settings.karma_pool_top_n
            top_items = scored[:top_n]

            # 5. 替换 Redis 怨念 Set
            top_titles = [item[1] for item in top_items]
            await self._redis.replace_resentment_set(top_titles)

            # 6. 标记 MySQL 记录为已入选
            mysql_ids: list[int] = []
            for _, _, ids in top_items:
                if ids:
                    mysql_ids.extend(ids)
            if mysql_ids:
                await self._heaven_pool.mark_selected(mysql_ids)

            return len(top_titles)

        finally:
            await self._redis.release_lock(lock_name)

    async def random_resentment(self) -> str | None:
        """随机获取一条怨念死因。

        优先 Redis Set（精品缓存），fallback 到 MySQL。
        """
        title = await self._redis.random_resentment()
        if title:
            return title

        rows = await self._dead_registry.random_dead_title(limit=1)
        if rows:
            return rows[0]["dead_title"]
        return None
