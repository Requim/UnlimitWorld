"""
llm_client.py unit tests.
Focus:
- OpenAI-compatible client request shape
- JSON parsing / normalization
- streaming extractor compatibility for reason_text and legacy story_text
- streaming orchestration success / rescue / fallback paths
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from server.config import settings
from server.domain.event import (
    AttributeChanges,
    LLMInputContext,
    LLMOutput,
    PlayerContextForLLM,
)
from server.infrastructure.llm_client import DeepSeekClient, LLMOrchestrator, StreamFieldExtractor


def _make_context(is_dead: bool = False) -> LLMInputContext:
    return LLMInputContext(
        system_context={"heaven_personality": "Chaos"},
        player_status=PlayerContextForLLM(
            player_name="test_player",
            realm="Qi Refining",
            realm_code=1,
            cultivation=500,
            luck=50,
            foundation=50,
            sin_value=10,
            effective_luck=50,
        ),
        trigger_type="HEAVEN",
        is_dead=is_dead,
        historical_karma="test karma",
        player_custom_input="test taunt",
        chosen_option="A",
        fixed_options=[{"id": "A", "text": "Option A"}],
        heaven_persona="Chaos",
    )


def _make_valid_llm_json(
    *,
    is_dead: bool = False,
    reason_text: str = "test reason text",
    verdict_text: str = "final verdict",
    event_title: str = "test event",
) -> str:
    return json.dumps(
        {
            "reason_text": reason_text,
            "verdict_text": verdict_text,
            "event_title": event_title,
            "story_text": "legacy story text",
            "is_dead": is_dead,
            "dead_title": "test death" if is_dead else "",
            "attribute_changes": {
                "cultivation": 100,
                "sin_value": 5,
                "luck": 0,
                "foundation": 0,
            },
            "next_action_required": "GAME_OVER" if is_dead else "IDLE",
        },
        ensure_ascii=False,
    )


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
        with patch.dict(sys.modules, {"openai": None}):
            client = DeepSeekClient(api_key="test")
            chunks = []
            async for chunk in client.chat_stream("system", "user"):
                chunks.append(chunk)
            assert len("".join(chunks)) > 0

    @pytest.mark.asyncio
    async def test_real_openai_stream(self):
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hello"

        class MockResponse:
            def __aiter__(self):
                async def gen():
                    yield mock_chunk
                return gen()

        mock_response = MockResponse()

        mock_async_openai = MagicMock()
        mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_openai_module = MagicMock()
        mock_openai_module.AsyncOpenAI = MagicMock(return_value=mock_async_openai)

        with patch.dict(sys.modules, {"openai": mock_openai_module}):
            client = DeepSeekClient(api_key="test")
            chunks = []
            async for chunk in client.chat_stream("system", "user"):
                chunks.append(chunk)
            assert chunks == ["Hello"]
            kwargs = mock_async_openai.chat.completions.create.await_args.kwargs
            assert kwargs["temperature"] == settings.deepseek_temperature
            assert kwargs["response_format"] == {"type": "json_object"}
            assert kwargs["stream"] is True


class TestDeepSeekClientChatComplete:
    @pytest.mark.asyncio
    async def test_chat_complete_reads_non_stream_content(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "abc"

        mock_async_openai = MagicMock()
        mock_async_openai.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_openai_module = MagicMock()
        mock_openai_module.AsyncOpenAI = MagicMock(return_value=mock_async_openai)

        with patch.dict(sys.modules, {"openai": mock_openai_module}):
            client = DeepSeekClient(api_key="test")
            result = await client.chat_complete("system", "user")
            assert result == "abc"
            kwargs = mock_async_openai.chat.completions.create.await_args.kwargs
            assert kwargs["stream"] is False
            assert kwargs["response_format"] == {"type": "json_object"}


class TestParseAndValidate:
    def test_parse_clean_json(self):
        orch = LLMOrchestrator()
        result = orch._parse_and_validate(_make_valid_llm_json())
        assert result.reason_text == "test reason text"
        assert result.verdict_text == "final verdict"
        assert result.story_text == "test reason text\n\nfinal verdict"
        assert result.event_title == "test event"

    def test_parse_json_with_markdown_wrapper(self):
        orch = LLMOrchestrator()
        raw = "```json\n" + _make_valid_llm_json() + "\n```"
        result = orch._parse_and_validate(raw)
        assert result.event_title == "test event"

    def test_parse_json_with_leading_noise_extracts_object(self):
        orch = LLMOrchestrator()
        raw = "Here you go:\n" + _make_valid_llm_json() + "\nDone."
        result = orch._parse_and_validate(raw)
        assert result.event_title == "test event"

    def test_parse_missing_required_fields_raises(self):
        orch = LLMOrchestrator()
        with pytest.raises(Exception):
            orch._parse_and_validate('{"event_title":"x","story_text":"y","attribute_changes":"bad"}')

    def test_parse_legacy_story_only_keeps_legacy_text(self):
        orch = LLMOrchestrator()
        raw = json.dumps(
            {
                "event_title": "legacy",
                "story_text": "legacy only story",
                "is_dead": False,
                "dead_title": "",
                "attribute_changes": {"cultivation": 1, "sin_value": 0, "luck": 0, "foundation": 0},
                "next_action_required": "IDLE",
            },
            ensure_ascii=False,
        )
        result = orch._parse_and_validate(raw)
        assert result.reason_text == "legacy only story"
        assert result.verdict_text == ""
        assert result.story_text == "legacy only story"


class TestStreamFieldExtractor:
    def test_extracts_reason_text(self):
        extractor = StreamFieldExtractor(["event_title", "reason_text", "verdict_text", "story_text"])
        chunks = [
            '{"event_title":"test","reason_text":"heaven',
            ' says why\\n',
            'the verdict is coming.","is_dead":false}',
        ]
        out = "".join(
            piece
            for chunk in chunks
            for segment, piece in extractor.feed(chunk)
            if segment == "reason_text"
        )
        assert out == "heaven says why\nthe verdict is coming."

    def test_extracts_legacy_story_text_too(self):
        extractor = StreamFieldExtractor(["event_title", "reason_text", "verdict_text", "story_text"])
        chunks = [
            '{"event_title":"test","story_text":"legacy',
            ' stream text',
            '","is_dead":false}',
        ]
        out = "".join(
            piece
            for chunk in chunks
            for segment, piece in extractor.feed(chunk)
            if segment == "story_text"
        )
        assert out == "legacy stream text"


class TestFallbackResolve:
    def test_fallback_dead(self):
        orch = LLMOrchestrator()
        result = orch._fallback_resolve(_make_context(is_dead=True))
        assert result.is_dead is True
        assert result.dead_title
        assert result.verdict_text == result.dead_title
        assert result.next_action_required == "GAME_OVER"

    def test_fallback_alive(self):
        orch = LLMOrchestrator()
        result = orch._fallback_resolve(_make_context(is_dead=False))
        assert result.is_dead is False
        assert result.verdict_text
        assert result.next_action_required == "IDLE"
        assert result.attribute_changes.cultivation > 0


class TestOrchestratorProcessStreaming:
    @pytest.mark.asyncio
    async def test_streaming_success(self):
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)

        async def mock_stream(prompt, content):
            for ch in _make_valid_llm_json():
                yield ch

        orch.client.chat_stream = mock_stream

        chunks = []
        output = None
        async for item in orch.process_streaming("system", ctx):
            chunks.append(item)
            if isinstance(item, LLMOutput):
                output = item

        full = "".join(c["chunk"] for c in chunks if isinstance(c, dict) and c["segment"] == "reason_text")
        title = "".join(c["chunk"] for c in chunks if isinstance(c, dict) and c["segment"] == "event_title")
        assert full == "test reason text"
        assert title == "test event"
        assert output is not None
        assert output.event_title == "test event"
        assert output.verdict_text == "final verdict"

    @pytest.mark.asyncio
    async def test_streaming_uses_non_stream_rescue_when_stream_returns_no_content(self):
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)

        async def mock_stream(prompt, content):
            if False:
                yield ""

        orch.client.chat_stream = mock_stream
        orch.client.chat_complete = AsyncMock(return_value=_make_valid_llm_json())

        output = None
        async for item in orch.process_streaming("system", ctx):
            if isinstance(item, LLMOutput):
                output = item

        assert output is not None
        assert output.event_title == "test event"
        orch.client.chat_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_streaming_preserves_story_when_json_breaks_after_streaming(self):
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)

        broken_json = (
            '{"story_text":"legacy streamed story survives",'
            '"event_title":"legacy","dead_title":"",'
            '"is_dead":false,"attribute_changes":{"cultivation":1,"sin_value":0,"luck":0,"foundation":0},'
            '"next_action_required":"IDLE"'
        )

        async def mock_stream(prompt, content):
            for ch in broken_json:
                yield ch

        orch.client.chat_stream = mock_stream

        streamed = []
        output = None
        async for item in orch.process_streaming("system", ctx):
            if isinstance(item, LLMOutput):
                output = item
            else:
                if item["segment"] in ("reason_text", "story_text"):
                    streamed.append(item["chunk"])

        full = "".join(streamed)
        assert full == "legacy streamed story survives"
        assert output is not None
        assert output.reason_text == full
        assert output.story_text.startswith(full)

    @pytest.mark.asyncio
    async def test_streaming_uses_non_stream_rescue_after_partial_json_break(self):
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=False)

        broken_json = (
            '{"reason_text":"streamed reason survives",'
            '"verdict_text":"broken verdict'
        )

        async def mock_stream(prompt, content):
            for ch in broken_json:
                yield ch

        orch.client.chat_stream = mock_stream
        orch.client.chat_complete = AsyncMock(
            return_value=_make_valid_llm_json(
                reason_text="repaired reason text",
                verdict_text="repaired verdict",
                event_title="repaired event",
            )
        )

        streamed = []
        output = None
        async for item in orch.process_streaming("system", ctx):
            if isinstance(item, LLMOutput):
                output = item
            else:
                if item["segment"] == "reason_text":
                    streamed.append(item["chunk"])

        full = "".join(streamed)
        assert full == "streamed reason survives"
        assert output is not None
        assert output.reason_text == full
        assert output.verdict_text == "repaired verdict"
        assert output.event_title == "repaired event"
        orch.client.chat_complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_streaming_retry_then_fallback(self):
        orch = LLMOrchestrator()
        ctx = _make_context(is_dead=True)

        async def mock_stream(prompt, content):
            yield "bad json"

        orch.client.chat_stream = mock_stream

        output = None
        streamed = []
        async for item in orch.process_streaming("system", ctx):
            if isinstance(item, LLMOutput):
                output = item
            else:
                streamed.append(item["chunk"])

        assert output is not None
        assert output.is_dead is True
        assert len("".join(streamed)) > 0
