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
| **3I** | 目标感闭环（本局执念 + 多榜单 + 盖棺定论结算） | 全栈/玩法 | ✅ `frontend-design` | ⏳ |
| **3J** | 异步因果偷渡（死亡遗毒 + 前人馈赠 + 因果污染榜） | 全栈/弱社交 | ✅ `frontend-design` | ⏳ |
| **3K** | 平常事件扩展（分池、轻选择、人格权重、目标推进） | 全栈/配置 | ✅ `frontend-design` | ⏳ |
| **3L** | 国内云部署 + ICP 备案 + 微信审核提交 | DevOps | — | ⏳ |

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
- **天谴上限前端映射**：首轮实现以前端按境界本地映射 `sin_max` 计算进度条百分比；2026-05-23 起后端在 `SC_GAME_LOG / SC_HEAVEN_EVENT_TRIGGER / SC_EVENT_SETTLEMENT` 中显式下发 `sin_max`，前端保留本地映射仅作兼容 fallback，减少双端常量漂移风险。
- **遮蔽卡反转只覆盖视觉，不改结算规则**：死亡拦截仍由后端 `intercepted_by_shield` 字段裁决，前端只根据该字段播放金光覆盖层，避免客户端越权影响生死结果。

#### 验证结果

- `python -m pytest server\tests\test_e2e_ws.py server\tests\test_shop.py server\tests\test_hall.py server\tests\test_wechat.py -q`：60 passed, 11 skipped。
- `npx -p typescript tsc -p client\tsconfig.json --noEmit` 未完成：仓库未安装 `wechat-miniprogram` 类型定义，且临时 TypeScript 6 对现有 `moduleResolution/baseUrl` 配置报弃用错误。该阻塞为项目现有工具链缺口，不是本轮代码路径的后端测试失败。

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3D | 抽离 `components/interaction-modal/`，并在微信开发者工具中做真机视觉/震动验证 |
| 3E | 耳塞协议消费链路需要端到端确认：购买后进入新局、`deafness_protocol` 递减/生效提示、账户持久化 |
| 3I | 国内云部署、ICP 备案、微信审核仍未开始 |

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

### 5.13 Phase 3D/3E 收口分析与协议补丁记录（/grill-me 深度分析）

> 分析/实施日期：2026-05-23 | 实施人：Codex | 范围：前端天谴进度展示契约收口 | 测试：93 passed, 14 skipped（WebSocket / Shop / Hall / WeChat / LLM 定向套件）

#### 现状判断

- 经过 Phase 3D/3E 首轮补齐后，小程序端天谴进度条已经可用，但 `sin_max` 仍依赖前端按境界名称本地推导。
- 这套兜底在当前版本可运行，但存在两个后续联调风险：
  1. 若后端 `REALM_CONFIG` 调整天谴上限，前端不一定同步更新；
  2. 断线重连、内容安全处罚日志、事件触发与结算三条路径的状态栏数据来源不完全一致，真机排查时容易出现“数值对得上、进度条不对”的假象。
