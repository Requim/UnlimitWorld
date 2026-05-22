# Milestone 3：客户端全量合流与微信生态上架 (小程序商业版)

## 1. 阶段目标

本阶段将前端（微信原生小程序）与后端进行全量合流。完善因果遮蔽卡、60秒对线超时等核心游戏机制，并对接微信内容合规、广告/支付组件，最终完成在微信平台的上线。

## 2. 核心系统需求

### 2.1 微信原生小程序开发（Frontend）
- **UI设计：**：使用frontend-design skill 进行设计。
- **组件树落地：**
  - **game 挂机主页：** 实现顶部【天谴值进度条】（包含 WXSS @keyframes 抖动火焰粒子特效）与【滚动日志流】。
  - **InteractionModal 对线弹窗：** 负责接收并组装 SC_STORY_STREAM 的流式文本，每收到一个 Chunk 触发一次 `wx.vibrateShort({type: 'light'})` 物理震动。
  - **网络管理器（utils/ws.js）：** 封装原生 `wx.connectSocket`，自带 10 秒一次的 CS_PING 心跳包，以及连接断开后 3 秒自动拉起重连的抗闪退重连状态机。

### 2.2 核心机制补丁（后端兜底）

- **60秒对线超时：** 当状态机停在 AWAIT_DECISION 超过 60 秒玩家不回应，后端强制代选选项 A，并扣除当前 10% 修为（文案提示：道心蒙尘）。
- **因果遮蔽卡拦截（剧透式反转）：** 在 SETTLEMENT 阶段，若 `is_dead = true` 且玩家账户有卡，后端无情扣卡，并强行阻断大模型原本生成的死亡结局，向前端发送特殊反转标识，前端全屏爆发金光动效，强制覆盖文案："宗门大能撕裂时空将你捞回！"。

### 2.3 微信内容安全防御（微信防火墙）

在 interface/ws.py 收到玩家的 CS_PLAYER_DECISION 文本输入时，在喂给 DeepSeek 之前，必须前置异步同步调用微信官方的文本安全安全审核接口（SecCheck）。若未通过审核，直接拦截该帧，不调用大模型，触发本地扣除功德处罚日志。

### 2.4 局外商店与名人堂

- 上线【天道虚无黑市】，使用结算产生的【天道点】兑换【因果遮蔽卡】、【降噪耳塞（天道失聪协议）】、【功德洗白券】。
- 上线【仙尊名人堂】，大乘期强制触发飞升雷劫，成功者写入名人堂表，并在前端提供"一键生成朋友圈/修仙群沙雕战报图"分享组件。

## 3. 部署与上架要求

- **服务器合规：** 服务端全量部署在国内云服务器（上海或广州节点），且通信域名必须完成国内合规的 ICP 备案。
- **大模型网络：** 统一接入国内云厂商（如腾讯云、火山引擎）提供的 DeepSeek 官方托管 API 节点，从根本上杜绝跨境网络抖动和政治封杀风险。

## 4. 验收标准

微信开发者工具里真机调试完全无报错，大模型字迹如丝般顺滑喷出，通过微信审核并成功发布内测小程序码。

---

## 5. 需求分析记录（/grill-me 深度分析）

> 分析日期：2026-05-21 | 分析人：Claude Code | 代码基线：M2 commit 871ddc7（225 测试全部通过）

### 5.1 现状总览：M2→M3 的起点状态

M2 已完成全部 6 个 Phase（2A/2A'/2B/2C/2D/2E），后端架构（DDD 分层 + WebSocket + MySQL/Redis + 怨念池 + 并发）已达工业级。前端完成小程序三页面骨架 + 水墨宇宙审美主题，但业务逻辑仅 game 页面有 WS 对接，shop/hall 仍为静态占位。

### 5.2 逐项需求对照分析

#### 5.2.1 60 秒对线超时（M3 §2.2）— ✅ 已完成

M2 Phase 2D 已完整实现：
- `config.py:32` — `decision_timeout: int = 60`
- `game_engine.py:257-263` — `is_decision_timeout()` 方法
- `game_engine.py:762-793` — `handle_timeout()` 扣除 10% 修为 + "道心蒙尘" 文案
- `game_engine.py:788-793` — `auto_timeout_submit()` 强制选 A
- `ws.py:299-304` — 主循环轮询检测超时

