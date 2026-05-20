# Milestone 1：核心玩法与数学公式验证原型 (CLI 版)

## 1. 阶段目标

本阶段属于核心可玩性原型（Prototype）验证。不引入微信小程序、不引入数据库、不引入网络通信。通过纯 Python 控制台（CLI）交互，闭环验证：

- 7 个境界的挂机速度与数值流转。
- 三次方复合暴毙率公式在边界状态下的表现。
- DeepSeek 大模型在"三大天道人格"下的 Prompt 表现和 JSON 返回稳定性。

## 2. 核心系统需求

### 2.1 数值状态机与 Tick 引擎（application/game_engine.py）

- **挂机循环：** CLI 通过用户按下 Enter 键手动模拟一次 10 秒的 Tick。
- **事件路由：** 每次 Tick 累加 PRD 步长（random(2, 12)）。优先级为：天谴满 100 → PRD 达 80（触发大模型奇遇）→ 修为满大境界（触发突破大考）→ 本地日常。
- **本地日常：** 100% 依赖 Config_Normal_Events.json 配置文件。通过解析器动态还原带占位符的文本并结算数值。

### 2.2 复合暴毙公式逻辑

后端必须在调用 LLM 之前，利用以下公式算出 `is_dead` 结论：

$$P_{final} = P_{base} + (1 - P_{base}) \times \left( \frac{S_{current}}{S_{max}} \right)^{3 \times (1 + F/100)}$$

当且仅当 $S_{current} \ge 100$ 时，`is_dead` 强行收敛至 `True`。

### 2.3 天道 Prompt 工厂（application/heaven_persona.py）

实现"太上忘情（高冷）"、"混沌乐子人（高危）"、"唯爱护短（爽文）"三大 System Prompt 模板。模板必须携带一个标准的 One-shot 输入输出 JSON 示例，锁死大模型的返回格式（禁止 Markdown 的 \`\`\`json 标记包装，必须返回纯字符串 JSON）。

### 2.4 LLM 异常降级链路（infrastructure/llm_client.py）

- 调用 DeepSeek-V3 或 DeepSeek-R1 API。
- **容错处理：** 若大模型返回非标准 JSON、网络 5xx 或超时，后端自动触发 2 次自动 Retry。若 2 次均失败，启动降级本地规则引擎，直接从本地 JSON 库中抽取一个对应结局，强行将文本拼装输出，保证游戏不断死。

## 3. 交付物与验收标准

- **交付物：** 包含 domain/、application/、infrastructure/ 和 interface/cli.py 的纯 Python 源码包。
- **验收标准：** 在控制台运行 `python main.py`，能顺畅挂机、输入骚话对线、触发暴毙、并能在结算时打印出大模型生成的死因和最终天道点。

---

## 4. 需求分析记录（/grill-me 深度分析）

> 分析日期：2026-05-20 | 分析人：Claude Code

### 4.1 数值状态机与 Tick 引擎

**PRD 阈值设计演进：从固定 80 → 动态按境界分档**

原始 M1 文档标注 PRD 阈值为固定 80，实际实现为动态分档：

| 境界 | PRD 阈值 | 设计意图 |
|------|----------|----------|
| 练气期 | 60 | 新手高频体验 LLM 事件，建立认知 |
| 筑基期 | 70 | 逐渐降低频率 |
| 金丹期 | 85 | 接近原始设计 |
| 元婴期 | 100 | 事件更稀有更史诗 |
| 化神期 | 110 | 高境界减少 API 成本 |
| 渡劫期 | 120 | 最稀有，每次都是大事件 |
| 大乘期 | 999 | 飞升后永不触发 |

**优先级链设计理由：** PRD 先于突破（"命运拦截器"）防止了设计死锁——如果突破优先，则每次修为达 cap 必定触发 LLM，5% 发生率无法保证。PRD 先拦截意味着突破前夕可能插入意外奇遇，这才符合"天道不正经"的体验定位。

**`is_breakthrough()` 参数设计：** 该函数需要显式传入 `realm_code` 而非内部推导。因为在突破边界上（如练气期满 1000），`get_realm_by_cultivation(1000)` 会返回 2（筑基期），导致突破被漏判。调用方负责传入当前 `realm_code`。commit 176c117 修复了 `game_engine.py:99` 中漏传此参数的 bug。

### 4.2 复合暴毙公式

**文档偏差修正：强制死亡条件从绝对值改为相对值**

原 M1 文档：「当且仅当 S_current ≥ 100 时，is_dead 强行收敛至 True」

实际实现：`S_current ≥ sin_max(realm)`，每个境界的 sin_max 不同（练气:50 → 渡劫:100）。

**设计理由：** 低境界玩家根基浅、扛不住高天谴，天谴 50 就应该死；高境界道心稳固，能扛到 100。这符合修仙世界观——练气期小修士天谴 50 已经是天地不容，渡劫期老怪天谴 100 才引动灭世神罚。

**公式验证：**
$$P_{final} = P_{base} + (1 - P_{base}) \times \left( \frac{S_{current}}{S_{max}} \right)^{\alpha \times (1 + F/100)}$$

- α = 3.0，β(F) = 1 + F/100
- 边界行为已验证：sin=0 → P_final = P_base；sin=sin_max → P_final ≈ 1.0；foundation=100 → 指数 6.0 → 大幅压低暴毙率
- `roll_death_check()` 在 sin_current ≥ sin_max 时短路返回 True（不掷骰）

### 4.3 天道 Prompt 工厂

**One-shot 示例的双重用途：**
1. 教授 LLM 目标写作风格（冰冷文言 / 无厘头网感 / 宠溺口吻）
2. 充当**格式防火墙**——示例将 `player_custom_input` 放在 JSON 数据字段内，而非系统指令位置，让 LLM 理解它是数据而非可执行命令

**Prompt 注入双重防护：**
- 第一层：格式防火墙（One-shot 示例中的数据定位）
- 第二层：后端硬覆盖（`output.is_dead = context.is_dead`，在 Pydantic 校验之后、返回之前强制执行）

**容错策略：** 虽然 System Prompt 明确要求"严禁 Markdown"，但 `_parse_and_validate()` 仍然兼容处理 ```json 包裹，作为防御性容错。commit 176c117 移除了该函数中的冗余死代码（`lines[0].startswith("```")` 在外层已确保为 True）。

