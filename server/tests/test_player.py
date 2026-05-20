"""
player.py 单元测试：境界判定、暴毙公式、PlayerState 模型方法
目标：100% 分支覆盖
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import math
import pytest
from unittest.mock import patch

from server.domain.player import (
    get_realm_by_cultivation,
    get_realm_name,
    get_realm_config,
    is_breakthrough,
    compute_death_rate,
    roll_death_check,
    PlayerState,
    PlayerAccount,
    DeadRecord,
)
from server.config import REALM_CONFIG, settings


# ══════════════════════════════════════════════════════════
# get_realm_by_cultivation
# ══════════════════════════════════════════════════════════

class TestGetRealmByCultivation:
    def test_lowest_cultivation_returns_1(self):
        assert get_realm_by_cultivation(0) == 1
        assert get_realm_by_cultivation(50) == 1

    def test_at_exact_base_returns_correct_realm(self):
        """精确命中境界 base —— 注意 realm 7 不在 get_realm_by_cultivation 的遍历范围内（大乘仅通过飞升到达）"""
        assert get_realm_by_cultivation(0) == 1       # 练气 base=0
        assert get_realm_by_cultivation(1000) == 2    # 筑基 base=1000
        assert get_realm_by_cultivation(8000) == 3    # 金丹 base=8000
        assert get_realm_by_cultivation(50000) == 4   # 元婴 base=50000
        assert get_realm_by_cultivation(400000) == 5  # 化神 base=400000
        assert get_realm_by_cultivation(5000000) == 6 # 渡劫 base=5000000

    def test_between_bases_returns_lower_realm(self):
        """在两个 base 之间应返回较低境界"""
        assert get_realm_by_cultivation(500) == 1     # 练气
        assert get_realm_by_cultivation(5000) == 2    # 筑基
        assert get_realm_by_cultivation(30000) == 3   # 金丹
        assert get_realm_by_cultivation(200000) == 4  # 元婴

    def test_very_high_cultivation_returns_6(self):
        """get_realm_by_cultivation 最高返回 6（渡劫期），大乘通过飞升进入"""
        assert get_realm_by_cultivation(100_000_000) == 6


# ══════════════════════════════════════════════════════════
# get_realm_name / get_realm_config
# ══════════════════════════════════════════════════════════

def test_get_realm_name():
    assert get_realm_name(1) == "练气期"
    assert get_realm_name(7) == "大乘期"


def test_get_realm_config():
    cfg = get_realm_config(1)
    assert cfg["name"] == "练气期"
    assert "base_death_rate" in cfg


# ══════════════════════════════════════════════════════════
# is_breakthrough
# ══════════════════════════════════════════════════════════

class TestIsBreakthrough:
    def test_below_cap_no_breakthrough(self):
        assert is_breakthrough(500, 1) is False       # 练气期 cap=1000
        assert is_breakthrough(5000, 2) is False      # 筑基期 cap=8000

    def test_at_cap_triggers_breakthrough(self):
        assert is_breakthrough(1000, 1) is True       # 练气期满
        assert is_breakthrough(8000, 2) is True       # 筑基期满

    def test_above_cap_triggers_breakthrough(self):
        assert is_breakthrough(1500, 1) is True

    def test_realm_6_cap_but_no_breakthrough_to_7(self):
        """渡劫期满修为达到大乘线时，realm_code=6 应判定为突破（进入飞升流程）"""
        assert is_breakthrough(50_000_000, 6) is True

    def test_realm_7_never_breakthrough(self):
        """大乘期不再有突破"""
        assert is_breakthrough(100_000_000, 7) is False
        assert is_breakthrough(50_000_000, 7) is False

    def test_boundary_caps_for_all_realms(self):
        """验证所有境界的 cap 边界"""
        for code in range(1, 7):
            cap = REALM_CONFIG[code]["cultivation_cap"]
            assert is_breakthrough(cap, code) is True
            assert is_breakthrough(cap - 1, code) is False


# ══════════════════════════════════════════════════════════
# compute_death_rate
# ══════════════════════════════════════════════════════════

class TestComputeDeathRate:
    def test_sin_zero_lowest_rate(self):
        """天谴为 0 时暴毙率应等于基础暴毙率"""
        rate = compute_death_rate(1, 0, 50)
        assert rate == pytest.approx(0.05)  # P_base for realm 1

    def test_sin_max_highest_rate(self):
        """天谴满值时暴毙率应接近 1.0"""
        cfg = REALM_CONFIG[1]
        rate = compute_death_rate(1, cfg["sin_max"], 50)
        assert rate > 0.9  # 应该非常高

    def test_sin_ratio_clamped_to_1(self):
        """天谴超过 sin_max 不应导致 ratio > 1"""
        rate = compute_death_rate(1, 999, 50)
        assert 0.0 <= rate <= 1.0

    def test_sin_ratio_clamped_to_0(self):
        """负天谴不应导致异常"""
        rate = compute_death_rate(1, -10, 50)
        assert rate == pytest.approx(0.05)

    def test_higher_foundation_reduces_death_rate(self):
        """高根基降低暴毙率"""
        rate_low = compute_death_rate(1, 40, 10)
        rate_high = compute_death_rate(1, 40, 90)
        assert rate_high < rate_low  # 高根基 → 低暴毙

    def test_higher_realm_higher_base_death(self):
        """高境界基础暴毙率更高"""
        rate_1 = compute_death_rate(1, 0, 50)
        rate_6 = compute_death_rate(6, 0, 50)
        assert rate_6 > rate_1

    def test_s_max_zero_returns_zero(self):
        """s_max <= 0 时直接返回 0"""
        with patch.dict(REALM_CONFIG[1], {"sin_max": 0}):
            rate = compute_death_rate(1, 50, 50)
            assert rate == 0.0

    def test_custom_alpha(self):
        """自定义 alpha 参数"""
        rate_default = compute_death_rate(1, 30, 50, alpha=3.0)
        rate_high = compute_death_rate(1, 30, 50, alpha=10.0)
        # alpha 更高 → sin_ratio 的幂更大 → P_final 更接近 P_base（因为 sin_ratio < 1）
        # 实际上 exponent = alpha * beta，alpha 越大，sin_ratio^exponent 越小
        # 所以 P_final = P_base + (1-P_base)*small_number，alpha 越大，P_final 越接近 P_base
        assert rate_high <= rate_default


# ══════════════════════════════════════════════════════════
# roll_death_check
# ══════════════════════════════════════════════════════════

class TestRollDeathCheck:
    def test_returns_bool(self):
        result = roll_death_check(1, 0, 50)
        assert isinstance(result, bool)

    def test_low_sin_survives_most_of_time(self):
        """低天谴应当在大多数情况下存活"""
        results = [roll_death_check(1, 0, 90) for _ in range(100)]
        deaths = sum(results)
        # P_base=0.05, sin=0, foundation=90 → 极低暴毙率
        assert deaths < 20  # 几乎不可能超过20次

    def test_max_sin_almost_always_dies(self):
        """满天谴应当几乎总是死亡"""
        cfg = REALM_CONFIG[6]
        results = [roll_death_check(6, cfg["sin_max"], 10) for _ in range(100)]
        deaths = sum(results)
        assert deaths > 70  # 渡劫期满天谴 + 低根基 → 极高暴毙

    def test_deterministic_with_seed(self):
        """固定随机种子验证"""
        import random
        random.seed(42)
        # 设定特定条件，确认可复现
        # sin=0 → P_final ≈ P_base = 0.05，seed(42) 下 random()=0.639... → 存活
        assert roll_death_check(1, 0, 50) is False


# ══════════════════════════════════════════════════════════
# PlayerState 模型方法
# ══════════════════════════════════════════════════════════

class TestPlayerState:
    def _make_player(self, **kwargs):
        defaults = {
            "player_id": "p_test",
            "player_name": "测试修士",
            "realm_code": 1,
            "cultivation": 500,
            "luck": 50,
            "foundation": 50,
            "sin_value": 10,
        }
        defaults.update(kwargs)
        return PlayerState(**defaults)

    # ── apply_talent_bonus ──

    def test_apply_talent_bonus_empty(self):
        p = self._make_player(talent_bonus={})
        orig_luck = p.luck
        orig_foundation = p.foundation
        p.apply_talent_bonus()
        assert p.luck == orig_luck
        assert p.foundation == orig_foundation

    def test_apply_talent_bonus_luck_only(self):
        p = self._make_player(talent_bonus={"luck": 20})
        p.apply_talent_bonus()
        assert p.luck == 70  # 50 + 20
        assert p.foundation == 50  # 不变

    def test_apply_talent_bonus_foundation_only(self):
        p = self._make_player(talent_bonus={"foundation": 30})
        p.apply_talent_bonus()
        assert p.foundation == 80  # 50 + 30
        assert p.luck == 50  # 不变

    def test_apply_talent_bonus_both(self):
        p = self._make_player(talent_bonus={"luck": 10, "foundation": 10})
        p.apply_talent_bonus()
        assert p.luck == 60
        assert p.foundation == 60

    def test_apply_talent_bonus_clamped_at_100(self):
        p = self._make_player(luck=95, talent_bonus={"luck": 20})
        p.apply_talent_bonus()
        assert p.luck == 100  # min(100, 115)
        p2 = self._make_player(foundation=95, talent_bonus={"foundation": 20})
        p2.apply_talent_bonus()
        assert p2.foundation == 100

    # ── apply_deafness_protocol ──

    def test_deafness_protocol_with_charges(self):
        p = self._make_player(deafness_protocol=3)
        bonus = p.apply_deafness_protocol()
        assert bonus == 10
        assert p.deafness_protocol == 2

    def test_deafness_protocol_zero_charges(self):
        p = self._make_player(deafness_protocol=0)
        bonus = p.apply_deafness_protocol()
        assert bonus == 0
        assert p.deafness_protocol == 0

    # ── effective_luck ──

    def test_effective_luck_with_protocol(self):
        p = self._make_player(luck=50, deafness_protocol=1)
        assert p.effective_luck() == 60  # 50 + 10

    def test_effective_luck_without_protocol(self):
        p = self._make_player(luck=50, deafness_protocol=0)
        assert p.effective_luck() == 50

    def test_effective_luck_clamped_at_100(self):
        p = self._make_player(luck=95, deafness_protocol=1)
        assert p.effective_luck() == 100

    # ── sin_phase ──

    def test_sin_phase_safe(self):
        p = self._make_player(sin_value=5)  # sin_max=50, ratio=0.1
        assert p.sin_phase() == "safe"

    def test_sin_phase_warning(self):
        p = self._make_player(sin_value=35)  # sin_max=50, ratio=0.7
        assert p.sin_phase() == "warning"

    def test_sin_phase_danger(self):
        p = self._make_player(sin_value=45)  # sin_max=50, ratio=0.9
        assert p.sin_phase() == "danger"

    def test_sin_phase_boundary_safe_warning(self):
        """ratio=0.5 → not < 0.5 → enters elif → 'warning'"""
        p = self._make_player(sin_value=25)  # sin_max=50, ratio=0.5
        assert p.sin_phase() == "warning"

    def test_sin_phase_boundary_warning_danger(self):
        """ratio=0.8 → not < 0.5, not < 0.8 → 'danger'"""
        p = self._make_player(sin_value=40)  # sin_max=50, ratio=0.8
        assert p.sin_phase() == "danger"

    def test_sin_phase_sin_zero(self):
        p = self._make_player(sin_value=0)
        assert p.sin_phase() == "safe"

    # ── to_dict / from_dict ──

    def test_to_dict_roundtrip(self):
        p = self._make_player()
        d = p.to_dict()
        p2 = PlayerState.from_dict(d)
        assert p2.player_id == p.player_id
        assert p2.player_name == p.player_name
        assert p2.cultivation == p.cultivation

    def test_from_dict_creates_valid_instance(self):
        d = {"player_id": "abc", "player_name": "test", "realm_code": 1}
        p = PlayerState.from_dict(d)
        assert isinstance(p, PlayerState)
        assert p.player_id == "abc"


class TestGetRealmByCultivationFallback:
    def test_fallback_return_1_when_no_realm_matches(self):
        """get_realm_by_cultivation 最终兜底 return 1"""
        # 修改 REALM_CONFIG 使所有境界的 base 都很大，loop 找不到匹配
        with patch("server.domain.player.REALM_CONFIG", {1: {"cultivation_base": 999}, 2: {"cultivation_base": 999}, 3: {"cultivation_base": 999}, 4: {"cultivation_base": 999}, 5: {"cultivation_base": 999}, 6: {"cultivation_base": 999}}):
            result = get_realm_by_cultivation(100)
            assert result == 1


# ══════════════════════════════════════════════════════════
# PlayerAccount / DeadRecord
# ══════════════════════════════════════════════════════════

def test_player_account_defaults():
    a = PlayerAccount(player_id="p1")
    assert a.heaven_points == 0
    assert a.wechat_openid == ""


def test_dead_record_creation():
    from datetime import datetime
    d = DeadRecord(
        player_id="p1",
        player_name="test",
        realm="练气期",
        realm_code=1,
        dead_title="test death",
    )
    assert d.player_name == "test"
    assert d.survived_seconds == 0
    assert isinstance(d.created_at, datetime)