**结论：无需额外开发。**

#### 5.2.2 因果遮蔽卡拦截（M3 §2.2）— ✅ 已完成

M2 Phase 2D 已实现：
- `game_engine.py:665-669` — SETTLEMENT 阶段检测 `session.karma_shield > 0`，拦截死亡，扣卡，追加反转文案
- `game_engine.py:740` — `intercepted_by_shield=True` 传入 `EventSettlement` 供前端展示

**前端适配缺失：** 前端收到 `intercepted_by_shield=true` 时应有金光动效 + "宗门大能撕裂时空将你捞回！"全屏覆盖。目前前端未处理该字段。

**耳塞协议缺失：** `player.py:117-122` 定义了 `apply_deafness_protocol()` 但未被任何执行路径调用。`effective_luck()` 在 `deafness_protocol > 0` 时返回被动加成，但计数器永不递减。

#### 5.2.3 WeChat 内容安全（M3 §2.3）— ❌ 完全缺失

`ws.py:316-331` 收到 `CS_PLAYER_DECISION` 后直接将 `custom_text` 传入 `engine.submit_decision()`，零过滤。

需要实现：
- `wx.login` → 换取 `openid`（当前 `app.ts:58-62` 使用 `Date.now() + Math.random()` 伪造 player_id）
- `wx.security.msgSecCheck` → 后端接口层前置同步调用
- 审查不通过 → 拦截帧 → 扣除功德 → 返回警告日志（不调用 LLM）

**架构决策：** `msgSecCheck` 需要 `access_token`（有效期 7200s），需新增 `WeChatTokenManager` 定时刷新缓存。此接口为同步 HTTP 调用，放在 `interface/` 层而非 `application/` 层，保持 domain 层零微信依赖。

#### 5.2.4 局外商店（M3 §2.4）— ❌ 完全缺失

当前 `shop.ts:1-11` 为 11 行骨架，WXML 为静态 teaser。

需要新建：
- **后端模型：** `ShopItem`（id, name, cost_heaven_points, effect_type, effect_value）
- **后端 API：** `GET /api/shop/items`（商品列表）、`POST /api/shop/buy`（购买扣点）
- **道具系统：** 因果遮蔽卡（karma_shield+1）、失聪协议（deafness_protocol+1）、功德洗白券（sin_value 清零）
- **前端：** 天道点余额展示、商品列表、购买交互

**架构决策：** shop 为局外系统（不依赖当前 game session），使用 REST API 而非 WebSocket。

#### 5.2.5 名人堂（M3 §2.4）— ⚠️ 写路径完成，读 API 缺失

写入路径完整（`storage.py:110-139` `ImmortalHallRepository.insert/get_top`），但无 REST 端点暴露。

需要新增：
- **后端：** `GET /api/hall/top?limit=50` 调用已有 `ImmortalHallRepository.get_top()`
- **前端：** hall 页面加载时调用 API，渲染排行榜列表
- **分享组件：** Canvas 绘制战报图 → `wx.canvasToTempFilePath` → `wx.shareFileMessage` / `wx.showShareImageMenu`

**架构决策：** 战报图生成放前端（Canvas 2D API），后端只提供数据。避免后端图像渲染依赖（Pillow/Playwright）。

#### 5.2.6 小程序 UI 进阶（M3 §2.1）— ⚠️ 部分完成

| 需求项 | 当前状态 | 缺口 |
|--------|----------|------|
| 天谴值进度条 + 火焰粒子特效 | 纯数字文本 | 新建 progress-bar 组件 + CSS @keyframes |
| 滚动日志流 | ✅ scroll-view 已实现 | 无 |
| InteractionModal 对线弹窗 | ❌ 不存在 | 新建 components/interaction-modal/ |
| 震动反馈 | ❌ 零调用 | 每个 SC_STORY_STREAM chunk 触发 `wx.vibrateShort` |
| 网络管理器心跳 | ⚠️ 30s 间隔 | M3 要求 10s，改常量 |
| 网络管理器重连 | ⚠️ 指数退避 | M3 要求固定 3s，简化逻辑 |
| TabBar 图标 | ❌ 空字符串 | 制作 icon 图片资源 |
| 环境配置 | ❌ ws://localhost 硬编码 | 抽为 config，支持 dev/prod 切换 |
| sitemap.json | ❌ 文件缺失 | 新建 |
| components/ 目录 | ❌ 不存在 | 新建并迁移 modal |

