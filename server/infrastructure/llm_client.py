"""
DeepSeek 异步流式客户端

- async generator (yield) 逐 chunk 返回，M1 CLI 用 sys.stdout.write 消费，M2 用 WebSocket 消费
- 修复重试：Pydantic 校验失败时，把报错信息喂回下一次 Prompt
- 降级兜底：重试耗尽后，本地规则引擎生成保底结果
"""

import json
import random
from typing import AsyncGenerator, Optional

from server.config import settings
from server.domain.event import LLMInputContext, LLMOutput, AttributeChanges


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

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.9,
            max_tokens=512,
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
        """非流式调用，返回完整文本（用于需要完整 JSON 的解析场景）"""
        full_text = ""
        async for chunk in self.chat_stream(system_prompt, user_content):
            full_text += chunk
        return full_text


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

        for attempt in range(settings.llm_max_retries + 1):
            try:
                if fix_hint:
                    # 修复重试：把上次的校验错误追加到 system prompt
                    corrected_prompt = system_prompt + f"\n\n[格式修正指令]\n你上次返回的 JSON 格式有误，Pydantic 校验报错：{fix_hint}\n请严格按照 [输出规范] 中的 JSON Schema 返回正确格式。严禁任何 Markdown、前导词或后续解释。"
                else:
                    corrected_prompt = system_prompt

                raw_text = await self.client.chat_complete(corrected_prompt, user_content)
                output = self._parse_and_validate(raw_text)

                # 硬保护：is_dead 必须等于后端公式计算结果
                output.is_dead = context.is_dead
                if context.is_dead and not output.dead_title:
                    output.dead_title = self._generate_fallback_dead_title(context)

                return output

            except Exception as e:
                fix_hint = str(e)
                if attempt < settings.llm_max_retries:
                    continue
                # 重试耗尽，降级
                break

        # 降级兜底：本地规则引擎
        return self._fallback_resolve(context)

    def _parse_and_validate(self, raw_text: str) -> LLMOutput:
        """从 LLM 返回文本中提取 JSON 并用 Pydantic 校验"""
        text = raw_text.strip()

        # 移除可能的 Markdown 代码块标记
        if text.startswith("```"):
            lines = text.split("\n")
            # 移除首行 ```json（外层已确保以 ``` 开头）和末行 ```
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        data = json.loads(text)
        return LLMOutput.model_validate(data)

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
                event_title="天道裁决",
                story_text=story,
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
                event_title="劫后余生",
                story_text=story,
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
    ) -> AsyncGenerator[str | LLMOutput, None]:
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

        for attempt in range(settings.llm_max_retries + 1):
            try:
                if fix_hint:
                    corrected_prompt = system_prompt + f"\n\n[格式修正指令]\n你上次返回的 JSON 格式有误：{fix_hint}\n请严格按照 JSON Schema 返回。"
                else:
                    corrected_prompt = system_prompt

                full_text = ""
                async for chunk in self.client.chat_stream(corrected_prompt, user_content):
                    full_text += chunk
                    yield chunk

                output = self._parse_and_validate(full_text)
                output.is_dead = context.is_dead
                if context.is_dead and not output.dead_title:
                    output.dead_title = self._generate_fallback_dead_title(context)
                yield output
                return

            except Exception as e:
                fix_hint = str(e)
                if attempt < settings.llm_max_retries:
                    continue
                break

        # 降级
        output = self._fallback_resolve(context)
        story = output.story_text
        for char in story:
            yield char
        yield output
