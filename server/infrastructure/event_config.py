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

from server.domain.event import LocalEventChoice, LocalEventResult


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

PERSONA_POOL_BONUS: dict[str, dict[str, int]] = {
    "因果账房先生": {"karma_echo": 35, "temptation": 10},
    "命盘赌坊主": {"gamble": 40, "temptation": 20},
    "朱笔记仇官": {"taunt": 35, "karma_echo": 15},
    "玉律监考官": {"merit": 35, "cultivation": 10},
    "混沌乐子人": {"temptation": 25, "gamble": 25, "heaven_gaze": 15},
}


def _extract_delta(value, default: int = 0) -> int:
    """从整数或 [min, max] 区间中取出本次数值。"""
    if isinstance(value, list) and len(value) >= 2:
        return random.randint(int(value[0]), int(value[1]))
    if isinstance(value, int):
        return value
    return default


def _apply_effects_from_dict(effects: dict, result: LocalEventResult):
    """将轻选择 effects 累加到 LocalEventResult。"""
    result.cultivation_delta += _extract_delta(effects.get("cultivation_delta"))
    result.sin_delta += _extract_delta(effects.get("sin_delta"))
    result.luck_delta += _extract_delta(effects.get("luck_delta"))
    result.foundation_delta += _extract_delta(effects.get("foundation_delta"))
    result.ambition_progress_delta += int(effects.get("ambition_progress_delta", 0) or 0)
    result.leaderboard_score_delta += int(effects.get("leaderboard_score_delta", 0) or 0)
    result.taunt_count += int(effects.get("taunt_count", 0) or 0)
    result.gamble_survive_count += int(effects.get("gamble_survive_count", 0) or 0)
    result.karma_pollution_score += int(effects.get("karma_pollution_score", 0) or 0)
    result.death_drama_score += int(effects.get("death_drama_score", 0) or 0)


def _pool_weight(pool_name: str, pool_data: dict, heaven_persona: str = "") -> int:
    weight = int(pool_data.get("weight", 1) or 0)
    weight += PERSONA_POOL_BONUS.get(heaven_persona, {}).get(pool_name, 0)
    return max(0, weight)


def _choose_from_normal_pools(
    normal_pools: dict,
    heaven_persona: str = "",
) -> tuple[str, dict, dict]:
    candidates = []
    weights = []
    for pool_name, pool_data in normal_pools.items():
        events = pool_data.get("events", [])
        if not events:
            continue
        candidates.append((pool_name, pool_data))
        weights.append(_pool_weight(pool_name, pool_data, heaven_persona))

    if not candidates:
        return "", {}, {}

    if sum(weights) <= 0:
        weights = [1 for _ in candidates]

    pool_name, pool_data = random.choices(candidates, weights=weights, k=1)[0]
    return pool_name, pool_data, random.choice(pool_data.get("events", []))


def _select_legacy_event(
    realm_code: int,
    current_sin: int,
    pools: dict,
) -> tuple[str, dict]:
    """按 M1-M2 三层池规则抽取事件模板，保持旧配置兼容。"""
    common_weight = pools.get("common", {}).get("weight", 70)
    realm_weight = pools.get("realm_specific", {}).get("weight", 20)
    sin_weight = pools.get("sin_conditional", {}).get("weight", 10)

    pool_name = random.choices(
        population=["common", "realm_specific", "sin_conditional"],
        weights=[common_weight, realm_weight, sin_weight],
        k=1,
    )[0]

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

    if not event_list:
        event_list = pools.get("common", {}).get("events", [])

    if not event_list:
        return "common", {}

    return pool_name, random.choice(event_list)


def _fill_placeholders_from_event(
    placeholders: list,
    event_tpl: dict,
    render_dict: dict,
) -> int:
    cultivation_delta = 0
    for ph in placeholders:
        if ph == "result_text" or ph in render_dict:
            continue
        key = _try_find_key(ph, event_tpl)
        if key is None:
            continue
        val = event_tpl[key]
        if isinstance(val, list) and val:
            picked = random.choice(val)
            if isinstance(picked, dict):
                render_dict[ph] = picked.get("text", str(picked))
                if "cultivation_delta" in picked:
                    cultivation_delta += _extract_delta(picked["cultivation_delta"])
            else:
                render_dict[ph] = picked
        elif isinstance(val, str):
            render_dict[ph] = val
    return cultivation_delta


def _apply_results_branch(event_tpl: dict, placeholders: list, render_dict: dict) -> int:
    res_pool = event_tpl["results"]
    weights = [r.get("weight", 1) for r in res_pool]
    chosen_res = random.choices(res_pool, weights=weights, k=1)[0]
    render_dict["result_text"] = chosen_res.get("text", "")
    cultivation_delta = _extract_delta(chosen_res.get("cultivation_delta", [0, 0]))
    cultivation_delta += _fill_placeholders_from_event(placeholders, event_tpl, render_dict)
    return cultivation_delta