#### 5.2.7 部署与合规（M3 §3）— ❌ 未开始

- ICP 备案：域名需完成 ICP 备案
- 国内云部署：腾讯云/阿里云上海或广州节点
- DeepSeek API 国内路由：需切换至火山引擎/腾讯云 DeepSeek 托管节点
- 微信小程序审核：需通过内容安全、隐私合规审核

### 5.3 架构决策汇总

| 决策 | 选择 | 理由 |
|------|------|------|
| 内容安全调用层 | `interface/` 层 | 保持 domain 层零微信依赖 |
| shop API 协议 | REST（非 WS） | 局外系统，无长连接需求 |
| 战报图生成 | 前端 Canvas 2D | 避免后端图像依赖 |
| 微信 access_token | 后端定时刷新缓存 | 7200s 有效期，避免每次请求 |
| 道具系统 | domain 模型 + ORM 持久化 | 与现有 PlayerState/PlayerAccount 一致 |
| 环境配置 | 小程序 app.json + 后端 .env | 前后端各自配置 |

### 5.4 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 微信审核内容安全不通过 | msgSecCheck 前置拦截 + 敏感词本地过滤双重兜底 |
| msgSecCheck API 限频 | 缓存 access_token，失败时降级为本地敏感词过滤 |
| 国内 DeepSeek API 服务不稳定 | 保留 M2 的 fallback 机制 + mock 降级 |
| ICP 备案耗时过长 | 开发期间使用 IP + 端口直连调试，备案并行推进 |
| Canvas 战报图兼容性 | 使用新版 Canvas 2D API，低版本微信降级为纯文本分享 |
| 道具系统数值平衡 | 因果遮蔽卡定价 = 1 局天道点收益期望值 |

### 5.5 前端设计强制规范

**所有涉及前端 UI 的 Phase（3B/3C/3D/3E），必须在编码前调用 `frontend-design` skill 进行设计评审。** 该 skill 要求：

- **设计思维先行：** 明确 Purpose → Tone → Constraints → Differentiation，确定大胆的美学方向后再编码
- **避免 AI 俗套：** 禁止 Inter/Roboto/Arial 字体、紫色渐变、通用布局模式
- **保持「水墨宇宙」主题一致性：** 在 M2 Phase 2A' 已建立的 5 层色彩体系（void/ink/paper/gold/cinnabar/jade）基础上深化，不可偏离
- **微信小程序兼容：** WXSS 不支持外链字体、高级 CSS 选择器、CSS Grid；动画仅限 `@keyframes` + `transition`
- **每个 Phase 的设计产出物：** design-direction.md（美学方向决策）+ 实际 WXML/WXSS/TS 代码

M2 Phase 2A' 已用该 skill 完成全局设计系统重塑（`app.wxss` 478 行）、game/shop/hall 三页面 WXSS 重写，效果显著。M3 延续此流程。

### 5.6 建议 Phase 拆分

基于以上分析，M3 建议拆分为 6 个 Phase：

| Phase | 内容 | 类型 | 前端设计 | 状态 |
|-------|------|------|----------|------|
| **3A** | 微信登录 + openid 绑定 + msgSecCheck 内容安全 | 后端为主 | — | ✅ |
| **3B** | 局外商店（模型/API/购买/道具生效 + 前端商店页面） | 全栈 | ✅ `frontend-design` | ⏳ |
| **3C** | 名人堂读 API + 前端排行榜 + Canvas 战报图分享 | 全栈 | ✅ `frontend-design` | ⏳ |
| **3D** | 前端 UI 进阶（进度条/Modal/震动/TabBar 图标/环境配置） | 前端为主 | ✅ `frontend-design` | ⏳ |
| **3E** | 因果遮蔽卡前端特效 + 耳塞协议消费 + 集成测试 | 全栈 | ✅ `frontend-design` | ⏳ |
| **3F** | 玩法扩展规划落档（命格签 + 天道人格扩容） | 设计/文档 | — | ✅ |
| **3G** | 命格签系统（开局三选一 + 局内修正） | 全栈 | ✅ `frontend-design` | ✅ |
| **3H** | 天道人格扩容（4 → 8） | 全栈 | — | ✅ |
| **3I** | 国内云部署 + ICP 备案 + 微信审核提交 | DevOps | — | ⏳ |