### 4.4 LLM 异常降级链路

**完整容错路径（全部有测试覆盖）：**

| 路径 | 行为 |
|------|------|
| 首次 API 调用成功 + JSON 合法 | 直接返回 |
| JSON 不合法 → 重试 1 | prompt 注入 fix_hint（Pydantic 报错原文） |
| 重试 1 失败 → 重试 2 | 再次注入 fix_hint |
| 全部重试耗尽 | `_fallback_resolve()` 本地规则引擎兜底 |
| openai 库不可用 | `_mock_stream()` 提供降级故事 |
| `llm_max_retries = -1` | range(0) 为空，直接走 fallback |

### 4.5 M1 → M2 预埋钩子

以下 M1 已实现但标记为 M2/M3 激活的功能：

- **因果遮蔽卡（karma_shield）：** `_settle()` 中已实现拦截逻辑，M1 CLI 无获取途径
- **天道失聪协议（deafness_protocol）：** `PlayerState` 中已实现 `effective_luck()` 加成，M1 无消耗渠道
- **天道夺舍人格（OVERLORD_PROMPT）：** Prompt 已定义，M1 不分配此人格，M3 激活
- **死亡因果池（_dead_registry）：** M1 用内存 list 模拟，M2 迁移到 MySQL dead_registry 表
- **名人堂（_immortal_hall）：** M1 用内存 list 模拟，M2 迁移到 MySQL immortal_hall 表

### 4.6 M1 验收状态

| 验收项 | 状态 | 证据 |
|--------|------|------|
| `python -m server.main` 可运行 | ✅ | `server/main.py` → `asyncio.run(cli_main())` |
| 顺畅挂机（Enter 键 tick） | ✅ | CLI 主循环，IDLE 状态按 Enter 推进 |
| 输入骚话对线（A/B/C） | ✅ | `submit_decision()` + 自由文本输入 |
| 触发暴毙 + LLM 死因 | ✅ | 暴毙公式 + LLM 推演 + dead_title 自动填充 |
| 结算天道点 | ✅ | `_calc_heaven_points()` |
| 单元测试 100% 分支覆盖 | ✅ | 179 passed，core modules all 100% |
| 集成测试（真实 DeepSeek API） | ✅ | 7 passed（完整生命周期/校验/安全/超时/死因池/因果引用/飞升） |
