# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

# 规则
思考过程使用中文。

## 里程碑需求文档

根据当前开发阶段，参考对应的里程碑需求文档：

- **M1 阶段 ✅（已完成）：** [M1-core-gameplay.md](M1-core-gameplay.md) — 核心玩法与数学公式验证原型 (CLI 版)
- **M2 阶段 ✅（已完成）：** [M2-networking.md](M2-networking.md) — 弱联机全生态与网络层建设 (WebSocket + Web 版)
- **M3 阶段（当前）：** [M3-client-launch.md](M3-client-launch.md) — 客户端全量合流与微信生态上架 (小程序商业版)

当前开发焦点：M3 已完成 Phase 3A（微信登录 + 内容安全）与玩法扩展首轮 Phase 3F/3G/3H（规划落档 + 命格签 + 天道人格扩容）；后续待收口 Phase 3D/3E 的真机联调与 Phase 3I 的部署上架。

编码时优先读取对应阶段的需求文档，确保实现与 PRD 一致。

### 阶段门控流程（严格执行）

每进入一个新阶段，必须遵循以下流程：

**Step 1 — 需求分析：** 调用 `/grill-me` skill 对当前阶段需求文档进行深度分析。逐项审查每个系统需求的实现细节、边界条件、潜在风险，并与已有代码对照找出偏差。

**Step 2 — 文档更新：** 将分析结论写回需求文档（作为新章节，如「需求分析记录」），记录所有设计决策、文档与代码偏差、预埋钩子等。

**Step 3 — 实现与验证：** 按需求实现功能。全部完成后运行全量测试确认覆盖率 100%，对照验收标准逐项检查。

**Step 4 — 阶段切换判定：** 确认当前阶段所有验收项达标后，更新本文件中的阶段完成状态（✅），将下一阶段标记为（当前），然后进入 Step 1。

严禁跳过任一阶段直接编码，严禁在未完成当前阶段验收的情况下切换到下一阶段。

**Step 5 — 阶段归档提交：** 每完成一个可独立验收的阶段/Phase，必须先补写对应 `M*.md` 的实施记录，再完成该阶段相关测试，随后立刻执行一次 Git `commit` 与 `push`。未完成当前阶段的文档、验证、提交、推送四项闭环，不得进入下一阶段。

### 文档更新规则

不是每轮代码改动都必须更新 MD，但每个可独立验收的功能闭环和所有会影响后续协作判断的变更必须写回文档。

**必须更新对应里程碑文档：**
- 阶段切换、Phase 完成状态、验收标准或 PRD 范围变化
- 架构决策、协议/接口变更、数据模型/数据库 Schema 变更、跨端约定变化
- 完整子功能落地后的实现记录、设计决策、测试结果与遗留风险
- 文档与代码出现偏差时的修正说明
- 阶段闭环后的 Git 归档信息（对应 commit/push 时机与阶段状态）

**建议更新对应里程碑文档：**
- 一个可演示/可验收的子功能完成，例如商店 API、名人堂 API、遮蔽卡特效、微信内容安全
- 影响后续排期或技术债判断的风险、限制、降级策略

**通常不需要更新 MD：**
- 纯 bugfix、局部样式微调、变量重命名、格式化、typo、少量测试补充
- 不改变设计约定、验收结论或跨模块行为的内部实现细节

`AGENTS.md` / `CLAUDE.md` 只记录阶段状态、工作流程和当前开发焦点；具体流水、设计决策、验收记录写入对应 `M*.md`。

## 项目身份

「天道不正经」— 微信小程序 idle 修仙肉鸽，DeepSeek LLM 驱动。玩家挂机修炼、触发 AI 生成故事事件、通过自由文本与天道"骚话对线"、死亡记录进入全服因果池成为其他玩家的游戏内容。

## 常用命令

```bash
# 安装依赖
cd server && pip install -r requirements.txt

# 运行 M1 CLI 原型（项目根目录执行）
python -m server.main

# 运行全部单元测试
cd server && python -m pytest tests/ -v

# 运行单个测试文件
cd server && python -m pytest tests/test_router.py -v

# 验证所有模块导入正常
python -c "from server.config import settings; from server.domain.player import PlayerState; from server.application.game_engine import GameEngine; from server.infrastructure.event_config import generate_local_event; print('OK')"
```