- 因此本轮将“后端显式下发 `sin_max`，前端只保留 realm 映射作为 fallback”确定为 3D/3E 收口优先项。

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/interface/ws.py` | 在 `SC_GAME_LOG / SC_HEAVEN_EVENT_TRIGGER / SC_EVENT_SETTLEMENT` 三类下行帧中统一补充 `sin_max`；同时补齐断线重连成功帧、内容安全处罚日志帧、正式开局成功帧的 `sin_max` 下发 |
| `client/pages/game/game.ts` | 新增 `resolveSinMax()`，优先读取服务端下发的 `sin_max`，仅在老帧缺失该字段时退回本地境界映射 |
| `server/tests/test_e2e_ws.py` | 扩展前端契约测试，校验 `SC_GAME_LOG`、事件触发帧与结算帧均包含 `sin_max`，并与 `REALM_CONFIG` 对齐 |

#### 设计决策

- **协议显式优先于前端推导**：天谴上限属于后端规则的一部分，长期看应由规则源头直接下发；前端映射保留为兼容旧帧与本地开发兜底，而不是主数据源。
- **先收口契约，再做真机视觉验证**：当前 3D/3E 余下的联调工作多发生在微信开发者工具与真机环境里，因此先把帧结构收紧，能减少后续把 UI 误判成样式 bug 的概率。

#### 验证结果

- `python -m pytest server\tests\test_e2e_ws.py server\tests\test_shop.py server\tests\test_hall.py server\tests\test_wechat.py server\tests\test_llm_client.py -q`
  - 结果：93 passed, 14 skipped
- `python -m compileall server -q`
  - 结果：通过

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3D | 继续评估是否需要抽离 `components/interaction-modal/`，并在微信开发者工具中做视觉/震动真机确认 |
| 3E | 继续做耳塞协议、遮蔽卡、商店余额的端到端人工联调，确认购买、消费、持久化与展示完全一致 |

### 5.14 Phase 3D/3E 直谏可靠性补丁记录

> 实施日期：2026-05-23 | 实施人：Codex | 范围：直谏天道流式 JSON 失败时的保真兜底 | 测试：113 passed（LLM Client / GameEngine / WebSocket E2E 定向套件）

#### 现象与根因

- Heaven 事件中的“直谏天道”在个别人格下会出现：正文已经开始流式输出，但最终 JSON 包装解析失败，导致后端二次重试或直接用通用 fallback 覆盖原本已经生成出来的正文。
- 典型日志表现为：
  - 首 token 很晚；
  - `Expecting value` 或 `Expecting ',' delimiter`；
  - `触发降级 fallback`；
  - 玩家前端最终看到的却是明显风味不足的降级文案。
- 根因主要有三类：
  1. 结构化输出场景下采样温度偏高；
  2. 模型偶发在 JSON 前后夹带杂质；
  3. 当 `story_text` 已经流出但 JSON 尾部损坏时，旧逻辑仍会用整段 fallback 覆盖正文。

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/config.py` | 新增 `deepseek_temperature`，默认收敛到 `0.6`，降低结构化 JSON 漂移概率 |
| `server/application/heaven_persona.py` | 在输出规范中补充“尽量避免半角双引号”约束，减少 `story_text` 破坏 JSON 的概率 |
| `server/infrastructure/llm_client.py` | 新增 JSON 主体提取、失败原文摘要日志、`story_text` 已流出时的“保正文兜底”逻辑；仅在完全没有正文可保时才退回通用 fallback 文案 |
| `server/tests/test_llm_client.py` | 新增前后缀杂质 JSON 解析测试、流式正文已输出但 JSON 结尾损坏时的保正文回归测试 |

#### 设计决策

- **正文保真优先于通用兜底**：一旦玩家已经看到了模型生成的正文，就优先保留这段正文；降级只兜底结构字段与数值结算，避免体验上“前面像真人，最后突然像模板”。
- **流式重试只适合“尚未吐正文”的失败**：如果某次尝试已经把正文流给前端，再发起下一轮流式重试只会把不同版本文本串在一起，所以本轮将策略调整为“有正文就保正文、无正文再重试/降级”。
- **结构化输出采样要克制**：人格风味主要来自 prompt，而不是高温采样；对 JSON 契约来说，低一点的温度更划算。

#### 验证结果

- `python -m pytest server\tests\test_llm_client.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`
  - 结果：113 passed
- `python -m compileall server -q`
  - 结果：通过

### 5.15 Phase 3D/3E DeepSeek 流式兼容补丁记录

> 实施日期：2026-05-23 | 实施人：Codex | 范围：兼容 `deepseek-v4-flash` 的 reasoning-first 流式协议 | 测试：114 passed（LLM Client / GameEngine / WebSocket E2E 定向套件）

#### 现象与根因

- 切回 `deepseek-v4-flash` 后，直谏天道在 Heaven / Resentment 事件里频繁出现：
  - `Expecting value: line 1 column 1 (char 0)`
  - `raw=`
  - 最终直接 fallback