### 5.7 Phase 3D/3E 前端体验补齐记录

> 实施日期：2026-05-22 | 实施人：Codex | 测试：60 passed, 11 skipped（WebSocket / Shop / Hall / WeChat 定向套件）

#### 完成内容

| 文件 | 变更 |
|------|------|
| `client/utils/ws.ts` | M3 网络策略落地：心跳从 30s 调整为 10s；断线重连从指数退避改为固定 3s 自动拉起 |
| `client/pages/game/game.ts` | 新增境界→天谴上限映射、`sinPercent` 计算、SC_STORY_STREAM 轻震节流、`intercepted_by_shield` 前端识别与金光反转状态 |
| `client/pages/game/game.wxml` | 状态栏重排，新增天谴进度条；新增因果遮蔽卡触发时的全屏「因果逆转」覆盖层 |
| `client/pages/game/game.wxss` | 新增朱砂火脉进度条、火焰粒子、危险震动、遮蔽卡金光反转动效 |
| `client/app.json` | 补齐 tabBar 图标路径，避免微信开发者工具空 icon 报错 |
| `client/assets/tabbar/*.png` | 新增挂机/黑市/名人堂普通与选中态图标 |
| `client/sitemap.json` | 新增小程序 sitemap 配置，与 `app.json:sitemapLocation` 对齐 |

#### 设计决策

- **InteractionModal 暂不拆组件**：当前 `game` 页面已有完整的 `await_decision / streaming / settlement` 六态结构，本轮先补齐 M3 要求的触觉反馈、进度条和反转特效，避免在联调前做大规模组件迁移。后续 Phase 3D 收尾可将事件弹窗与流式故事区抽为 `components/interaction-modal/`。
- **流式震动节流**：后端 chunk 高频推送，前端每个 chunk 都直接震动会造成过强触感与耗电；实现为 120ms 最小间隔，仍能保留「天道逐字降临」的触觉节奏。
- **天谴上限前端映射**：后端当前下行帧未携带 `sin_max`，前端按境界本地映射计算进度条百分比，保持与 `REALM_CONFIG` 一致。后续可在 `SC_GAME_LOG / SC_HEAVEN_EVENT_TRIGGER / SC_EVENT_SETTLEMENT` 中显式下发 `sin_max` 以减少双端常量重复。
- **遮蔽卡反转只覆盖视觉，不改结算规则**：死亡拦截仍由后端 `intercepted_by_shield` 字段裁决，前端只根据该字段播放金光覆盖层，避免客户端越权影响生死结果。

#### 验证结果

- `python -m pytest server\tests\test_e2e_ws.py server\tests\test_shop.py server\tests\test_hall.py server\tests\test_wechat.py -q`：60 passed, 11 skipped。
- `npx -p typescript tsc -p client\tsconfig.json --noEmit` 未完成：仓库未安装 `wechat-miniprogram` 类型定义，且临时 TypeScript 6 对现有 `moduleResolution/baseUrl` 配置报弃用错误。该阻塞为项目现有工具链缺口，不是本轮代码路径的后端测试失败。

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3D | 抽离 `components/interaction-modal/`，并在微信开发者工具中做真机视觉/震动验证 |
| 3E | 耳塞协议消费链路需要端到端确认：购买后进入新局、`deafness_protocol` 递减/生效提示、账户持久化 |
| 3F | 国内云部署、ICP 备案、微信审核仍未开始 |

### 5.8 Phase 3E 局外道具消费闭环记录

