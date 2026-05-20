"""
heaven_persona.py 单元测试：人格 Prompt 工厂
目标：100% 分支覆盖
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest
from server.application.heaven_persona import (
    PERSONA_NAMES,
    PERSONA_REGISTRY,
    get_persona_prompt,
    build_system_prompt,
    TAISHANG_PROMPT,
    CHAOS_PROMPT,
    SPOIL_PROMPT,
    OVERLORD_PROMPT,
    OUTPUT_SCHEMA_INSTRUCTION,
)


class TestPersonaRegistry:
    def test_all_four_personas_registered(self):
        assert len(PERSONA_REGISTRY) == 4
        assert "太上忘情" in PERSONA_REGISTRY
        assert "混沌乐子人" in PERSONA_REGISTRY
        assert "唯爱护短" in PERSONA_REGISTRY
        assert "天道夺舍·恶意化身" in PERSONA_REGISTRY

    def test_persona_names_matches_registry(self):
        assert PERSONA_NAMES == list(PERSONA_REGISTRY.keys())

    def test_all_prompts_contain_output_schema(self):
        for name, prompt in PERSONA_REGISTRY.items():
            assert OUTPUT_SCHEMA_INSTRUCTION in prompt, f"{name} missing schema"

    def test_taishang_has_core_rules(self):
        assert "太上忘情" in TAISHANG_PROMPT
        assert "核心律令" in TAISHANG_PROMPT

    def test_chaos_has_core_rules(self):
        assert "混沌乐子人" in CHAOS_PROMPT
        assert "核心律令" in CHAOS_PROMPT

    def test_spoil_has_core_rules(self):
        assert "唯爱护短" in SPOIL_PROMPT
        assert "核心律令" in SPOIL_PROMPT

    def test_overlord_has_core_rules(self):
        assert "天道夺舍·恶意化身" in OVERLORD_PROMPT
        assert "核心律令" in OVERLORD_PROMPT


class TestGetPersonaPrompt:
    def test_known_persona_returns_correct_prompt(self):
        assert get_persona_prompt("太上忘情") == TAISHANG_PROMPT
        assert get_persona_prompt("混沌乐子人") == CHAOS_PROMPT
        assert get_persona_prompt("唯爱护短") == SPOIL_PROMPT
        assert get_persona_prompt("天道夺舍·恶意化身") == OVERLORD_PROMPT

    def test_unknown_persona_falls_back_to_chaos(self):
        """未知人格降级为混沌乐子人"""
        result = get_persona_prompt("不存在的天道人格")
        assert result == CHAOS_PROMPT

    def test_empty_string_falls_back_to_chaos(self):
        result = get_persona_prompt("")
        assert result == CHAOS_PROMPT


class TestBuildSystemPrompt:
    def test_without_global_rule_returns_base_prompt(self):
        result = build_system_prompt("混沌乐子人")
        assert result == CHAOS_PROMPT

    def test_with_global_rule_appends_rule(self):
        rule = "附加规则：不准使用网络梗"
        result = build_system_prompt("太上忘情", global_rule=rule)
        assert result.startswith(TAISHANG_PROMPT)
        assert "[追加全局规则]" in result
        assert rule in result

    def test_empty_global_rule_no_append(self):
        result = build_system_prompt("唯爱护短", global_rule="")
        assert result == SPOIL_PROMPT

    def test_unknown_persona_with_rule(self):
        """未知人格降级 + 全局规则追加"""
        rule = "测试规则"
        result = build_system_prompt("未知人格", global_rule=rule)
        assert result.startswith(CHAOS_PROMPT)
        assert rule in result