CLI 无需 API Key 即可运行 —— LLM 调用会降级为本地 mock 故事生成器，状态机、暴毙公式、事件池仍可完整测试。

## 架构

**分层 DDD，严格依赖方向：** `interface/` → `application/` → `domain/`。`infrastructure/` 实现 `application/` 依赖的接口。Domain 层零框架导入 —— 纯 Pydantic 模型 + 纯函数。

**关键安全规则：** `is_dead` 由 Python 后端使用暴毙公式在调用 LLM 之前算好。LLM 接收 `is_dead` 作为已知事实，只负责编故事解释结果。这防止了玩家通过自由文本进行 prompt 注入攻击，诱骗模型覆盖游戏规则。

### 暴毙公式

```
P_final = P_base + (1 - P_base) * (S_current / S_max) ^ (alpha * beta)
```
其中 `alpha = 3.0`，`beta = 1 + foundation / 100`。`P_base` 和 `S_max` 随境界变化（见 `config.py:REALM_CONFIG`）。后端调用 `roll_death_check()`，比较 `random() < P_final`。

### 事件路由（双轨制）

- **95% 本地轨道：** 每 10s tick，PRD 计数器累加 `random(2-12)`。若未达到当前境界的 PRD 阈值，从 `Config_Normal_Events.json` 抽取本地事件（三池系统：common/realm_specific/sin_conditional）。零 API 成本。
- **5% 天道轨道：** PRD 达到境界阈值、或修为达到大境界突破门槛、或 `sin_value` 达到 `sin_max` 时触发。暂停挂机，通过 DeepSeek 异步推演。
- **动态 PRD 阈值（按境界）：** 练气:60, 筑基:70, 金丹:85, 元婴:100, 化神:110, 渡劫:120, 大乘:999（永不触发）。
- **优先级链：** `飞升 > 天谴满 > PRD >= 境界阈值 > 大境界突破 > 本地日常`（PRD 作为"命运拦截器"优先于突破，防止突破必定触发 LLM 的设计死锁）。

### 六阶段状态机

`INIT → IDLE → EVENT_TRIGGER → AWAIT_DECISION → LLM_PROCESSING → SETTLEMENT → (IDLE 或 GAME_OVER)`

只能前向转换。`AWAIT_DECISION` 阶段有 60s 决策超时，超时自动选 A 选项并扣除 10% 修为（"道心蒙尘"）。详见 `game_engine.py` 完整生命周期。

### LLM 可靠性

DeepSeek 通过 OpenAI 兼容 API 返回 JSON。`LLMOrchestrator` 流程：流式收集 chunks → 拼接全文 → `Pydantic.model_validate_json()` → 若 `ValidationError`，重试最多 2 次，将错误信息注入下一次 prompt 作为修正提示 → 最终失败则 `_fallback_resolve()` 生成本地结果（不调用 API）。`is_dead` 字段在返回前**始终**被后端计算值覆盖。

### M1 → M2 演进

M1 仅 CLI（`interface/cli.py`），但与 M2（WebSocket + MySQL + 微信）共享全部 `application/` 和 `domain/` 层。关键迁移钩子：
- `DeepSeekClient.chat_stream()` 是异步生成器 —— CLI 用 `sys.stdout.write` 消费，M2 将用 `await ws.send_json()` 消费
- `PlayerState.to_dict()` / `PlayerState.from_dict()` 使用 Pydantic `model_dump()`/`model_validate()` 进行 JSON 序列化往返
- 超时控制置于接口层（`asyncio.wait_for`），而非引擎内部

### `is_breakthrough()` 注意事项

该函数接受显式 `realm_code` 参数（而非从 cultivation 推导），因为在突破边界上（如练气期满 1000），若内部推导会得出已进入下一境界，导致突破被漏判。调用方负责传入当前 `realm_code`。

### 配置

所有设置位于 `server/config.py`，通过 `pydantic-settings` 从 `.env` 加载。API Key 绝不硬编码。境界常量（修为上限、暴毙率、天谴上限）存放在 `REALM_CONFIG` 字典中，以整数境界代号为键（1=练气 至 7=大乘）。

### 四大天道人格

定义于 `heaven_persona.py`，附带 one-shot 示例，兼具双重用途：教授 LLM 写作风格，同时充当格式防火墙 —— 示例将 `player_custom_input` 作为数据字段而非系统指令展示，防止 prompt 注入。