> 实施日期：2026-05-22 | 实施人：Codex | 测试：88 passed, 8 skipped（Shop / GameEngine / WebSocket E2E 定向套件）

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/infrastructure/storage.py` | 新增 `consume_deafness_protocol()` 与 `consume_karma_shield()`，将天道失聪协议和因果遮蔽卡从“账户库存”语义改为一次性消费库存 |
| `server/interface/ws.py` | 开局时 `get_or_create()` 玩家账号；若账户有失聪协议则消费 1 次，并仅给本局传入 `deafness_protocol=1`；结算后同步遮蔽卡消耗与天道点收益到账号 |
| `server/tests/test_shop.py` | 新增仓储消费测试与 WebSocket 结算资产同步 mock 测试 |

#### 设计决策

- **失聪协议按局消费**：`player_account.deafness_protocol` 表示局外库存；开新局时若库存大于 0，后端扣 1 次库存，并在本局 `PlayerState.deafness_protocol=1`，使 `effective_luck()` 在整局内提供 +10 逻辑气运。
- **遮蔽卡按触发消费**：`player_account.karma_shield` 表示局外库存；开局时加载可用数量进入本局，真正触发 `intercepted_by_shield` 后再扣账户库存，避免购买 1 张卡后跨局无限复活。
- **结算天道点回写账号**：事件结算产生 `heaven_points_earned` 后，通过 `PlayerAccountRepository.update_heaven_points()` 同步到局外账号，保证商店余额能看到真实收益。
- **账号创建位置**：WebSocket `CS_START_GAME` 时调用 `get_or_create()`，保持“先开局再拥有可购买账号”的业务直觉，也避免 `/api/shop/buy` 找不到正常玩家。

#### 验证结果

- `python -m pytest server\tests\test_shop.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`：88 passed, 8 skipped。
- `python -m compileall server -q`：通过。

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3E | 在微信开发者工具中真机验证：购买失聪协议 → 开新局看到生效日志 → 商店库存扣减；购买遮蔽卡 → 触发死亡拦截 → 库存扣减 |

### 5.9 Phase 3E 内容安全处罚资产同步记录

> 实施日期：2026-05-22 | 实施人：Codex | 测试：59 passed, 9 skipped（Shop / WeChat / WebSocket E2E 定向套件）

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/interface/ws.py` | 在 `msgSecCheck` 拦截分支中新增 `_sync_account_penalty()`，将违规输入扣除的功德同步回局外账号 |
| `server/infrastructure/storage.py` | `update_heaven_points()` 增加 `max(0, ...)` 下限保护，避免处罚或异常扣点把余额写成负数 |
| `server/tests/test_shop.py` | 新增处罚同步 helper 测试与余额扣减下限测试 |

#### 设计决策

- **处罚同时作用于局内与局外**：违规输入会先更新当前 `session.heaven_points`，再通过仓储把同额扣减写回 `player_account.heaven_points`，保证当局显示和商店余额一致。
- **余额不允许为负**：无论是奖励还是处罚，账号层 `heaven_points` 最终都被钳位在 `>= 0`，减少外部接口和并发异常导致的脏数据风险。

#### 验证结果

- `python -m pytest server\tests\test_shop.py server\tests\test_wechat.py server\tests\test_e2e_ws.py -q`：59 passed, 9 skipped。
- `python -m compileall server -q`：通过。

### 5.10 Phase 3F 玩法扩展规划记录（/grill-me 深度分析）

> 分析日期：2026-05-22 | 分析人：Codex | 范围：命格签系统 + 天道人格扩容 | 结论：先做 3F 文档落档，再按 3G / 3H 分阶段实施

#### 目标与玩家心理

- **核心目标**：提升复玩率与每局差异感，让玩家在“再开一局”时有明确的新鲜感和策略预期。
- **当前短板**：现有开局在数值与流程上过于同质，天道人格虽然已有文风差异，但玩家对“这把遇到的是哪类天道”感知还不够强。
- **保留优势**：继续强化“挂机修仙 + 天道对线 + 黑色幽默暴毙”的主情绪，不引入重战斗或复杂社交系统。

#### 现状对照与设计结论

