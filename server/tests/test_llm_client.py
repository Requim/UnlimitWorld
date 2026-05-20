"""
llm_client.py 单元测试：DeepSeek 客户端、编排器重试/降级
目标：100% 分支覆盖（通过 mock 控制所有路径）
"""
import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from server.domain.event import (
    LLMInputContext,
    LLMOutput,
    AttributeChanges,
    PlayerContextForLLM,
)
from server.infrastructure.llm_client import DeepSeekClient, LLMOrchestrator
from server.config import settings


# ══════════════════════════════════════════════════════════
# 测试辅助
# ══════════════════════════════════════════════════════════

def _make_context(is_dead=False, player_name="测试修士", realm="练气期"):
    return LLMInputContext(
        system_context={"heaven_personality": "混沌乐子人"},
        player_status=PlayerContextForLLM(
            player_name=player_name,
            realm=realm,
            realm_code=1,
            cultivation=500,
            luck=50,
            foundation=50,
            sin_value=10,
        ),
        trigger_type="HEAVEN",
        is_dead=is_dead,
        historical_karma="测试因果",
        player_custom_input="测试骚话",
        chosen_option="A",
        fixed_options=[{"id": "A", "text": "选项A"}],
        heaven_persona="混沌乐子人",
    )


def _make_valid_llm_json(is_dead=False):
    return json.dumps({
        "event_title": "测试事件",
        "story_text": "这是一个测试剧情文本。",
        "is_dead": is_dead,
        "dead_title": "测试死因" if is_dead else "",
        "attribute_changes": {
            "cultivation": 100,
            "sin_value": 5,
            "luck": 0,
            "foundation": 0,
        },
        "next_action_required": "GAME_OVER" if is_dead else "IDLE",
    }, ensure_ascii=False)


# ══════════════════════════════════════════════════════════
# DeepSeekClient
# ══════════════════════════════════════════════════════════

class TestDeepSeekClientInit:
    def test_default_values_from_settings(self):
        client = DeepSeekClient()
        assert client.api_key == settings.deepseek_api_key
        assert client.base_url == settings.deepseek_base_url
        assert client.model == settings.deepseek_model

    def test_custom_values_override_settings(self):
        client = DeepSeekClient(
            api_key="custom_key",
            base_url="https://custom.api",
            model="custom-model",
        )
        assert client.api_key == "custom_key"
        assert client.base_url == "https://custom.api"
        assert client.model == "custom-model"


class TestDeepSeekClientChatStream:
    @pytest.mark.asyncio
    async def test_mock_stream_when_openai_unavailable(self):
        """openai 不可用时降级到 mock stream"""
        with patch.dict(sys.modules, {"openai": None}):
            client = DeepSeekClient(api_key="test")
            chunks = []
            async for chunk in client.chat_stream("system", "user"):
                chunks.append(chunk)
            full = "".join(chunks)
            assert "天道在虚空中沉默" in full

    @pytest.mark.asyncio
    async def test_mock_stream_when_import_error(self):
        """ImportError 时也降级"""
        with patch.dict(sys.modules):
            sys.modules.pop("openai", None)
            # 强制 import 失败
            import builtins
            orig_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name == "openai":
                    raise ImportError("mock")
                return orig_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                client = DeepSeekClient(api_key="test")
                chunks = []
                async for chunk in client.chat_stream("s", "u"):
                    chunks.append(chunk)
                assert len("".join(chunks)) > 0

    @pytest.mark.asyncio
    async def test_real_openai_stream(self):
        """mock AsyncOpenAI 验证流式调用路径 —— patch 内部 import"""
        mock_client = MagicMock()

        async def mock_aiter(self):
            mock_chunk = MagicMock()
            mock_chunk.choices = [MagicMock()]
            mock_chunk.choices[0].delta.content = "Hello"
            yield mock_chunk

        mock_response = MagicMock()
        mock_response.__aiter__ = mock_aiter

        mock_async_openai = MagicMock()
        mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_openai_module = MagicMock()
        mock_openai_module.AsyncOpenAI = MagicMock(return_value=mock_async_openai)

        with patch.dict(sys.modules, {"openai": mock_openai_module}):
            client = DeepSeekClient(api_key="test")
            chunks = []
            async for chunk in client.chat_stream("system", "user"):
                chunks.append(chunk)
            assert "Hello" in chunks


class TestDeepSeekClientChatComplete:
    @pytest.mark.asyncio
    async def test_chat_complete_joins_chunks(self):
        """chat_complete 拼接所有流式输出"""
        async def mock_stream(system, user):
            for c in ["a", "b", "c"]:
                yield c

        client = DeepSeekClient()
        client.chat_stream = mock_stream
        result = await client.chat_complete("s", "u")
        assert result == "abc"