- 根因并不在 prompt 本身，而在于 `deepseek-v4-flash` 的流式返回会先长时间输出 `delta.reasoning_content`，而我们旧版客户端只消费 `delta.content`。
- 结果就是：模型其实一直在工作，但业务层看到的 `full_text` 为空串，最终被误判成“模型没回内容”。

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/infrastructure/llm_client.py` | 为 OpenAI 兼容调用补充 `response_format={"type":"json_object"}`；`chat_complete()` 改为真正的非流式 completion 调用，不再通过拼接 `chat_stream()` 伪装；若流式阶段整轮未收到 `content`，则自动补打一发非流式 completion 取最终 JSON |
| `server/tests/test_llm_client.py` | 新增 `response_format` 断言、非流式 `chat_complete()` 路径测试，以及“流式无 content 时自动转非流式补拉”的回归测试 |

#### 设计决策

- **reasoning 不上屏，但不能让它吃掉业务内容**：前端仍只展示 `story_text` 正文，不展示模型思维链；但当流式协议先吐 reasoning 时，后端必须有办法拿到最终 content。
- **流式失败补救优先走同模型非流式**：相比直接 fallback，本轮优先在同一次 attempt 内补打一发非流式 completion，把模型本来就能给出的最终 JSON 拿回来，保住人格文风与结算细节。
- **`chat_complete()` 与 `chat_stream()` 分职责**：后续所有“需要最终结构化 JSON”的场景都应走真正的非流式路径，避免再被某个供应商的流式字段习惯拖下水。

#### 验证结果

- `python -m pytest server\tests\test_llm_client.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`
  - 结果：114 passed
- `python -m compileall server -q`
  - 结果：通过


### 5.16 Phase 3D/3E ??????????

> ?????2026-05-25 | ????Codex | ????????????????? + ????????????????

#### ?????
- ??? `SC_EVENT_SETTLEMENT` ???????????????????????????????????
- ????????? `story_text` ????????????????????????????????????????

#### ????
- ?? `LLMOutput` / `EventSettlement` ?? `reason_text` ? `verdict_text`??? `story_text` ???????
- ??????????? `reason_text`?????????????????
- ??????? `verdict_text`???? Game Over ????? 3 ?????????????????????
- ???????? `verdict_text`???????? `event_title` / `dead_title`???????????

#### ?????
- Heaven / Resentment ????????? reason?????? verdict?
- ?????????????????????????
- ? fallback ?? JSON ??????????

### 5.17 Phase 3I/3J/3K 目标感与异步因果玩法方案（/grill-me 深度分析）

> 分析日期：2026-05-26 | 分析人：Codex | 范围：本局目标感、多榜单、弱社交因果偷渡、平常事件扩展 | 结论：部署上架前先补齐“每局以什么方式被世界记住”的玩法闭环

#### 设计问题

当前核心体验仍偏单线：玩家挂机修炼，最终只有“飞升成功上榜”或“死亡结束”两种强反馈。命格签和天道人格已经提高了开局差异，但仍不足以回答玩家开局时最关键的问题：**这局我到底在追什么？**

本轮玩法扩展的目标不是增加更复杂的战斗系统，而是把每局包装成一份可传播、可入榜、可污染后来者的修仙档案：

- 活着可以飞升上榜；
- 死了可以暴毙上榜；
- 嘴硬可以对线上榜；
- 赌命可以风险上榜；
- 作恶可以因果污染上榜；
- 前人死亡可以变成后来者的事件内容。

#### /grill-me 关键设计树与推荐答案

| 问题 | 推荐答案 |
|------|----------|
| 是否继续把“飞升”作为唯一胜利？ | 否。飞升保留为正统胜利，但新增暴毙、嘴硬、赌命、因果污染等并行目标，让失败也能成为荣耀。 |
| 是否做实时 PvP？ | 否。采用异步弱社交：玩家死亡/结算后留下因果记录，后续随机污染或馈赠其他玩家，避免实时对抗带来的挫败与合规风险。 |
| 害人玩法是否允许直接指定玩家？ | 否。第一版只允许投放到公共因果池，不允许点名、追杀、私聊或复仇链。 |
| 被害玩家是否应该纯吃亏？ | 否。每个因果偷渡事件必须有低风险选项、识破补偿或反向收益，让被害也像看笑话而不是被恶心。 |
| 普通事件是否继续只做数值加减？ | 否。普通事件要承担目标推进、人格表达、弱社交触发和轻选择，不再只是挂机日志噪声。 |
| 是否需要新增大状态机？ | 尽量不需要。3I/3J/3K 优先沿用现有 `IDLE / EVENT_TRIGGER / AWAIT_DECISION / SETTLEMENT` 流程，只在开局准备、普通事件生成和终局结算层加扩展字段。 |
| 内容安全如何处理玩家遗言/投毒文本？ | 复用 Phase 3A 的 `msgSecCheck`：所有遗言、投毒短语、名句榜内容在入池前审核；未通过则降级为本地模板。 |

#### Phase 3I：目标感闭环（本局执念 + 多榜单 + 盖棺定论）

**目标：** 让玩家开局 30 秒内形成明确本局目标，并在结算时获得“我这局成了什么”的强反馈。

##### 3I.1 本局执念

在命格签三选一之后，新增“本局执念”三选一。命格回答“我这局是什么打法”，执念回答“我这局追什么结果”。

首版执念建议：

| 执念 | 目标 | 奖励/风险 |
|------|------|-----------|
| **苟到筑基** | 到达筑基前不死亡 | 奖励天道点；自由文本怼天道会提高奖励但增加天谴 |
| **嘴硬十回合** | 累计使用自由文本回应天道达到指定次数 | 推进嘴硬榜；额外天道点；提高被记仇概率 |
| **死得漂亮** | 死亡时天谴、境界、事件稀有度达到评分阈值 | 推进暴毙榜；死亡也有高结算 |
| **借命翻盘** | 至少经历一次高风险事件并存活 | 推进赌命榜；奖励倍率提高 |
| **功德圆满** | 低天谴进入指定境界，不使用遮蔽卡 | 稳健奖励；推进功德类后续榜单 |
| **污染因果** | 死亡或结算时成功留下因果遗毒 | 推进因果污染榜；获得污染值 |

实现建议：

- `domain/ambition.py`：定义执念目录、三选一抽取、进度结算规则。
- `PlayerState`：新增 `ambition_id / ambition_title / ambition_progress / ambition_target`。
- WebSocket：新增 `SC_AMBITION_OFFER` 与 `CS_SELECT_AMBITION`，插入 `CS_SELECT_DESTINY_SIGN` 之后、正式 `SC_GAME_LOG` 之前。
- 前端：复用命格弹层视觉语言，新增“本局宣言”：
  - “你是借命赌徒，执念为死得漂亮，本局天道为命盘赌坊主。祂已经为你的命标好了赔率。”

##### 3I.2 多榜单

第一版只做 5 个榜，避免过度发散：

| 榜单 | 入榜条件 | 评分维度 |
|------|----------|----------|
| **飞升榜** | 飞升成功 | 境界、耗时、天谴、根基、是否使用道具 |
| **暴毙榜** | 死亡结算 | 死亡境界、天谴比例、事件稀有度、死法戏剧性 |
| **嘴硬榜** | 自由文本对线 | 自由文本次数、嘴硬收益、高天谴存活、被记仇次数 |
| **赌命榜** | 高风险事件 | 高风险选择次数、濒死存活、收益倍率、借命赌徒加权 |
| **因果污染榜** | 异步因果影响他人 | 遗毒触发次数、害人得分、传梗次数、导致死亡次数 |

实现建议：

- 后端新增统一 `LeaderboardEntry` 领域模型，避免飞升榜、暴毙榜、污染榜各自散落。
- 仓储层可以先复用现有 `immortal_hall` 思路，新增 `leaderboard_entries` 表或本地 mock 仓储。
- REST API：
  - `GET /api/leaderboards?type=ascension|death|taunt|gamble|karma_pollution`
  - `GET /api/leaderboards/me?player_id=...`
- 前端 hall 页面从单榜扩展为 Tab 榜单。

##### 3I.3 盖棺定论结算

终局不再只显示 Game Over，而是输出“盖棺定论”：

- 本局称号：如“雷劫嘴硬体验官”“练气期碰瓷大师”；
- 入榜结果：如“今日暴毙榜第 12”；
- 本局名场面：玩家输入 + 天道回应 + 结局摘要；
- 因果遗产：是否进入他人事件池；
- 下局推荐目标：挑战嘴硬榜 / 赌命榜 / 飞升榜。

验收标准：

- 玩家每局开局后可见一个明确执念进度；
- 死亡和飞升均能生成结算评分；
- 至少飞升榜、暴毙榜、嘴硬榜可读；
- 结算页能展示“本局称号 + 入榜结果 + 下局推荐目标”。

#### Phase 3J：异步因果偷渡（死亡遗毒 + 前人馈赠 + 因果污染榜）

**目标：** 把“死亡记录进入全服因果池”从背景设定升级为玩家能感知、能投放、能上榜的弱社交系统。

##### 3J.1 核心循环

1. 玩家死亡、飞升失败或完成特定执念；
2. 系统允许玩家留下遗言或选择本地模板；
3. 玩家选择一种因果偷渡类型；
4. 后端审核文本并写入公共因果池；
5. 后来者普通事件低概率抽到这条因果；
6. 后来者选择后产生收益/风险；
7. 原投放者累计污染值、触发次数和榜单分。

##### 3J.2 因果偷渡类型

| 类型 | 对后来者效果 | 反制方式 |
|------|--------------|----------|
| **误导选项** | 某个选项文案更诱人，但实际风险更高 | 选择保守项可得“识破因果”补偿 |
| **天谴残响** | 获得收益时额外增加少量天谴 | 消耗功德或选择净化 |
| **假功法** | 看似加修为，可能降低根基 | 根基高或清修类命格可识破 |
| **嘴硬传染** | 诱导后来者对天道自由文本开喷 | 成功加嘴硬进度，失败加天谴 |
| **雷劫标记** | 下一次高风险事件死亡率略升，奖励也升 | 使用遮蔽卡或低风险选项规避 |
| **因果碰瓷** | 搜刮尸骸得天道点，但污染值增加 | 安葬尸骸可得功德和少量修为 |

##### 3J.3 前人馈赠

为了避免弱社交全是恶意，飞升成功或功德路线玩家可以留下正向内容：

| 馈赠 | 效果 |
|------|------|
| **半卷功法** | 修为或根基小幅提升 |
| **护道残念** | 下一次死亡判定轻微降低 |
| **仙尊批注** | 揭示一个高风险选项的真实倾向 |
| **功德香火** | 降低少量天谴 |

##### 3J.4 数据模型建议

新增 `KarmaTrace`：

- `trace_id`
- `source_player_id`
- `source_player_name`
- `source_run_id`
- `trace_type`：`trap / gift`
- `effect_type`：`mislead / sin_echo / fake_manual / taunt_infection / thunder_mark / karma_extortion / blessing`
- `message`
- `toxicity_score`
- `trigger_count`
- `harm_score`
- `death_caused_count`
- `created_at`
- `expires_at`
- `is_approved`

新增 `KarmaTraceTrigger`：

- `trigger_id`
- `trace_id`
- `target_player_id`
- `target_run_id`
- `choice`
- `result_delta`
- `created_at`

##### 3J.5 公平与安全边界

- 不允许指定目标玩家；
- 新手前 3 局降低命中率；
- 同一玩家短时间不能连续踩同一来源因果；
- 每个负面事件必须提供低风险选项；
- 被害后至少给少量“识破因果”或日志爽感补偿；
- 所有玩家遗言、投毒短句、名句榜候选内容都必须先过 `msgSecCheck`；
- 审核失败时使用本地模板，例如“前人留下了一句被天道打码的遗言”。

验收标准：

- 死亡结算可生成 1 条因果偷渡记录；
- 普通事件池可抽取并展示前人遗毒；
- 后来者选择会回写 `trigger_count / harm_score`；
- 因果污染榜可按污染分排序；
- 审核失败不会入池原文。

#### Phase 3K：平常事件扩展（分池、轻选择、人格权重、目标推进）

**目标：** 让挂机过程不再只是等待 LLM 大事件，而是持续推进本局目标、榜单评分和弱社交内容。

##### 3K.1 普通事件分池

将当前普通事件从单一池扩展为多池：

| 事件池 | 作用 |
|--------|------|
| **修炼池** | 稳定加修为、根基，风险低 |
| **诱惑池** | 高收益，高天谴或埋后患 |
| **嘴硬池** | 提供自由文本插话机会，推进嘴硬榜 |
| **遗迹池** | 发现前人尸骸、残卷、墓碑 |
| **天道窥视池** | 天道人格主动评价玩家当前状态 |
| **因果回声池** | 从 `KarmaTrace` 抽取弱社交事件 |
| **赌命池** | 低概率高收益，推进赌命榜 |
| **功德池** | 稳健路线，降低天谴或增加功德类评分 |

##### 3K.2 普通事件轻选择

普通事件不必全部进入 LLM，但可以支持本地轻选择：

示例：

> 你在洞府墙上看到前人刻字：“选第二个，包飞升。”

- 相信前人：高收益，高天谴；
- 擦掉刻字：功德 +2，少量修为；
- 补一句更缺德的：嘴硬进度 +1，并可能生成新的因果偷渡。

实现建议：

- 扩展 `Config_Normal_Events.json` schema：
  - `event_pool`
  - `risk_level`
  - `ambition_tags`
  - `leaderboard_tags`
  - `persona_weight`
  - `choices`
  - `karma_trace_hook`
- 对无选择的旧事件保持兼容，避免一次性重写全部配置。

##### 3K.3 天道人格影响事件权重

天道人格不只改变文风，也轻微改变事件分布：

| 人格 | 权重倾向 |
|------|----------|
| 因果账房先生 | 因果回声、债务、追账事件权重提高 |
| 命盘赌坊主 | 赌命池、诱惑池权重提高 |
| 朱笔记仇官 | 嘴硬池、记仇事件权重提高 |
| 玉律监考官 | 功德池、规训事件权重提高 |
| 乐子型人格 | 荒诞事件、反常奖励权重提高 |

##### 3K.4 目标推进

普通事件结算时同步推进：

- `ambition_progress`
- `leaderboard_score_delta`
- `taunt_count`
- `gamble_survive_count`
- `karma_pollution_score`
- `death_drama_score`

验收标准：

- 普通事件至少分为 4 个可抽取事件池；
- 至少 10 条普通事件支持轻选择；
- 至少 3 个天道人格能影响普通事件池权重；
- 执念进度可以被普通事件推进；
- 老配置事件仍能正常加载。

#### 推荐实施顺序

1. **3I-1：本局执念最小闭环**
   - 新增执念目录、开局三选一、前端弹层和进度展示。
2. **3I-2：多榜单与盖棺定论**
   - 先实现飞升榜、暴毙榜、嘴硬榜；赌命榜和污染榜可预留 schema。
3. **3J-1：死亡遗言入池**
   - 死亡结算允许留遗言，审核后写入 `KarmaTrace`。
4. **3J-2：因果偷渡事件抽取**
   - 普通事件低概率抽中前人遗毒，并回写触发数据。
5. **3K-1：普通事件分池**
   - 配置 schema 扩展，保留旧事件兼容。
6. **3K-2：轻选择与人格权重**
   - 让普通事件能推进执念和榜单，不再只是日志。

#### 验证计划

- `python -m pytest server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`
- `python -m pytest server\tests\test_hall.py server\tests\test_shop.py server\tests\test_wechat.py -q`
- 新增测试文件建议：
  - `server/tests/test_ambition.py`
  - `server/tests/test_leaderboards.py`
  - `server/tests/test_karma_trace.py`
  - `server/tests/test_normal_event_pools.py`
- 前端 TypeScript 校验在现有工具链修复前继续记录为阻塞项；微信开发者工具真机验证作为 3I/3J/3K 每个 Phase 的人工验收项。

#### 风险与缓解

| 风险 | 缓解 |
|------|------|
| 榜单过多导致目标分散 | 第一版只上线飞升、暴毙、嘴硬三个强感知榜，赌命/污染榜可先只记录分数 |
| 害人玩法带来挫败 | 不做指定玩家、不连续命中、每个负面事件保留低风险选项和识破补偿 |
| 玩家遗言合规风险 | 入池前强制 `msgSecCheck`，失败使用本地模板 |
| 普通事件 schema 改动影响旧配置 | 新字段全部可选，旧事件走兼容路径 |
| 人格权重影响数值平衡 | 首版只影响事件池权重，不直接改暴毙公式 |
| 结算页信息过载 | 前端只展示称号、入榜结果、名场面、下局推荐四块，详细分数折叠 |

#### 产品原则

本轮玩法的核心不是让玩家永远赢，而是让每局都有可被记住的身份：

> 飞升是赢，暴毙是梗，嘴硬是资产，害人是因果，失败也能成为后来者的内容。

### 5.18 Phase 3I-1 本局执念最小闭环实施记录

> 实施日期：2026-05-26 | 实施人：Codex | 范围：开局执念三选一 + WebSocket 握手扩展 + 前端准备页串联 | 测试：90 passed（Ambition / GameEngine / WebSocket E2E 定向套件）

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/domain/ambition.py` | 新增本局执念目录、三选一抽取、按前端展示所需字段序列化 |
| `server/domain/player.py` | `PlayerState` 新增 `ambition_id / ambition_title / ambition_progress / ambition_target / ambition_progress_label` |
| `server/application/game_engine.py` | 新增待选执念状态、`prepare_ambition_selection()`、执念合法性校验，并在 `new_game()` 中写入执念字段 |
| `server/interface/ws.py` | 开局握手调整为 `CS_START_GAME -> SC_DESTINY_OFFER -> CS_SELECT_DESTINY_SIGN -> SC_AMBITION_OFFER -> CS_SELECT_AMBITION -> SC_GAME_LOG` |
| `client/utils/actions.ts` | 新增 `CS_SELECT_AMBITION` 与 `SC_AMBITION_OFFER` 协议常量 |
| `client/pages/game/game.ts/wxml/wxss` | 准备页从命格签选择扩展为“命格 -> 执念”两段式；挂机页顶部新增本局执念进度条式提示 |
| `server/tests/test_ambition.py` | 新增执念目录、抽取、查找测试 |
| `server/tests/test_game_engine.py` | 新增执念候选生成与 `new_game()` 写入执念字段测试 |
| `server/tests/test_e2e_ws.py` | E2E helper 适配新握手，并新增非法执念选择错误测试 |

