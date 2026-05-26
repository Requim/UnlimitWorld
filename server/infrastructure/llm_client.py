"""
DeepSeek 异步流式客户端

- async generator (yield) 逐 chunk 返回，M1 CLI 用 sys.stdout.write 消费，M2 用 WebSocket 消费
- 修复重试：Pydantic 校验失败时，把报错信息喂回下一次 Prompt
- 降级兜底：重试耗尽后，本地规则引擎生成保底结果
"""

import json
import logging
import random
import time
from typing import AsyncGenerator, Optional

from server.config import settings
from server.domain.event import LLMInputContext, LLMOutput, AttributeChanges


logger = logging.getLogger("uvicorn")


class StreamFieldExtractor:
    """从流式 JSON 中增量提取多个字符串字段。"""

    def __init__(self, target_keys: list[str]):
        self._target_keys = {f'"{key}"': key for key in target_keys}
        self._phase = "seek_key"
        self._recent = ""
        self._escape = False
        self._unicode_buffer = ""
        self._current_key = ""

    def feed(self, chunk: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for ch in chunk:
            if self._phase == "seek_key":
                self._recent = (self._recent + ch)[-48:]
                for quoted_key, key in self._target_keys.items():
                    if self._recent.endswith(quoted_key):
                        self._current_key = key
                        self._phase = "seek_colon"
                        break
            elif self._phase == "seek_colon":
                if ch == ":":
                    self._phase = "seek_open_quote"
            elif self._phase == "seek_open_quote":
                if ch == '"':
                    self._phase = "capture"
            elif self._phase == "capture":
                if self._unicode_buffer:
                    self._unicode_buffer += ch
                    if len(self._unicode_buffer) == 4:
                        try:
                            out.append((self._current_key, chr(int(self._unicode_buffer, 16))))
                        except ValueError:
                            pass
                        self._unicode_buffer = ""
                        self._escape = False
                    continue

                if self._escape:
                    mapping = {
                        '"': '"',
                        "\\": "\\",
                        "/": "/",
                        "b": "\b",
                        "f": "\f",
                        "n": "\n",
                        "r": "\r",
                        "t": "\t",
                    }
                    if ch == "u":
                        self._unicode_buffer = ""
                    else:
                        out.append((self._current_key, mapping.get(ch, ch)))
                        self._escape = False
                    continue

                if ch == "\\":
                    self._escape = True
                    continue

                if ch == '"':
                    self._phase = "seek_key"
                    self._current_key = ""
                    self._recent = ""
                    continue

                out.append((self._current_key, ch))
        return out


# ═══════════════════════════════════════════════════════════════
# DeepSeek API 客户端（OpenAI 兼容接口）
# ═══════════════════════════════════════════════════════════════

class DeepSeekClient:
    """封装 DeepSeek API 调用，支持流式输出和重试"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = base_url or settings.deepseek_base_url
        self.model = model or settings.deepseek_model

    def _build_messages(self, system_prompt: str, user_content: str) -> list[dict]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    async def chat_stream(
        self,
        system_prompt: str,
        user_content: str,
    ) -> AsyncGenerator[str, None]:
        """
        异步生成器：逐 chunk 返回大模型文本。

        M1 CLI: for chunk in client.chat_stream(...): sys.stdout.write(chunk)
        M2 WS:  for chunk in client.chat_stream(...): await ws.send_json({chunk})
        """
        try:
            from openai import AsyncOpenAI
        except ImportError:
            # 如果 openai 库不可用，使用模拟模式
            async for chunk in self._mock_stream(system_prompt, user_content):
                yield chunk
            return

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=settings.deepseek_request_timeout,
        )

        response = await client.chat.completions.create(
            model=self.model,
            messages=self._build_messages(system_prompt, user_content),
            temperature=settings.deepseek_temperature,
            max_tokens=512,
            response_format={"type": "json_object"},
            stream=True,
        )

        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _mock_stream(self, system_prompt: str, user_content: str) -> AsyncGenerator[str, None]:
        """
        模拟流式输出（当 openai 库不可用或 API Key 未配置时）。
        生成一个默认的降级故事。
        """
        mock_story = (
            "天道在虚空中沉默了片刻。你的骚话没有引起任何波澜。"
            "本地规则引擎接管了这次判定——不浪漫，但可靠。"
        )
        for char in mock_story:
            yield char

    async def chat_complete(self, system_prompt: str, user_content: str) -> str:
        """非流式调用，直接返回 message.content（用于需要完整 JSON 的解析场景）"""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            full_text = ""
            async for chunk in self._mock_stream(system_prompt, user_content):
                full_text += chunk
            return full_text

        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=settings.deepseek_request_timeout,
        )
        response = await client.chat.completions.create(
            model=self.model,
            messages=self._build_messages(system_prompt, user_content),
            temperature=settings.deepseek_temperature,
            max_tokens=512,
            response_format={"type": "json_object"},
            stream=False,
        )
        if not response.choices:
            return ""

        content = response.choices[0].message.content or ""
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                else:
                    parts.append(str(item))
            return "".join(parts)
        return str(content)


# ═══════════════════════════════════════════════════════════════
# LLM 调用编排器（含 Retry + Fallback）
# ═══════════════════════════════════════════════════════════════

class LLMOrchestrator:
    """
    编排一次完整的大模型推演：

    1. 组装 System Prompt（天道人格 + One-shot）和 User Content（PlayerContext JSON）
    2. 流式调用 DeepSeek
    3. Pydantic 校验返回的 JSON
    4. 失败则修复重试（最多 settings.llm_max_retries 次）
    5. 重试耗尽则降级到本地规则引擎
    """

    def __init__(self, client: Optional[DeepSeekClient] = None):
        self.client = client or DeepSeekClient()

    @staticmethod
    def _compose_story_text(reason_text: str, verdict_text: str) -> str:
        reason = (reason_text or "").strip()
        verdict = (verdict_text or "").strip()
        if reason and verdict:
            return f"{reason}\n\n{verdict}"
        return reason or verdict

    def _normalize_output_segments(self, output: LLMOutput, fallback_story: str = "") -> LLMOutput:
        if not output.reason_text:
            output.reason_text = (output.story_text or fallback_story or "").strip()
        output.verdict_text = (output.verdict_text or "").strip()
        output.story_text = self._compose_story_text(output.reason_text, output.verdict_text)
        return output

    async def process(
        self,
        system_prompt: str,
        context: LLMInputContext,
    ) -> LLMOutput:
        """
        执行一次完整的大模型推演，返回通过 Pydantic 校验的 LLMOutput。

        对 is_dead 字段做硬保护：无论 LLM 返回什么，始终用后端传入的 context.is_dead 覆盖。
        """
        user_content = context.model_dump_json(ensure_ascii=False)
        raw_text = ""
        fix_hint = ""
        request_started_at = time.perf_counter()

        for attempt in range(settings.llm_max_retries + 1):
            try:
                if fix_hint:
                    # 修复重试：把上次的校验错误追加到 system prompt
                    corrected_prompt = system_prompt + f"\n\n[格式修正指令]\n你上次返回的 JSON 格式有误，Pydantic 校验报错：{fix_hint}\n请严格按照 [输出规范] 中的 JSON Schema 返回正确格式。严禁任何 Markdown、前导词或后续解释。"
                else:
                    corrected_prompt = system_prompt

                raw_text = await self.client.chat_complete(corrected_prompt, user_content)
                output = self._parse_and_validate(raw_text)
                output.is_dead = context.is_dead
                if context.is_dead and not output.dead_title:
                    output.dead_title = self._generate_fallback_dead_title(context)
                output = self._normalize_output_segments(output)

                logger.info(
                    "[LLM] 非流式完成 total=%.0fms trigger=%s persona=%s attempt=%s",
                    (time.perf_counter() - request_started_at) * 1000,
                    context.trigger_type,
                    context.heaven_persona,
                    attempt + 1,
                )
                return output

            except Exception as e:
                fix_hint = str(e)
                logger.warning(
                    "[LLM] 非流式失败 attempt=%s reason=%s raw=%s",
                    attempt + 1,
                    fix_hint,
                    self._summarize_raw_text(raw_text),
                )
                if attempt < settings.llm_max_retries:
                    continue
                # 重试耗尽，降级
                break

        # 降级兜底：本地规则引擎
        logger.warning(
            "[LLM] 非流式触发降级 fallback total=%.0fms trigger=%s persona=%s",
            (time.perf_counter() - request_started_at) * 1000,
            context.trigger_type,
            context.heaven_persona,
        )
        return self._normalize_output_segments(self._fallback_resolve(context))

    def _parse_and_validate(self, raw_text: str) -> LLMOutput:
        """从 LLM 返回文本中提取 JSON 并用 Pydantic 校验"""
        text = self._extract_json_candidate(raw_text)
        data = json.loads(text)
        output = LLMOutput.model_validate(data)
        return self._normalize_output_segments(output)

    def _extract_json_candidate(self, raw_text: str) -> str:
        """尽量从模型返回中剥离出最像 JSON 的主体。"""
        text = raw_text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        if not text:
            return text

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1].strip()
        return text

    def _summarize_raw_text(self, raw_text: str, limit: int = 240) -> str:
        """压缩失败原文用于日志，避免整段刷屏。"""
        compact = raw_text.replace("\n", "\\n").replace("\r", "\\r")
        if len(compact) <= limit:
            return compact
        head = limit // 2
        tail = limit - head - 3
        return f"{compact[:head]}...{compact[-tail:]}"

    def _fallback_with_preserved_story(self, context: LLMInputContext, story_text: str) -> LLMOutput:
        """解析失败但正文已流出时，保留正文，只对结构字段做兜底。"""
        output = self._fallback_resolve(context)
        cleaned_story = story_text.strip()
        if cleaned_story:
            output.reason_text = cleaned_story
        return self._normalize_output_segments(output, fallback_story=cleaned_story)

    async def _rescue_structured_output(
        self,
        system_prompt: str,
        user_content: str,
        context: LLMInputContext,
        streamed_story: str,
        attempt: int,
        request_started_at: float,
    ) -> LLMOutput:
        """当流式 JSON 损坏但正文已成功流出时，用非流式补拉完整结构。"""
        repaired_raw = await self.client.chat_complete(system_prompt, user_content)
        output = self._parse_and_validate(repaired_raw)
        output.is_dead = context.is_dead
        if context.is_dead and not output.dead_title:
            output.dead_title = self._generate_fallback_dead_title(context)
        output = self._normalize_output_segments(output, fallback_story=streamed_story)

        cleaned_story = streamed_story.strip()
        if cleaned_story:
            output.reason_text = cleaned_story
            output.story_text = self._compose_story_text(output.reason_text, output.verdict_text)

        logger.info(
            "[LLM] 流式损坏后非流式补全成功 total=%.0fms trigger=%s persona=%s attempt=%s",
            (time.perf_counter() - request_started_at) * 1000,
            context.trigger_type,
            context.heaven_persona,
            attempt,
        )
        return output

    def _fallback_resolve(self, context: LLMInputContext) -> LLMOutput:
        """降级兜底：本地规则引擎生成保底结果"""
        if context.is_dead:
            story = (
                f"天道意志不可违逆。{context.player_status.player_name}"
                f"在{context.player_status.realm}的修行之路上，"
                f"因果之力终于反噬。天雷滚滚，万劫不复。"
            )
            dead_title = self._generate_fallback_dead_title(context)
            return LLMOutput(
                reason_text=story,
                verdict_text=dead_title,
                event_title="天道裁决",
                story_text=self._compose_story_text(story, dead_title),
                is_dead=True,
                dead_title=dead_title,
                attribute_changes=AttributeChanges(),
                next_action_required="GAME_OVER",
            )
        else:
            story = (
                f"{context.player_status.player_name}凭借自身的根基与气运，"
                f"在危机中勉强站稳了脚跟。天道虽然不悦，但规则之下，你活了下来。"
            )
            return LLMOutput(
                reason_text=story,
                verdict_text="记账在案，暂缓追缴。",
                event_title="劫后余生",
                story_text=self._compose_story_text(story, "记账在案，暂缓追缴。"),
                is_dead=False,
                dead_title="",
                attribute_changes=AttributeChanges(
                    cultivation=random.randint(100, 500),
                    sin_value=random.randint(5, 15),
                ),
                next_action_required="IDLE",
            )

    def _generate_fallback_dead_title(self, context: LLMInputContext) -> str:
        """生成降级死因文本"""
        titles = [
            f"在{context.player_status.realm}修行中因果反噬而亡",
            f"天道神罚降下，{context.player_status.player_name}身死道消",
            "触怒天道被无情抹杀",
            "因果之力吞噬，陨落于天地之间",
        ]
        return random.choice(titles)

    async def process_streaming(
        self,
        system_prompt: str,
        context: LLMInputContext,
    ) -> AsyncGenerator[dict | LLMOutput, None]:
        """
        流式处理 + 最终返回 LLMOutput。

        用法:
            output = None
            async for chunk, result in orchestrator.process_streaming(prompt, ctx):
                if chunk:
                    yield chunk  # 前端打字机渲染
                if result:
                    output = result  # 最终结算
        """
        user_content = context.model_dump_json(ensure_ascii=False)
        full_text = ""
        fix_hint = ""
        request_started_at = time.perf_counter()
        best_streamed_story = ""
        best_streamed_title = ""

        for attempt in range(settings.llm_max_retries + 1):
            try:
                if fix_hint:
                    corrected_prompt = system_prompt + f"\n\n[格式修正指令]\n你上次返回的 JSON 格式有误：{fix_hint}\n请严格按照 JSON Schema 返回。"
                else:
                    corrected_prompt = system_prompt

                full_text = ""
                extractor = StreamFieldExtractor(["event_title", "reason_text", "verdict_text", "story_text"])
                first_token_logged = False
                first_story_logged = False
                attempt_story = ""
                attempt_title = ""

                logger.info(
                    "[LLM] 开始流式推演 trigger=%s persona=%s attempt=%s",
                    context.trigger_type,
                    context.heaven_persona,
                    attempt + 1,
                )
                async for chunk in self.client.chat_stream(corrected_prompt, user_content):
                    full_text += chunk
                    now = time.perf_counter()
                    if not first_token_logged:
                        logger.info(
                            "[LLM] 首 token 到达 %.0fms attempt=%s",
                            (now - request_started_at) * 1000,
                            attempt + 1,
                        )
                        first_token_logged = True

                    for segment, segment_chunk in extractor.feed(chunk):
                        if segment == "event_title":
                            attempt_title += segment_chunk
                        elif segment in ("reason_text", "story_text"):
                            attempt_story += segment_chunk
                            if not first_story_logged:
                                logger.info(
                                    "[LLM] 首个正文字符到达 %.0fms attempt=%s",
                                    (now - request_started_at) * 1000,
                                    attempt + 1,
                                )
                                first_story_logged = True
                        yield {"segment": segment, "chunk": segment_chunk}

                if not full_text.strip():
                    logger.warning(
                        "[LLM] 流式未收到 content，转非流式补拉 trigger=%s persona=%s attempt=%s",
                        context.trigger_type,
                        context.heaven_persona,
                        attempt + 1,
                    )
                    full_text = await self.client.chat_complete(corrected_prompt, user_content)

                output = self._parse_and_validate(full_text)
                output.is_dead = context.is_dead
                if context.is_dead and not output.dead_title:
                    output.dead_title = self._generate_fallback_dead_title(context)
                output = self._normalize_output_segments(output, fallback_story=attempt_story)
                if attempt_title.strip():
                    output.event_title = attempt_title.strip()
                logger.info(
                    "[LLM] 流式完成 total=%.0fms story_len=%s attempt=%s",
                    (time.perf_counter() - request_started_at) * 1000,
                    len(output.reason_text or ""),
                    attempt + 1,
                )
                yield output
                return

            except Exception as e:
                fix_hint = str(e)
                if len(attempt_story.strip()) > len(best_streamed_story.strip()):
                    best_streamed_story = attempt_story.strip()
                if len(attempt_title.strip()) > len(best_streamed_title.strip()):
                    best_streamed_title = attempt_title.strip()
                logger.warning(
                    "[LLM] 流式推演失败 attempt=%s reason=%s raw=%s",
                    attempt + 1,
                    fix_hint,
                    self._summarize_raw_text(full_text),
                )
                if attempt_story.strip():
                    try:
                        output = await self._rescue_structured_output(
                            corrected_prompt,
                            user_content,
                            context,
                            attempt_story,
                            attempt + 1,
                            request_started_at,
                        )
                        if attempt_title.strip():
                            output.event_title = attempt_title.strip()
                        yield output
                        return
                    except Exception as repair_error:
                        fix_hint = f"{fix_hint}; rescue={repair_error}"
                        logger.warning(
                            "[LLM] 非流式补全失败 attempt=%s reason=%s",
                            attempt + 1,
                            repair_error,
                        )
                        break
                if attempt < settings.llm_max_retries:
                    continue
                break

        # 降级
        output = self._fallback_with_preserved_story(context, best_streamed_story)
        if best_streamed_title:
            output.event_title = best_streamed_title
        logger.warning(
            "[LLM] 触发降级 fallback total=%.0fms trigger=%s persona=%s preserved_story_chars=%s",
            (time.perf_counter() - request_started_at) * 1000,
            context.trigger_type,
            context.heaven_persona,
            len(best_streamed_story),
        )
        if not best_streamed_story:
            story = output.story_text
            for char in story:
                yield {"segment": "reason_text", "chunk": char}
        yield output