| 维度 | 当前现状 | 结论 |
|------|----------|------|
| 开局流程 | `CS_START_GAME` 后直接 `new_game()`，缺少局前抉择 | 最适合在 WebSocket `INIT` 握手阶段插入命格三选一，不改长期主状态机 |
| 会话持久化 | `PlayerState.to_dict()/from_dict()` 已用于断线重连 | 命格签可直接挂在 `PlayerState`，无需新增账号表 |
| 天道人格池 | 当前文档定义 4 个，人格抽取代码仍只抽前 3 个 | Phase 3H 需要先修复抽取 bug，再扩到 8 个常驻人格 |
| 前端游戏页 | 已有 `connecting / idle / await_decision / streaming / settlement / game_over` 六态页面 | 命格签 UI 以页面内弹层实现，新增 `preparing` 过渡态即可 |
| 测试基础 | 已有 WebSocket E2E、GameEngine、人格 Prompt 测试 | 3G/3H 可以在现有测试体系上增量补覆盖 |

#### Phase 3G 设计范围：命格签系统

- 仅做 **局内命格签**，不做账号解锁、稀有度、收藏册。
- 开局随机给 3 张，从 4 张基础命格中三选一；全部默认解锁。
- 服务端协议新增：
  - `SC_DESTINY_OFFER`
  - `CS_SELECT_DESTINY_SIGN`
- 首版命格固定为：

| 命格 | 效果 |
|------|------|
| **嘴硬成道** | `luck +5`；本次事件使用自由文本时额外获得 `heaven_points +3`，并追加 `sin_value +5` |
| **清修避世** | `foundation +8`；每 tick 的 `prd_counter` 增量 `-3`（最低保底 1）；所有结算 `heaven_points x0.9` |
| **借命赌徒** | `luck +8`、`foundation -8`；每 tick 的 `prd_counter` 增量 `+2`；所有结算 `heaven_points x1.5` |
| **福祸同炉** | 开局 `sin_value +10`、`foundation +6`；所有结算 `heaven_points x1.3` |

#### Phase 3H 设计范围：天道人格扩容

- 在现有 4 个基础上扩成 8 个常驻人格。
- 新增 4 个：

| 人格 | 核心气质 | 裁决偏好 |
|------|----------|----------|
| **因果账房先生** | 精算、记账、秋后算账 | 先让利再追债，擅长“这账先记着” |
| **命盘赌坊主** | 庄家、赔率、煽动冒险 | 高风险高收益，鼓励玩家搏命 |
| **朱笔记仇官** | 刻薄、冷笑、翻旧账 | 对嘴硬和挑衅最敏感，记仇感最强 |
| **玉律监考官** | 规训、打分、判卷 | 把修仙视作考试，偏好“你是否合格”叙事 |

#### 前后端接口草案

- **后端握手链路**：`CS_START_GAME` → `SC_DESTINY_OFFER` → `CS_SELECT_DESTINY_SIGN` → `SC_GAME_LOG`
- **局内状态**：`PlayerState` 新增 `destiny_sign_id / destiny_sign_title / destiny_mods`
- **前端状态**：`UIState` 新增 `PREPARING`
- **文档与测试要求**：
  - 3G 完成后写入 `### 5.11 Phase 3G 命格签系统实施记录`
  - 3H 完成后写入 `### 5.12 Phase 3H 天道人格扩容实施记录`

#### 暂缓项

- 赌约系统
- 天道关系谱
- 死法图鉴
- 因果回声
- 人格专属触发权重池

#### 风险与缓解

| 风险 | 缓解 |
|------|------|
| 新握手流程影响现有 WebSocket E2E | 先补测试 helper，统一处理开局拿命格 → 选命格 |
| 命格效果过强导致数值失衡 | 首版只改初始属性、PRD、少量天道点倍率，不触碰核心暴毙公式 |
| 人格变多导致 prompt 体积膨胀 | 延续当前精简 prompt 模板，每个人格只保留口吻/裁决/禁区三类信息 |
| 阶段编号冲突 | 本文档从此将部署上架阶段顺延为 `3I`，AGENTS/CLAUDE/README 同步 |

#### 阶段提交规则落档