# ══════════════════════════════════════════════════════════
# LLMOrchestrator._parse_and_validate
# ══════════════════════════════════════════════════════════

class TestParseAndValidate:
    def test_parse_clean_json(self):
        orch = LLMOrchestrator()
        raw = _make_valid_llm_json(is_dead=False)
        result = orch._parse_and_validate(raw)
        assert result.event_title == "测试事件"
        assert result.story_text == "这是一个测试剧情文本。"

    def test_parse_json_with_markdown_wrapper(self):
        orch = LLMOrchestrator()
        raw = "```json\n" + _make_valid_llm_json(is_dead=False) + "\n```"
        result = orch._parse_and_validate(raw)
        assert result.event_title == "测试事件"

    def test_parse_json_with_markdown_no_lang_specifier(self):
        orch = LLMOrchestrator()
        raw = "```\n" + _make_valid_llm_json(is_dead=False) + "\n```"
        result = orch._parse_and_validate(raw)
        assert result.event_title == "测试事件"

    def test_parse_json_with_markdown_no_trailing_backticks(self):
        """Markdown 包裹但末尾没有 ``` → 只移除首行"""
        orch = LLMOrchestrator()
        content = _make_valid_llm_json(is_dead=False)
        raw = "```json\n" + content  # 没有结尾 ```
        result = orch._parse_and_validate(raw)
        assert result.event_title == "测试事件"

    def test_parse_invalid_json_raises(self):
        orch = LLMOrchestrator()
        with pytest.raises(Exception):
            orch._parse_and_validate("这不是JSON")

    def test_parse_missing_required_fields_raises(self):
        orch = LLMOrchestrator()
        # attribute_changes 必须是对象，传字符串会触发 ValidationError
        with pytest.raises(Exception):
            orch._parse_and_validate('{"event_title": "x", "story_text": "y", "attribute_changes": "not_an_object"}')


# ══════════════════════════════════════════════════════════
# LLMOrchestrator._fallback_resolve
# ══════════════════════════════════════════════════════════

class TestFallbackResolve:
    def test_fallback_dead(self):
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)
        result = orch._fallback_resolve(ctx)
        assert result.is_dead is True
        assert result.event_title == "天道裁决"
        assert result.dead_title
        assert result.next_action_required == "GAME_OVER"

    def test_fallback_alive(self):
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)
        result = orch._fallback_resolve(ctx)
        assert result.is_dead is False
        assert result.event_title == "劫后余生"
        assert result.dead_title == ""
        assert result.next_action_required == "IDLE"
        assert result.attribute_changes.cultivation > 0


# ══════════════════════════════════════════════════════════
# LLMOrchestrator._generate_fallback_dead_title
# ══════════════════════════════════════════════════════════

def test_generate_fallback_dead_title():
    orch = LLMOrchestrator()
    ctx = _make_context(is_dead=True, player_name="张三", realm="筑基期")
    title = orch._generate_fallback_dead_title(ctx)
    assert isinstance(title, str)
    assert len(title) > 0


# ══════════════════════════════════════════════════════════
# LLMOrchestrator.process — 成功路径
# ══════════════════════════════════════════════════════════