def _render_event_template(event_tpl: dict) -> tuple[str, int]:
    """渲染事件模板并返回文本与修为增量。"""
    cultivation_delta = 0
    template_str = event_tpl.get("template", "")
    placeholders = _extract_placeholders(template_str)
    render_dict = {}

    if "results" in event_tpl:
        cultivation_delta = _apply_results_branch(event_tpl, placeholders, render_dict)
    elif "cultivation_delta" in event_tpl:
        cultivation_delta = _extract_delta(event_tpl["cultivation_delta"])

    cultivation_delta += _fill_placeholders_from_event(placeholders, event_tpl, render_dict)

    try:
        final_text = template_str.format(**render_dict)
    except KeyError:
        final_text = template_str

    return final_text, cultivation_delta


def _build_light_choices(raw_choices: list) -> list[LocalEventChoice]:
    choices = []
    for raw in raw_choices:
        if not isinstance(raw, dict):
            continue
        choices.append(
            LocalEventChoice(
                id=str(raw.get("id", "")),
                text=str(raw.get("text", "")),
                result_text=str(raw.get("result_text", "")),
                effects=raw.get("effects", {}) if isinstance(raw.get("effects", {}), dict) else {},
            )
        )
    return choices


def _auto_pick_choice(choices: list[LocalEventChoice]) -> LocalEventChoice | None:
    if not choices:
        return None
    return random.choice(choices)


def _select_event_template(
    realm_code: int,
    current_sin: int,
    pools: dict,
    heaven_persona: str,
) -> tuple[str, str, dict]:
    normal_pools = pools.get("normal_pools", {})
    if normal_pools:
        pool_name, pool_data, event_tpl = _choose_from_normal_pools(normal_pools, heaven_persona)
        return pool_name, pool_data.get("label", pool_name), event_tpl
    pool_name, event_tpl = _select_legacy_event(realm_code, current_sin, pools)
    return pool_name, pool_name, event_tpl


def _fallback_local_event() -> LocalEventResult:
    return LocalEventResult(
        event_id="fallback_001",
        log_text="你在虚空中打坐，灵气稀薄，几乎没涨修为。",
        cultivation_delta=1,
    )


def _build_local_event_result(
    event_tpl: dict,
    pool_name: str,
    final_text: str,
    cultivation_delta: int,
    choices: list[LocalEventChoice],
    chosen_choice: LocalEventChoice | None,
) -> LocalEventResult:
    return LocalEventResult(
        event_id=event_tpl.get("id", "unknown"),
        log_text=final_text,
        cultivation_delta=cultivation_delta,
        sin_delta=_extract_delta(event_tpl.get("sin_delta")),
        luck_delta=_extract_delta(event_tpl.get("luck_delta")),
        foundation_delta=_extract_delta(event_tpl.get("foundation_delta")),
        flavor=event_tpl.get("flavor", "normal"),
        event_pool=event_tpl.get("event_pool", pool_name or "common"),
        risk_level=event_tpl.get("risk_level", "low"),
        ambition_tags=event_tpl.get("ambition_tags", []),
        leaderboard_tags=event_tpl.get("leaderboard_tags", []),
        choices=choices,
        chosen_choice=chosen_choice,
        karma_trace_hook=event_tpl.get("karma_trace_hook"),
        ambition_progress_delta=int(event_tpl.get("ambition_progress_delta", 0) or 0),
        leaderboard_score_delta=int(event_tpl.get("leaderboard_score_delta", 0) or 0),
        taunt_count=int(event_tpl.get("taunt_count", 0) or 0),
        gamble_survive_count=int(event_tpl.get("gamble_survive_count", 0) or 0),
        karma_pollution_score=int(event_tpl.get("karma_pollution_score", 0) or 0),
        death_drama_score=int(event_tpl.get("death_drama_score", 0) or 0),
    )


def generate_local_event(
    realm_code: int,
    current_sin: int,
    pools: Optional[dict] = None,
    heaven_persona: str = "",
) -> LocalEventResult:
    """
    根据玩家状态从三层池中抽取并拼装本地事件。

    Args:
        realm_code: 玩家当前境界代号 (1-7)
        current_sin: 玩家当前天谴值
        pools: 可选的外部配置（用于测试注入）
        heaven_persona: 当局天道人格，用于 3K 普通事件池权重修正

    Returns:
        LocalEventResult: 包含文本、数值增量和风味标签的完整事件
    """
    if pools is None:
        pools = _event_loader.pools

    pool_name, pool_label, event_tpl = _select_event_template(
        realm_code,
        current_sin,
        pools,
        heaven_persona,
    )

    if not event_tpl:
        return _fallback_local_event()

    final_text, cultivation_delta = _render_event_template(event_tpl)
    choices = _build_light_choices(event_tpl.get("choices", []))
    chosen_choice = _auto_pick_choice(choices)
    result = _build_local_event_result(
        event_tpl,
        pool_name,
        final_text,
        cultivation_delta,
        choices,
        chosen_choice,
    )

    if chosen_choice:
        _apply_effects_from_dict(chosen_choice.effects, result)
        choice_text = chosen_choice.result_text or chosen_choice.text
        if choice_text:
            result.log_text = f"{result.log_text}【{pool_label}抉择】{choice_text}"

    return result
