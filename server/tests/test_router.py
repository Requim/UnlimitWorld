"""
优先级链路由 单元测试

验证 determine_next_event() 的优先级正确性：
飞升 > 天谴满100 > PRD触发 > 大境界突破 > 本地日常
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from server.application.game_engine import determine_next_event, EventType


class TestEventPriorityChain:
    """验证优先级链的正确顺序"""

    def test_sin_full_has_highest_priority(self):
        """天谴满值时，无条件触发神罚"""
        event = determine_next_event(
            realm_code=1,
            cultivation=500,      # 未到突破门槛
            sin_value=50,         # = sin_max，满值
            prd_counter=85,       # PRD 满
        )
        assert event == EventType.FORCE_HEAVEN_KILL, (
            f"天谴满值应为最高优先级 FORCE_HEAVEN_KILL，实际返回 {event}"
        )

    def test_prd_intercepts_breakthrough(self):
        """PRD 触发优先于境界突破 —— 命运拦截器"""
        event = determine_next_event(
            realm_code=1,
            cultivation=1_000,    # 达到突破门槛！
            sin_value=20,         # 天谴未满
            prd_counter=85,       # PRD 满 (>=60 for 练气)
        )
        assert event == EventType.PRD_LLM_EVENT, (
            f"PRD 应拦截突破事件 PRD_LLM_EVENT，实际返回 {event}"
        )

    def test_breakthrough_after_prd_reset(self):
        """PRD 归零后，突破事件顺位触发"""
        event = determine_next_event(
            realm_code=1,
            cultivation=1_000,    # 达到突破门槛
            sin_value=20,         # 天谴未满
            prd_counter=0,        # PRD 已归零
        )
        assert event == EventType.BREAKTHROUGH_EVENT, (
            f"PRD 归零后应为突破事件 BREAKTHROUGH_EVENT，实际返回 {event}"
        )

    def test_sin_full_overrides_everything(self):
        """天谴满值覆盖所有其他条件"""
        event = determine_next_event(
            realm_code=2,
            cultivation=8_000,    # 突破门槛
            sin_value=60,         # = sin_max 满值
            prd_counter=90,       # PRD 满
        )
        assert event == EventType.FORCE_HEAVEN_KILL, (
            f"天谴满值应覆盖一切，实际返回 {event}"
        )

    def test_local_when_nothing_triggered(self):
        """所有条件都不满足时返回本地事件"""
        event = determine_next_event(
            realm_code=1,
            cultivation=500,      # 未到突破门槛
            sin_value=10,         # 天谴低
            prd_counter=20,       # PRD 未满 (<60)
        )
        assert event == EventType.LOCAL_EVENT, (
            f"无触发条件时应返回 LOCAL_EVENT，实际返回 {event}"
        )

    def test_ascension_highest_priority(self):
        """渡劫期满修为时飞升为最高优先级"""
        event = determine_next_event(
            realm_code=6,
            cultivation=50_000_000,  # 飞升门槛
            sin_value=100,           # 天谴满值
            prd_counter=200,         # PRD 满
        )
        assert event == EventType.ASCENSION_EVENT, (
            f"飞升应为最高优先级 ASCENSION_EVENT，实际返回 {event}"
        )

    def test_dynamic_prd_threshold_by_realm(self):
        """验证动态 PRD 阈值：练气期 60，渡劫期 120"""
        # 练气期：prd_counter=50 < 60，不触发
        event_low = determine_next_event(1, 500, 10, 50)
        assert event_low == EventType.LOCAL_EVENT

        # 练气期：prd_counter=60 >= 60，触发
        event_trigger = determine_next_event(1, 500, 10, 60)
        assert event_trigger == EventType.PRD_LLM_EVENT

        # 渡劫期：prd_counter=100 >= 80 但不是 >= 120，不触发
        event_high = determine_next_event(6, 10_000_000, 50, 100)
        assert event_high == EventType.LOCAL_EVENT

        # 渡劫期：prd_counter=120 >= 120，触发
        event_high_trigger = determine_next_event(6, 10_000_000, 50, 120)
        assert event_high_trigger == EventType.PRD_LLM_EVENT
