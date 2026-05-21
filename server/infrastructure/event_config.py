"""
本地事件配置加载与动态模板组装

从 Config_Normal_Events.json 加载三层池（common / realm_specific / sin_conditional），
根据玩家状态随机抽取并渲染事件文本。
"""

import random
import re
import json
from pathlib import Path
from typing import Optional

from server.domain.event import LocalEventResult


# ═══════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════

_DATA_DIR = Path(__file__).parent.parent / "data"
_DEFAULT_CONFIG_PATH = _DATA_DIR / "Config_Normal_Events.json"


class EventConfigLoader:
    """加载并缓存本地事件配置"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or _DEFAULT_CONFIG_PATH
        self._config: dict = {}
        self._loaded = False

    def load(self) -> dict:
        if not self._loaded:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            self._loaded = True
        return self._config

    def reload(self):
        self._loaded = False
        return self.load()

    @property
    def pools(self) -> dict:
        if not self._loaded:
            self.load()
        return self._config.get("pools", {})


# 全局单例
_event_loader = EventConfigLoader()


# ═══════════════════════════════════════════════════════════════
# 动态模板渲染
# ═══════════════════════════════════════════════════════════════

def _try_find_key(placeholder: str, data: dict) -> str | None:
    """在 data 中查找占位符对应的键，自动处理单复数不匹配。

    例如模板用 {location} 但 JSON 键为 locations；模板用 {reactions} 但 JSON 键为 reaction。
    """
    if placeholder in data:
        return placeholder
    # 尝试复数形式：location → locations
    plural = placeholder + "s"
    if plural in data:
        return plural
    # 尝试单数形式：reactions → reaction（排除以 ss/us 结尾的词）
    if placeholder.endswith("s") and not placeholder.endswith(("ss", "us")):
        singular = placeholder[:-1]
        if singular in data:
            return singular
    return None


def _extract_placeholders(template: str) -> list:
    """提取模板中所有 {placeholder} 变量名"""
    return re.findall(r"\{(\w+)\}", template)


def _render_template(template: str, event_data: dict) -> str:
    """将模板中的占位符替换为事件配置中的随机选择值"""
    placeholders = _extract_placeholders(template)
    render_dict = {}

    for ph in placeholders:
        if ph in event_data:
            val = event_data[ph]
            if isinstance(val, list):
                render_dict[ph] = random.choice(val)
            elif isinstance(val, str):
                render_dict[ph] = val
            else:
                render_dict[ph] = str(val)

    return template.format(**render_dict)


# ═══════════════════════════════════════════════════════════════
# 事件路由与生成
# ═══════════════════════════════════════════════════════════════

def generate_local_event(
    realm_code: int,
    current_sin: int,
    pools: Optional[dict] = None,
) -> LocalEventResult:
    """
    根据玩家状态从三层池中抽取并拼装本地事件。

    Args:
        realm_code: 玩家当前境界代号 (1-7)
        current_sin: 玩家当前天谴值
        pools: 可选的外部配置（用于测试注入）

    Returns:
        LocalEventResult: 包含文本、数值增量和风味标签的完整事件
    """
    if pools is None:
        pools = _event_loader.pools

    # 1. 按权重选择池
    common_weight = pools.get("common", {}).get("weight", 70)
    realm_weight = pools.get("realm_specific", {}).get("weight", 20)
    sin_weight = pools.get("sin_conditional", {}).get("weight", 10)

    pool_name = random.choices(
        population=["common", "realm_specific", "sin_conditional"],
        weights=[common_weight, realm_weight, sin_weight],
        k=1,
    )[0]

    # 2. 从池中筛选有效事件列表
    event_list = []

    if pool_name == "sin_conditional":
        triggers = pools.get("sin_conditional", {}).get("triggers", [])
        valid_events = []
        for t in triggers:
            if current_sin >= t.get("min_sin", 0):
                valid_events.extend(t.get("events", []))
        event_list = valid_events if valid_events else pools.get("common", {}).get("events", [])

    elif pool_name == "realm_specific":
        realm_str = str(realm_code)
        realm_pools = pools.get("realm_specific", {})
        if realm_str in realm_pools:
            event_list = realm_pools[realm_str].get("events", [])
        if not event_list:
            event_list = pools.get("common", {}).get("events", [])

    else:
        event_list = pools.get("common", {}).get("events", [])

    # 3. 安全降级
    if not event_list:
        event_list = pools.get("common", {}).get("events", [])
    if not event_list:
        # 终极兜底
        return LocalEventResult(
            event_id="fallback_001",
            log_text="你在虚空中打坐，灵气稀薄，几乎没涨修为。",
            cultivation_delta=1,
        )

    # 4. 随机抽取一个事件模板
    event_tpl = random.choice(event_list)

    # 5. 计算 cultivation_delta 和渲染结果文本
    cultivation_delta = 0
    template_str = event_tpl.get("template", "")
    placeholders = _extract_placeholders(template_str)
    render_dict = {}

    # 处理 results 分支
    if "results" in event_tpl:
        res_pool = event_tpl["results"]
        weights = [r.get("weight", 1) for r in res_pool]
        chosen_res = random.choices(res_pool, weights=weights, k=1)[0]
        render_dict["result_text"] = chosen_res.get("text", "")
        cult_range = chosen_res.get("cultivation_delta", [0, 0])
        cultivation_delta = random.randint(cult_range[0], cult_range[1])

        # 处理 outcome 等嵌套对象占位符
        for ph in placeholders:
            if ph == "result_text":
                continue
            key = _try_find_key(ph, event_tpl)
            if key is not None:
                val = event_tpl[key]
                if isinstance(val, list):
                    picked = random.choice(val)
                    if isinstance(picked, dict):
                        # 嵌套结果对象，如 {outcome} 指向 {"text": "...", "cultivation_delta": [...]}
                        render_dict[ph] = picked.get("text", str(picked))
                        if "cultivation_delta" in picked:
                            extra_range = picked["cultivation_delta"]
                            cultivation_delta += random.randint(extra_range[0], extra_range[1])
                    else:
                        render_dict[ph] = picked
                elif isinstance(val, str):
                    render_dict[ph] = val

    elif "cultivation_delta" in event_tpl:
        cult_range = event_tpl["cultivation_delta"]
        cultivation_delta = random.randint(cult_range[0], cult_range[1])

    # 6. 渲染普通占位符（跳过已在 results 分支处理的）
    for ph in placeholders:
        if ph == "result_text":
            continue
        if ph in render_dict:
            continue
        key = _try_find_key(ph, event_tpl)
        if key is not None:
            val = event_tpl[key]
            if isinstance(val, list) and val:
                picked = random.choice(val)
                if isinstance(picked, dict):
                    render_dict[ph] = picked.get("text", str(picked))
                else:
                    render_dict[ph] = picked
            elif isinstance(val, str):
                render_dict[ph] = val

    # 7. 组装最终文本
    try:
        final_text = template_str.format(**render_dict)
    except KeyError:
        final_text = template_str  # 兜底：直接返回原始模板

    return LocalEventResult(
        event_id=event_tpl.get("id", "unknown"),
        log_text=final_text,
        cultivation_delta=cultivation_delta,
        flavor=event_tpl.get("flavor", "normal"),
    )