#### 设计决策

- **执念插在命格之后、正式开局之前**：命格回答“这局怎么打”，执念回答“这局追什么”，两者共同组成开局宣言，但仍不新增长期主状态机。
- **首版只做目标可见，不急着做复杂评分**：本轮先让玩家在开局和挂机页明确看到“本局执念”，多榜单评分与盖棺定论留给 3I-2。
- **复用准备页视觉体系**：前端沿用命格签卡片结构，执念只强化朱砂光晕和“念”标识，保持 M2/M3 已建立的水墨宇宙风格，不另起一套 UI。
- **旧会话恢复不重走执念流程**：若断线重连命中 active session，仍直接恢复既有 `PlayerState`；新增执念字段由 Pydantic 默认值兼容旧快照。

#### 验证结果

- `python -m pytest server\tests\test_ambition.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`
  - 结果：90 passed
- `python -m compileall server -q`
  - 结果：通过

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3I-2 | 多榜单与盖棺定论结算：先做飞升榜、暴毙榜、嘴硬榜的统一评分与结算展示 |
| 3I | 执念进度推进仍是静态字段，后续需要在自由文本、突破、死亡、赌命事件中累计进度 |
| 3J | `污染因果` 执念需要等 `KarmaTrace` 入池与触发回写后才具备完整闭环 |