- 每完成一个可独立验收的 Phase，必须先补写本里程碑文档，再执行测试，随后立即 `commit` 与 `push`。
- 本轮按以下顺序执行：
  1. **3F**：文档与规则落档
  2. **3G**：命格签系统
  3. **3H**：天道人格扩容

### 5.11 Phase 3G 命格签系统实施记录

> 实施日期：2026-05-22 | 实施人：Codex | 测试：83 passed（GameEngine / WebSocket E2E 定向套件）

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/domain/destiny.py` | 新增命格签目录、三选一抽取逻辑与四张基础命格配置 |
| `server/domain/player.py` | `PlayerState` 新增 `destiny_sign_id / destiny_sign_title / destiny_mods`，并补充命格初始修正、PRD 修正、自由文本奖惩、天道点倍率 helper |
| `server/application/game_engine.py` | 新增 `prepare_new_game()` / `get_pending_destiny_offers()`；`new_game()` 接收 `destiny_sign_id`；tick PRD 步长与结算逻辑接入命格修正 |
| `server/interface/ws.py` | WebSocket 握手改为 `CS_START_GAME → SC_DESTINY_OFFER → CS_SELECT_DESTINY_SIGN → SC_GAME_LOG` |
| `client/utils/actions.ts` | 新增 `CS_SELECT_DESTINY_SIGN`、`SC_DESTINY_OFFER`、`UIState.PREPARING` |
| `client/pages/game/game.ts` / `game.wxml` / `game.wxss` | 新增命格签选择弹层与前端协议流转 |
| `server/tests/test_game_engine.py` / `test_e2e_ws.py` | 新增命格签相关单测与 E2E 覆盖，并将开局 helper 统一迁移到新握手流程 |

#### 设计决策

- **命格签只插入 `INIT` 握手，不新增长期主状态机**：`GameEngine` 仍只在正式 `new_game()` 后进入 `IDLE`，避免影响后续挂机、事件、结算六阶段生命周期。
- **命格签只挂 `PlayerState`**：断线重连天然复用现有 `session_json` 快照，不引入账号表迁移和额外 schema 风险。
- **嘴硬成道奖励允许在未死亡时结算**：额外 `heaven_points +3` 直接通过事件结算回写局内/局外余额，让玩家当局就能感知“嘴硬有收益”。
- **前端使用页内弹层而非独立页面**：保持小程序游戏页的单页六态结构，只加一个 `preparing` 过渡态，减少跳页与状态同步复杂度。

#### 验证结果

- `python -m pytest server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`：83 passed。
- `python -m compileall server -q`：通过。

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3G | 微信开发者工具实机目测命格签弹层布局与点击态 |

### 5.12 Phase 3H 天道人格扩容实施记录

> 实施日期：2026-05-22 | 实施人：Codex | 测试：99 passed（HeavenPersona / GameEngine / WebSocket E2E 定向套件）

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/application/heaven_persona.py` | 新增 4 个常驻人格 Prompt：因果账房先生、命盘赌坊主、朱笔记仇官、玉律监考官 |
| `server/tests/test_heaven_persona.py` | 扩展人格注册表、Prompt 常量、fallback 行为与 schema 注入覆盖 |
| `server/tests/test_game_engine.py` | 更新默认人格池断言，并新增可抽到扩容人格的验证 |

#### 设计决策

- **扩容优先做“可辨识的文风差异”**：每个人格继续沿用当前精简 prompt 结构，只强化口吻、裁决偏好和叙事隐喻，避免 prompt 体积再次膨胀。
- **不重写 Prompt 工厂**：在现有常量 + registry 模式上直接扩 4 个新人格，降低对 `get_persona_prompt()`、fallback 和测试基线的扰动。
- **抽取逻辑复用 3G 已修正的人格池选择**：`GameEngine.new_game()` 已改为从完整 `PERSONA_NAMES` 抽取，3H 只需扩容注册表即可生效。

#### 验证结果

- `python -m pytest server\tests\test_heaven_persona.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`：99 passed。
- `python -m compileall server -q`：通过。

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3H | 后续可在真机联调阶段补一轮截图审校，确认新人格名在前端标题与日志中的可读性 |
