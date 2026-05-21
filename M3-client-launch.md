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

| Phase | 内容 | 类型 | 前端设计 |
|-------|------|------|----------|
| **3A** | 微信登录 + openid 绑定 + msgSecCheck 内容安全 | 后端为主 | — |
| **3B** | 局外商店（模型/API/购买/道具生效 + 前端商店页面） | 全栈 | ✅ `frontend-design` |
| **3C** | 名人堂读 API + 前端排行榜 + Canvas 战报图分享 | 全栈 | ✅ `frontend-design` |
| **3D** | 前端 UI 进阶（进度条/Modal/震动/TabBar 图标/环境配置） | 前端为主 | ✅ `frontend-design` |
| **3E** | 因果遮蔽卡前端特效 + 耳塞协议消费 + 集成测试 | 全栈 | ✅ `frontend-design` |
| **3F** | 国内云部署 + ICP 备案 + 微信审核提交 | DevOps | — |
