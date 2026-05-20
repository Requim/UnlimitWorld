"""
event_config.py 单元测试：本地事件池加载、模板渲染、三层池路由
目标：100% 分支覆盖
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from server.infrastructure.event_config import (
    EventConfigLoader,
    _extract_placeholders,
    _render_template,
    generate_local_event,
    _event_loader,
)
from server.domain.event import LocalEventResult


# ══════════════════════════════════════════════════════════
# 测试用的 Mock 事件池
# ══════════════════════════════════════════════════════════

def _make_mock_pools(**overrides):
    """构建标准的三层测试池"""
    base = {
        "common": {
            "weight": 70,
            "events": [
                {
                    "id": "common_001",
                    "template": "你在{location}打坐，获得了{cultivation_gain}点修为。",
                    "location": ["山洞", "悬崖", "瀑布"],
                    "cultivation_gain": ["10", "20", "30"],
                    "cultivation_delta": [5, 15],
                    "flavor": "normal",
                },
            ],
        },
        "realm_specific": {
            "weight": 20,
            "1": {
                "events": [
                    {
                        "id": "realm_001",
                        "template": "练气期专属：{action}",
                        "action": ["吸收灵石", "吞服丹药"],
                        "cultivation_delta": [20, 50],
                        "flavor": "normal",
                    },
                ],
            },
        },
        "sin_conditional": {
            "weight": 10,
            "triggers": [
                {
                    "min_sin": 30,
                    "events": [
                        {
                            "id": "sin_high_001",
                            "template": "天谴笼罩：{omen}",
                            "omen": ["乌云压顶", "雷声隐隐"],
                            "results": [
                                {"text": "你感到一阵心悸", "weight": 1, "cultivation_delta": [0, 5]},
                                {"text": "你强运玄功抵御", "weight": 1, "cultivation_delta": [5, 10]},
                            ],
                            "flavor": "danger",
                        },
                    ],
                },
            ],
        },
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════════════════
# EventConfigLoader
# ══════════════════════════════════════════════════════════

class TestEventConfigLoader:
    def test_load_from_default_path(self):
        loader = EventConfigLoader()
        config = loader.load()
        assert "pools" in config
        assert loader._loaded is True
        # 二次加载不重复读文件
        config2 = loader.load()
        assert config2 is config  # 缓存命中

    def test_reload_clears_cache(self):
        loader = EventConfigLoader()
        config1 = loader.load()
        config2 = loader.reload()
        assert "pools" in config2
        # reload 后重新读取

    def test_pools_property_lazy_loads(self):
        loader = EventConfigLoader()
        assert not loader._loaded
        pools = loader.pools
        assert loader._loaded
        assert isinstance(pools, dict)

    def test_pools_property_returns_cached_when_loaded(self):
        """pools 属性 _loaded=True 时直接返回缓存，不重新加载"""
        loader = EventConfigLoader()
        loader.load()  # 触发加载
        assert loader._loaded is True
        pools = loader.pools  # 走 if not self._loaded → False 分支
        assert isinstance(pools, dict)

    def test_custom_config_path(self, tmp_path):
        import json
        custom_file = tmp_path / "custom_events.json"
        custom_file.write_text(json.dumps({"pools": {"custom": True}}), encoding="utf-8")
        loader = EventConfigLoader(config_path=custom_file)
        config = loader.load()
        assert config["pools"]["custom"] is True


# ══════════════════════════════════════════════════════════
# _extract_placeholders
# ══════════════════════════════════════════════════════════

def test_extract_single_placeholder():
    result = _extract_placeholders("你在{location}打坐")
    assert result == ["location"]


def test_extract_multiple_placeholders():
    result = _extract_placeholders("{name}在{place}做了{action}")
    assert result == ["name", "place", "action"]


def test_extract_no_placeholders():
    result = _extract_placeholders("纯文本没有占位符")
    assert result == []


def test_extract_duplicate_placeholders():
    result = _extract_placeholders("{x} and {x}")
    assert result == ["x", "x"]


# ══════════════════════════════════════════════════════════
# _render_template
# ══════════════════════════════════════════════════════════

class TestRenderTemplate:
    def test_render_list_value_picks_random(self):
        template = "你选择了{weapon}"
        event_data = {"weapon": ["剑", "刀", "枪"]}
        result = _render_template(template, event_data)
        assert result.startswith("你选择了")
        weapon = result[4:]
        assert weapon in ["剑", "刀", "枪"]

    def test_render_string_value_direct(self):
        template = "你好{name}"
        event_data = {"name": "张三"}
        result = _render_template(template, event_data)
        assert result == "你好张三"

    def test_render_non_string_value(self):
        template = "数字{num}"
        event_data = {"num": 42}
        result = _render_template(template, event_data)
        assert result == "数字42"

    def test_render_missing_placeholder_raises_keyerror(self):
        template = "你好{name}"
        event_data = {}
        with pytest.raises(KeyError):
            _render_template(template, event_data)


# ══════════════════════════════════════════════════════════
# generate_local_event — 池路由分支
# ══════════════════════════════════════════════════════════

class TestGenerateLocalEventPoolRouting:
    def test_common_pool_only(self):
        """仅 common 池有事件时降级到 common"""
        pools = {
            "common": {"weight": 100, "events": [
                {"id": "c1", "template": "common事件", "cultivation_delta": [5, 10]}
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.event_id == "c1"
        assert "common事件" in result.log_text

    def test_realm_specific_pool(self):
        """强制走向 realm_specific 池"""
        pools = {
            "common": {"weight": 0, "events": [{"id": "c1", "template": "c", "cultivation_delta": [1, 1]}]},
            "realm_specific": {"weight": 100, "1": {"events": [
                {"id": "r1", "template": "realm事件", "cultivation_delta": [20, 50]}
            ]}},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.event_id == "r1"

    def test_realm_specific_no_match_falls_to_common(self):
        """realm_specific 中没有当前境界的事件，降级到 common"""
        pools = {
            "common": {"weight": 0, "events": [{"id": "c1", "template": "c降级", "cultivation_delta": [1, 1]}]},
            "realm_specific": {"weight": 100, "5": {"events": [
                {"id": "r5", "template": "仅化神", "cultivation_delta": [20, 50]}
            ]}},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.event_id == "c1"

    def test_sin_conditional_pool(self):
        """强制走向 sin_conditional 池"""
        pools = {
            "common": {"weight": 0, "events": [{"id": "c1", "template": "c", "cultivation_delta": [1, 1]}]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 100, "triggers": [
                {"min_sin": 30, "events": [
                    {"id": "s1", "template": "sin事件", "cultivation_delta": [5, 10]}
                ]},
            ]},
        }
        result = generate_local_event(1, 50, pools=pools)
        assert result.event_id == "s1"

    def test_sin_conditional_below_threshold_falls_to_common(self):
        """天谴值不满足 sin_conditional 触发条件，降级到 common"""
        pools = {
            "common": {"weight": 0, "events": [{"id": "c1", "template": "c降级", "cultivation_delta": [1, 1]}]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 100, "triggers": [
                {"min_sin": 80, "events": [
                    {"id": "s1", "template": "高天谴专属", "cultivation_delta": [5, 10]}
                ]},
            ]},
        }
        result = generate_local_event(1, 10, pools=pools)
        # 不满足 sin_conditional 条件，events为空，降级到 common
        assert result.event_id == "c1"

    def test_sin_conditional_multiple_triggers(self):
        """多个 sin 触发器中匹配满足条件的"""
        pools = {
            "common": {"weight": 0, "events": [{"id": "c1", "template": "c", "cultivation_delta": [1, 1]}]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 100, "triggers": [
                {"min_sin": 10, "events": [
                    {"id": "s_low", "template": "低天谴", "cultivation_delta": [1, 5]}
                ]},
                {"min_sin": 50, "events": [
                    {"id": "s_high", "template": "高天谴", "cultivation_delta": [10, 20]}
                ]},
            ]},
        }
        result = generate_local_event(1, 60, pools=pools)
        # sin=60 两个都满足，事件列表应合并
        assert result.event_id in ("s_low", "s_high")


# ══════════════════════════════════════════════════════════
# generate_local_event — 模板渲染分支
# ══════════════════════════════════════════════════════════

class TestGenerateLocalEventRendering:
    def test_simple_template_with_cultivation_delta(self):
        pools = {
            "common": {"weight": 100, "events": [
                {"id": "e1", "template": "获得{amount}修为", "amount": ["100", "200"], "cultivation_delta": [50, 100]}
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert "修为" in result.log_text
        assert result.cultivation_delta >= 50

    def test_template_with_results_branch(self):
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e2",
                    "template": "遭遇{enemy}，结果：{result_text}",
                    "enemy": ["妖兽", "邪修"],
                    "results": [
                        {"text": "战胜了敌人", "weight": 1, "cultivation_delta": [10, 20]},
                        {"text": "落荒而逃", "weight": 1, "cultivation_delta": [-5, 0]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert "结果" in result.log_text
        assert result.flavor == "normal"

    def test_template_with_nested_outcome_dict_in_results(self):
        """嵌套 {outcome} 对象在 results 分支中处理 text + cultivation_delta"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e3",
                    "template": "探索{location}，结果：{result_text}，收获{outcome}",
                    "location": ["古墓"],
                    "results": [
                        {"text": "发现密道", "weight": 1, "cultivation_delta": [5, 10]},
                    ],
                    "outcome": [
                        {"text": "一本秘籍", "cultivation_delta": [50, 100]},
                        {"text": "一堆废铁", "cultivation_delta": [-10, 0]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.log_text.startswith("探索")
        # cultivation_delta includes results + outcome nested dict
        assert result.cultivation_delta != 0

    def test_template_with_results_and_outcome_combined(self):
        """results 和嵌套 outcome 同时存在，cultivation_delta 累加"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e4",
                    "template": "探索{location}，{result_text}，收获{outcome}",
                    "location": ["古墓", "仙府"],
                    "results": [
                        {"text": "发现密道", "weight": 1, "cultivation_delta": [10, 20]},
                    ],
                    "outcome": [
                        {"text": "一本秘籍", "cultivation_delta": [50, 100]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        # cultivation_delta 应包含 results 和 outcome 的累加
        assert result.cultivation_delta >= 60

    def test_template_format_keyerror_fallback(self):
        """模板有未提供的占位符时，返回原始模板文本"""
        pools = {
            "common": {"weight": 100, "events": [
                {"id": "e5", "template": "缺失{missing_var}的模板", "cultivation_delta": [1, 5]}
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        # KeyError 兜底：直接返回原始模板
        assert result.log_text == "缺失{missing_var}的模板" or "{missing_var}" in result.log_text


# ══════════════════════════════════════════════════════════
# generate_local_event — 终极兜底
# ══════════════════════════════════════════════════════════

class TestGenerateLocalEventRenderingExtra:
    """补充覆盖剩余模板渲染分支"""

    def test_placeholder_is_result_text_is_skipped_in_results_loop(self):
        """step 5: 占位符是 result_text 时 continue"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_skip",
                    "template": "{result_text}之后",
                    "results": [
                        {"text": "成功突破", "weight": 1, "cultivation_delta": [10, 20]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert "成功突破" in result.log_text

    def test_non_dict_value_in_results_branch_else(self):
        """step 5: picked 不是 dict → 直接赋值 render_dict[ph]"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_list",
                    "template": "遇到了{enemy}，{result_text}",
                    "enemy": ["妖兽", "邪修"],  # 简单的字符串列表
                    "results": [
                        {"text": "战胜", "weight": 1, "cultivation_delta": [5, 10]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert "遇到了" in result.log_text
        assert "战胜" in result.log_text

    def test_cultivation_delta_direct_without_results(self):
        """elif 'cultivation_delta' in event_tpl 分支"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_direct",
                    "template": "修为增长了",
                    "cultivation_delta": [30, 50],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.cultivation_delta >= 30

    def test_string_placeholder_in_general_loop(self):
        """step 6: val 是字符串 → 直接赋值"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_str",
                    "template": "{greeting}，道友",
                    "greeting": "你好",
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.log_text == "你好，道友"

    def test_string_val_in_results_branch(self):
        """step 5: results 分支中占位符值为字符串 → elif isinstance(val, str)"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_str_res",
                    "template": "{result_text}，地点：{location}",
                    "location": "幽冥洞府",
                    "results": [
                        {"text": "发现灵脉", "weight": 1, "cultivation_delta": [5, 10]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert "幽冥洞府" in result.log_text

    def test_nested_dict_without_cultivation_delta(self):
        """step 5: 嵌套 dict 无 cultivation_delta → 不进入 if 'cultivation_delta' in picked"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_no_extra",
                    "template": "{result_text}，获得{outcome}",
                    "results": [
                        {"text": "探索遗迹", "weight": 1, "cultivation_delta": [5, 10]},
                    ],
                    "outcome": [
                        {"text": "一块废铁"},
                        {"text": "一枚铜钱"},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.log_text.startswith("探索遗迹")

    def test_general_loop_list_of_dicts(self):
        """step 6: 普通占位符值为 list[dict] → render_dict[ph] = picked.get('text', ...)"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_dicts",
                    "template": "遭遇{npc}",
                    "npc": [
                        {"text": "白发老者"},
                        {"text": "蒙面女子"},
                    ],
                    "cultivation_delta": [1, 5],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.log_text in ("遭遇白发老者", "遭遇蒙面女子")

    def test_general_loop_non_list_non_str(self):
        """step 6: val 非 list 也非 str（如 int）→ elif isinstance(val, str) 为 False → 不加入 render_dict → KeyError 兜底返回原模板"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_int",
                    "template": "修炼第{day}天",
                    "day": 7,
                    "cultivation_delta": [1, 5],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        # int 值不匹配 isinstance(val, str) 也不匹配 isinstance(val, list)，跳过
        # render_dict 中缺少 "day" → KeyError → 返回原始模板
        assert result.log_text == "修炼第{day}天"

    def test_results_branch_placeholder_not_in_event_tpl(self):
        """step 5: 占位符不在 event_tpl 中 → ph in event_tpl 为 False → continue"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_missing",
                    "template": "{result_text} {undefined_key}",
                    "results": [
                        {"text": "测试", "weight": 1, "cultivation_delta": [1, 5]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        # undefined_key 不在 event_tpl 中 → 两次循环都跳过 → KeyError → 返回原模板
        assert result.log_text == "{result_text} {undefined_key}"

    def test_results_branch_non_list_non_str_val(self):
        """step 5: results 分支中 val 非 list 非 str → isinstance(val, str) 为 False → continue"""
        pools = {
            "common": {"weight": 100, "events": [
                {
                    "id": "e_int_res",
                    "template": "{result_text}，第{round}轮",
                    "round": 1,
                    "results": [
                        {"text": "修炼", "weight": 1, "cultivation_delta": [1, 5]},
                    ],
                }
            ]},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        # round 是 int → step5 中 isinstance(val, str) False → step6 中也不是 str/list → KeyError → 返回原模板
        assert result.log_text == "{result_text}，第{round}轮"


class TestGenerateLocalEventFallback:
    def test_all_pools_empty_returns_fallback(self):
        """所有池都为空时，返回终极兜底事件"""
        pools = {
            "common": {"weight": 100, "events": []},
            "realm_specific": {"weight": 0},
            "sin_conditional": {"weight": 0},
        }
        result = generate_local_event(1, 0, pools=pools)
        assert result.event_id == "fallback_001"
        assert "虚空中打坐" in result.log_text
        assert result.cultivation_delta == 1

    def test_no_pools_at_all_returns_fallback(self):
        pools = {}
        result = generate_local_event(1, 0, pools=pools)
        assert result.event_id == "fallback_001"

    def test_uses_default_loader_when_no_pools(self):
        """不传 pools 参数时使用默认的 _event_loader"""
        result = generate_local_event(1, 0)
        assert isinstance(result, LocalEventResult)
        assert result.log_text  # 非空