### 5.19 Phase 3I-2 盖棺定论最小闭环实施记录

> 实施日期：2026-05-26 | 实施人：Codex | 范围：终局称号 + 候选榜类型 + 结算评分 + 下局目标提示 | 测试：90 passed（Ambition / GameEngine / WebSocket E2E 定向套件）

#### 完成内容

| 文件 | 变更 |
|------|------|
| `server/domain/event.py` | `EventSettlement` 新增 `epitaph_title / leaderboard_type / leaderboard_score / next_goal_hint` |
| `server/application/game_engine.py` | 新增 `build_run_epitaph()`，在死亡、飞升、嘴硬结算时生成候选榜信息 |
| `client/pages/game/game.ts/wxml/wxss` | Game Over 面板展示“本局称号、候选榜、评分、下局提示” |
| `server/tests/test_game_engine.py` | 覆盖死亡与飞升的盖棺定论字段 |
| `server/tests/test_e2e_ws.py` | 扩展 `SC_EVENT_SETTLEMENT` 结构契约，确保前端依赖字段下发 |

#### 设计决策

- **先做候选榜，不先建正式榜单表**：本轮目标是终局爽感最小闭环，让玩家先看到“我这局属于什么榜”；正式持久化排行榜留给后续榜单仓储阶段。
- **失败也给身份**：死亡默认进入暴毙榜候选，使用自由文本死亡优先进入嘴硬榜候选，飞升成功进入飞升榜候选。
- **评分轻量可解释**：首版评分只由境界、天谴比例、存活时间、天道点、是否嘴硬等本地可得字段组成，不额外调用 LLM。
- **前端只展示四块信息**：本局称号、候选榜、评分、下局提示，避免结算页信息过载。

#### 验证结果

- `python -m pytest server\tests\test_ambition.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`
  - 结果：90 passed
- `python -m compileall server -q`
  - 结果：通过

#### 后续剩余项

| Phase | 剩余工作 |
|-------|----------|
| 3I-3 | 正式多榜单持久化与 hall 页面 Tab 化：飞升榜、暴毙榜、嘴硬榜 |
| 3I | 执念进度仍未按事件实时推进，需要在自由文本、突破、死亡和高风险事件中累计 |
| 3J | 因果污染榜需要等 `KarmaTrace` 投毒/触发系统落地 |