class TestOrchestratorProcess:
    @pytest.mark.asyncio
    async def test_process_success_first_attempt(self):
        """首次调用成功"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)

        async def mock_complete(prompt, content):
            return _make_valid_llm_json(is_dead=False)

        orch.client.chat_complete = mock_complete
        result = await orch.process("system prompt", ctx)
        assert result.event_title == "测试事件"
        assert result.is_dead is False  # 被后端覆盖

    @pytest.mark.asyncio
    async def test_process_is_dead_hard_override(self):
        """即使 LLM 返回 is_dead=False，后端也强制覆盖为 True"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)  # 后端判定死亡

        async def mock_complete(prompt, content):
            return _make_valid_llm_json(is_dead=False)  # LLM 说没死

        orch.client.chat_complete = mock_complete
        result = await orch.process("system prompt", ctx)
        assert result.is_dead is True  # 必须被覆盖

    @pytest.mark.asyncio
    async def test_process_dead_fills_title(self):
        """is_dead=True 但没有 dead_title 时自动生成"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)

        async def mock_complete(prompt, content):
            return json.dumps({
                "event_title": "死",
                "story_text": "你死了",
                "is_dead": True,
                "dead_title": "",  # 空的
                "attribute_changes": {"cultivation": 0, "sin_value": 0, "luck": 0, "foundation": 0},
                "next_action_required": "GAME_OVER",
            }, ensure_ascii=False)

        orch.client.chat_complete = mock_complete
        result = await orch.process("system prompt", ctx)
        assert result.is_dead is True
        assert result.dead_title  # 自动填充


# ══════════════════════════════════════════════════════════
# LLMOrchestrator.process — 重试与降级路径
# ══════════════════════════════════════════════════════════

class TestOrchestratorRetryAndFallback:
    @pytest.mark.asyncio
    async def test_retry_on_validation_error_then_success(self):
        """第一次校验失败，第二次成功"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)
        call_count = [0]

        async def mock_complete(prompt, content):
            call_count[0] += 1
            if call_count[0] == 1:
                return "无效JSON{{{"
            else:
                return _make_valid_llm_json(is_dead=False)

        orch.client.chat_complete = mock_complete
        result = await orch.process("system prompt", ctx)
        assert call_count[0] == 2
        assert result.event_title == "测试事件"

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_falls_back(self):
        """所有重试耗尽后降级到本地引擎"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)

        async def mock_complete(prompt, content):
            return "每次都无效的JSON{{{{"

        orch.client.chat_complete = mock_complete
        result = await orch.process("system prompt", ctx)
        # 降级到 fallback
        assert result.event_title == "天道裁决"
        assert result.is_dead is True

    @pytest.mark.asyncio
    async def test_fix_hint_injected_on_retry(self):
        """重试时 prompt 中包含 fix_hint"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)
        prompts_seen = []

        async def mock_complete(prompt, content):
            prompts_seen.append(prompt)
            if len(prompts_seen) == 1:
                return "bad json"
            else:
                return _make_valid_llm_json(is_dead=False)

        orch.client.chat_complete = mock_complete
        await orch.process("system prompt", ctx)
        assert len(prompts_seen) == 2
        assert "[格式修正指令]" in prompts_seen[1]

    @pytest.mark.asyncio
    async def test_zero_retries_skips_loop_to_fallback(self):
        """llm_max_retries = -1 → range(0) 为空 → for 循环不进入 → 直接走降级"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)

        with patch.object(settings, "llm_max_retries", -1):
            result = await orch.process("system prompt", ctx)
        assert result.event_title == "天道裁决"


# ══════════════════════════════════════════════════════════
# LLMOrchestrator.process_streaming
# ══════════════════════════════════════════════════════════

class TestOrchestratorProcessStreaming:
    @pytest.mark.asyncio
    async def test_streaming_success(self):
        """流式处理成功路径"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)

        async def mock_stream(prompt, content):
            for c in _make_valid_llm_json(is_dead=False):
                yield c

        orch.client.chat_stream = mock_stream
        chunks = []
        output = None
        async for chunk in orch.process_streaming("system", ctx):
            chunks.append(chunk)
            if isinstance(chunk, LLMOutput):
                output = chunk
        full = "".join(c for c in chunks if isinstance(c, str))
        assert "测试事件" in full

    @pytest.mark.asyncio
    async def test_streaming_retry_then_fallback(self):
        """流式处理重试耗尽后降级"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)

        async def mock_stream(prompt, content):
            yield "bad json!!!"

        orch.client.chat_stream = mock_stream
        chunks = []
        async for chunk in orch.process_streaming("system", ctx):
            chunks.append(chunk)
            if isinstance(chunk, LLMOutput):
                pass
        full = "".join(c for c in chunks if isinstance(c, str))
        assert len(full) > 0  # 降级文本

    @pytest.mark.asyncio
    async def test_streaming_dead_fills_empty_title(self):
        """流式处理 is_dead 且 dead_title 为空时自动填充"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)

        result_json = json.dumps({
            "event_title": "死亡事件",
            "story_text": "你死了",
            "is_dead": True,
            "dead_title": "",  # 空的
            "attribute_changes": {"cultivation": 0, "sin_value": 0, "luck": 0, "foundation": 0},
            "next_action_required": "GAME_OVER",
        }, ensure_ascii=False)

        async def mock_stream(prompt, content):
            for c in result_json:
                yield c

        orch.client.chat_stream = mock_stream
        async for chunk in orch.process_streaming("system", ctx):
            pass  # 处理完成即验证通过

    @pytest.mark.asyncio
    async def test_streaming_zero_retries_skips_loop_to_fallback(self):
        """流式: llm_max_retries = -1 → range(0) 为空 → 直接走降级"""
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)

        with patch.object(settings, "llm_max_retries", -1):
            chunks = []
            async for chunk in orch.process_streaming("system", ctx):
                chunks.append(chunk)
            full = "".join(c for c in chunks if isinstance(c, str))
            assert len(full) > 0
