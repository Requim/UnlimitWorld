"""可持久化的确定性随机源。"""

from __future__ import annotations

import hashlib

from .models import RunState


def randbelow(run: RunState, upper: int) -> int:
    """消费局面的随机计数器并返回 [0, upper)；会修改计数器，upper 非正时报错。"""
    if upper <= 0:
        raise ValueError("upper must be positive")
    raw = f"{run.rng_seed}:{run.rng_counter}".encode("ascii")
    run.rng_counter += 1
    return int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "big") % upper


def shuffle(run: RunState, items: list) -> None:
    """使用局面随机流原地洗牌；会推进随机计数器。"""
    for index in range(len(items) - 1, 0, -1):
        target = randbelow(run, index + 1)
        items[index], items[target] = items[target], items[index]


def sample_unique(run: RunState, items: list, count: int) -> list:
    """从序列中无放回抽取；会推进随机计数器，数量不足时返回全部。"""
    pool = list(items)
    shuffle(run, pool)
    return pool[: min(count, len(pool))]
