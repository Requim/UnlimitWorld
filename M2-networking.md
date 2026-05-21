# Milestone 2：弱联机全生态与网络层建设 (WebSocket + 基础小程序)

## 1. 阶段目标

将 M1 的纯进程内存骨架，升级为能够承载高并发网络通信的工业级后端。本阶段不急于上架微信，而是通过浏览器客户端（或 Postman/Web-Dev-Tools）联调 WebSocket 协议同时上线第一版极简微信原生小程序，调通基础长连接，实现全服怨念事件的纯文本动态注入与基础渲染，并补全数据库、缓存以及全服死因弱联机池。

## 2. 核心系统需求

### 2.1 异步网络层改造（interface/ws.py）

- 引入 FastAPI WebSocket 路由，客户端通过 `wss://domain.com/ws/game?player_id=xxx` 建立长连接。
- 实现统一的通信帧路由（Action Frame）：
  - **上行：** CS_START_GAME、CS_PING、CS_PLAYER_DECISION。
  - **下行：** SC_GAME_LOG、SC_HEAVEN_EVENT_TRIGGER、SC_STORY_STREAM（逐字流式）、SC_EVENT_SETTLEMENT。
- **流式拆分：** 将 DeepSeek 的异步生成器通过 yield 拆解为字符块（Chunk），以 SC_STORY_STREAM 帧实时高频喷向客户端，实现真正的"打字机"效果。

### 2.2 微信原生小程序极简骨架（前端）

- **三大页面基础布局：** 建立 `pages/game/game`（挂机主界面）、`pages/shop/shop`（局外黑市）、`pages/hall/hall`（名人堂）三个页面，在 `app.json` 中注册。
- **单例网络管理器（utils/ws.ts）：** 封装原生 `wx.connectSocket`，提供全局可调用的 `send()` 和 `onMessage()` 方法，统一管理 WebSocket 长连接生命周期（自动重连、心跳维持、消息分发）。
- **数据流调通：** game 页面加载时自动连接 WebSocket（`wss://domain.com/ws/game?player_id=xxx`），通过 `<text>` 组件静态呈现后端下发的挂机日志（`SC_GAME_LOG`）与对线文本（`SC_STORY_STREAM` 逐字拼接）。对线时通过极简按钮（A / B / 自由输入）进行选项上报（`CS_PLAYER_DECISION`）。
- **页面状态映射：** 根据后端下行帧切换页面 UI 状态 —— IDLE（挂机中）、EVENT_TRIGGER（显示选项按钮）、STREAMING（打字机效果）、SETTLEMENT（显示结算结果）。

### 2.3 数据持久化与三级缓存（infrastructure/storage）

- **MySQL 表结构建设：** 落地 player_account、dead_registry、immortal_hall、active_session、heaven_overlord_pool 五张核心表。
- **Redis 缓存提速：** 玩家每 10 秒 Tick 产生的灵石/修为/天谴变动，直接写入 Redis Hash（player:session:{player_id}）。
- **异步写回：** 后端每 30 秒或玩家触发重大状态变动（突破/对线结束）时，触发异步 Task 将 Redis 的快照快写入 MySQL active_session 表中，拒绝高频高并发 I/O。

### 2.4 弱联机"怨念残留"池（全服踩雷）

完美落实上一轮审查的 PRD 逻辑：

- 玩家暴毙满足门槛后，写入 heaven_overlord_pool 并定时每 10 分钟清洗 250 条精品死因到 Redis 怨念 Set 中。
- 修改日常 Tick 路由，使其有 10% 的概率抽取全服玩家怨念转换为【本地血红日志】或 5% 的概率转为【大模型心魔试炼】。

## 3. 交付物与验收标准

- **交付物：** 部署在 Linux 测试环境的 FastAPI 异步后端 + 支持真机调试的基础小程序代码包（`client/` 目录）。
- **后端验收标准：** 启动 5 个测试脚本并发连接 WebSocket，挂机数值能高频刷新，输入骚话后能收到流式逐字喷出的故事，关闭脚本再重连能恢复状态。
- **前端验收标准：** 微信开发者工具中打开 `client/` 项目，点击「开始游戏」后自动连接 WebSocket 并收到每 Tick 日志下行；触发天道事件后显示 A/B/C 选项按钮，选择后展示流式故事文本；游戏结束后显示结算结果（天道点/死因/名人堂）。

---

## 4. 需求分析记录（/grill-me 深度分析）

> 分析日期：2026-05-21 | 分析人：Claude Code | 代码基线：M1 commit 356b0b9

### 4.1 架构决策：单例 GameEngine → 多玩家架构

M1 的 `GameEngine` 是单玩家单体（`self.session` + `self._dead_registry` + `self._immortal_hall` 全在一个对象内）。M2 每个 WebSocket 连接一个独立玩家，需要拆分：

| 组件 | M1 位置 | M2 策略 |
|------|---------|---------|
| `session` (PlayerState) | GameEngine 实例属性 | 每连接一个 GameEngine 实例，session 隔离 |
| `_dead_registry` | GameEngine 实例属性 (list) | **提升为全服共享单例** → `infrastructure/shared_state.py` |
| `_immortal_hall` | GameEngine 实例属性 (list) | **提升为全服共享单例** |
| `LLMOrchestrator` | GameEngine 实例属性 | 可共享（无状态），也可每连接独立（隔离 API 调用） |

**决策：** 新建 `infrastructure/shared_state.py` 持有全服单例 `DeadRegistry` 和 `ImmortalHall`。GameEngine 通过构造函数依赖注入获取共享引用。`_fetch_random_karma()` 改为从共享 DeadRegistry 查询。

### 4.2 WebSocket Action Frame 协议设计

基于 M1 已有的 Pydantic 模型（EventTrigger, EventSettlement, PlayerState），定义 3 上行 + 4 下行帧：

**上行（Client → Server）：**

| Action | 字段 | 触发 |
|--------|------|------|
| `CS_START_GAME` | `player_name: str` | 新一局 |
| `CS_PING` | （空） | 每 10s 心跳保活 |
| `CS_PLAYER_DECISION` | `choice_id: str` (A/B/C), `custom_text: str` | 玩家对线决策 |

**下行（Server → Client）：**

| Action | 字段 | M1 来源 |
|--------|------|---------|
| `SC_GAME_LOG` | `log_text, cultivation, sin_value, realm, sin_phase` | TickResult (LOCAL) |
| `SC_HEAVEN_EVENT_TRIGGER` | `trigger: EventTrigger` (JSON) | TickResult.trigger |
| `SC_STORY_STREAM` | `chunk: str, is_last: bool` | LLMOrchestrator.process_streaming 逐 chunk |
| `SC_EVENT_SETTLEMENT` | `settlement: EventSettlement` (JSON) | TickResult.settlement |

**流式拆分：** M1 的 `process_streaming()` 已逐 char yield，直接复用。每个 char → 一个 `SC_STORY_STREAM` 帧，最后一个帧 `is_last: true` 附带完整的 LLMOutput 校验结果。前端收到 `is_last` 后关闭打字机效果，展示完整故事。

### 4.3 数据库表结构设计

**`player_account`**（M1 已有 Pydantic 模型 `PlayerAccount`）：
```sql
player_id VARCHAR(32) PRIMARY KEY,
wechat_openid VARCHAR(64) DEFAULT '',
player_name VARCHAR(64) DEFAULT '无名修士',
avatar_url VARCHAR(256) DEFAULT '',
heaven_points INT DEFAULT 0,
deafness_protocol INT DEFAULT 0,
karma_shield INT DEFAULT 0,
talent_bonus JSON DEFAULT '{}',
created_at DATETIME DEFAULT NOW(),
last_login DATETIME DEFAULT NOW()
```

**`dead_registry`**（M1 已有 Pydantic 模型 `DeadRecord`）：
```sql
id INT AUTO_INCREMENT PRIMARY KEY,
player_id VARCHAR(32),
player_name VARCHAR(64),
realm VARCHAR(32),
realm_code INT,
dead_title VARCHAR(256),
sin_value INT DEFAULT 0,
survived_seconds INT DEFAULT 0,
created_at DATETIME DEFAULT NOW()
```

**`immortal_hall`**（M1 用 `list[dict]` 存储）：
```sql
id INT AUTO_INCREMENT PRIMARY KEY,
player_id VARCHAR(32),
player_name VARCHAR(64),
ascension_title VARCHAR(128),
total_heaven_points INT DEFAULT 0,
ascended_at DATETIME DEFAULT NOW()
```

**`active_session`**（新增，M2 断线重连核心）：
```sql
player_id VARCHAR(32) PRIMARY KEY,
session_json JSON,          -- PlayerState.model_dump_json()
stage VARCHAR(32),          -- 当前状态机阶段
trigger_json JSON NULL,     -- 若在 AWAIT_DECISION，保存 EventTrigger
updated_at DATETIME DEFAULT NOW()
```

**`heaven_overlord_pool`**（新增，全服怨念池）：
```sql
id INT AUTO_INCREMENT PRIMARY KEY,
dead_registry_id INT,
player_name VARCHAR(64),
dead_title VARCHAR(256),
realm_code INT,
quality_score FLOAT DEFAULT 0,  -- 精品评分
is_selected TINYINT DEFAULT 0,  -- 是否已被选入怨念 Set
created_at DATETIME DEFAULT NOW()
```

### 4.4 Redis 缓存设计

| Key | 类型 | 用途 | 更新频率 |
|-----|------|------|----------|
| `player:session:{player_id}` | Hash | 实时 PlayerState 快照 | 每 10s tick |
| `dead:resentment:set` | Set | 精品怨念死因（250条） | 每 10min 清洗 |
| `dead:resentment:candidates` | List | 待评分候选死因 | 玩家死亡时 push |

**写入策略：**
- Tick → `HMSET player:session:{pid} cultivation X sin_value Y ...`（轻量，10s 一次）
- 重大事件（突破/对线结束/死亡）→ 异步 Task 读取 Redis Hash → `UPSERT active_session`
- 玩家暴毙 → `INSERT dead_registry` + `RPUSH dead:resentment:candidates dead_title`
- 定时 10min → `RENAME dead:resentment:candidates dead:resentment:bak` → 评分 → 取 top 250 → `SADD dead:resentment:set`

### 4.5 怨念残留池集成点

M1 的 `_process_local_event()` 仅从本地 JSON 池抽取。M2 需在抽取前插入怨念判定：

```
每次 tick → _process_local_event():
  roll = random(1..100)
  if roll <= 5:  → _trigger_resentment_llm_event()   # 5% LLM 心魔试炼
  elif roll <= 15: → _trigger_resentment_local_event() # 10% 本地血红日志
  else: → 原有本地日常逻辑
```

`_fetch_random_karma()` 改为：优先从 Redis `SRANDMEMBER dead:resentment:set` 取值，fallback 到 MySQL `SELECT * FROM dead_registry ORDER BY RAND() LIMIT 1`。

### 4.6 M2 文件变更清单

**后端新建（10 个）：**

| 文件 | 职责 |
|------|------|
| `server/interface/ws.py` | WebSocket 路由 + 连接管理 + 每连接 tick loop |
| `server/interface/app.py` | FastAPI 应用工厂 + 生命周期 |
| `server/infrastructure/db.py` | SQLAlchemy async engine + session |
| `server/infrastructure/redis.py` | Redis 连接池封装 |
| `server/infrastructure/models.py` | SQLAlchemy ORM 五表定义 |
| `server/infrastructure/storage.py` | Repository 抽象层（GameRepository, DeadRegistryRepository） |
| `server/infrastructure/shared_state.py` | 全服单例：DeadRegistryManager + ImmortalHallManager |
| `server/infrastructure/karma_pool.py` | 怨念池清洗/评分/抽取逻辑 |
| `server/tests/conftest.py` | pytest fixtures（DB/Redis mock） |
| `server/tests/test_ws.py` | WebSocket 集成测试（5 并发 + 断线重连） |

**后端修改（5 个）：**

| 文件 | 变更 |
|------|------|
| `server/application/game_engine.py` | 注入 SharedState；怨念判定路由；写回钩子 |
| `server/domain/player.py` | 新增 `ActiveSession` Pydantic 模型 |
| `server/config.py` | 新增 MySQL/Redis 配置 |
| `server/requirements.txt` | 激活 fastapi/uvicorn/sqlalchemy/redis/aiomysql |
| `server/main.py` | 增加 uvicorn 启动路径 |

**前端新建 — Phase 2A'（15 个）：**

| 文件 | 职责 |
|------|------|
| `client/app.ts` | 应用入口：WsManager 初始化 + 全局 player_id 管理 |
| `client/app.json` | 页面注册 + window 修仙暗黑风配置 |
| `client/app.wxss` | 全局样式变量（暗黑修仙主题） |
| `client/project.config.json` | 微信开发者工具项目配置 |
| `client/utils/ws.ts` | WebSocket 单例管理器（connect/send/心跳/重连） |
| `client/utils/actions.ts` | Action Frame 常量（与后端 Action class 一致） |
| `client/pages/game/game.ts` | 挂机页面主逻辑：WS 消息路由 + setData |
| `client/pages/game/game.wxml` | 模板：状态栏 + 日志滚动区 + 选项按钮 + 故事区 |
| `client/pages/game/game.wxss` | 挂机页面样式 |
| `client/pages/shop/shop.ts` + `.wxml` + `.wxss` | 局外黑市占位（Phase 2A' 不实现业务逻辑） |
| `client/pages/hall/hall.ts` + `.wxml` + `.wxss` | 名人堂占位（Phase 2A' 不实现业务逻辑） |

### 4.7 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| Redis 不可用 | Tick 直接写内存 PlayerState，重大事件同步写 MySQL，跳过 Redis |
| 多玩家并发 LLM 调用超 API 速率限制 | `LLMOrchestrator` 层加 `asyncio.Semaphore(3)` 限制并发 |
| AWAIT_DECISION 阶段断线重连 | `active_session` 保存 `trigger_json`，重连时检查超时，未超时则重推 trigger |
| 怨念池清洗任务重复执行 | Redis `SETNX` 分布式锁 + `SRANDMEMBER` 天然去重 |
| WebSocket 连接泄漏 | `finally` 块确保 tick task cancel + Redis session 清理 |

### 4.8 实现优先级

1. **Phase 2A — 网络层骨架：** `app.py` + `ws.py` + 基本的 WebSocket 连接管理 + tick loop（沿用 M1 内存存储）
2. **Phase 2A' — 小程序骨架：** `client/` 项目脚手架 + `utils/ws.ts` 单例 + game 页面基础布局 + WS 联调（与后端 Phase 2A 联动验证）
3. **Phase 2B — 持久化层：✅ 完成** `db.py` + `models.py` + `redis.py` + `storage.py`（五表建表 + 读写）
4. **Phase 2C — 全服怨念池：✅ 完成** `shared_state.py` + `karma_pool.py`（怨念抽取、清洗定时任务）
5. **Phase 2D — GameEngine 改造：** 注入 SharedState + 怨念路由集成 + 断线重连 + 超时处理
6. **Phase 2E — 测试与并发验证：** `test_ws.py`（5 并发 + 重连恢复）

---

### 4.10 Phase 2B 实施记录

> 完成日期：2026-05-21 | 实施人：Claude Code | 测试：212 passed

#### 新建文件

| 文件 | 说明 |
|------|------|
| `server/infrastructure/db.py` | SQLAlchemy 2.0 async engine（aiomysql 驱动）+ async_sessionmaker，懒加载模式 |
| `server/infrastructure/models.py` | 五表 ORM：PlayerAccountModel / DeadRegistryModel / ImmortalHallModel / ActiveSessionModel / HeavenOverlordPoolModel |
| `server/infrastructure/redis.py` | Redis 异步连接池 + player:session Hash / dead:resentment Set+List / 分布式锁 |
| `server/infrastructure/storage.py` | 5 个子 Repository + GameRepository 聚合入口，ORM→Domain 映射 |

#### 修改文件

| 文件 | 变更 |
|------|------|
| `server/config.py` | 新增 mysql_* / redis_* / karma_pool_* / session_flush_interval 配置 |
| `server/requirements.txt` | 激活 sqlalchemy / aiomysql / redis / structlog |
| `server/domain/player.py` | 新增 ActiveSession Pydantic 模型（session_json + stage + trigger_json） |

#### 设计决策

- **懒加载引擎**：`get_engine()` 首次调用时才创建连接池，避免导入时数据库不可用就崩溃
- **怨念候选原子清空**：`pop_resentment_candidates()` 使用 RENAME→LRANGE→DEL 三连避免并发写入丢失
- **聚合仓储**：`GameRepository` 统一持有 5 个子仓储 + RedisClient，简化上层依赖注入
- **ActiveSession.stage** 存储状态机阶段字符串，供 Phase 2D 断线重连判断使用

---

### 4.11 Phase 2C 实施记录

> 完成日期：2026-05-21 | 实施人：Claude Code | 测试：212 passed

#### 新建文件

| 文件 | 说明 |
|------|------|
| `server/infrastructure/shared_state.py` | 全服共享状态单例：DeadRegistryManager（死亡因果池读写 + Redis 怨念推送）+ ImmortalHallManager（飞升名人堂读写） |
| `server/infrastructure/karma_pool.py` | 怨念池管理器：死因精品评分函数 score_dead_title() + KarmaPoolManager（清洗/评分/Redis Set 注入/分布式锁防重） |

#### 设计决策

- **死因精品评分算法**：三维评分 —— 长度（5-80 字符最佳）+ 高价值修仙关键词（+15，如天谴/神罚/飞升）+ 趣味词（+5，如骚话/翻车/作死），满分 100
- **怨念池清洗流程**：分布式锁 → RENAME 原子弹出 Redis candidates → 合并 MySQL unselected → 评分取 top 250 → 替换 Redis Set → 标记 MySQL is_selected → 释放锁
- **DeadRegistryManager 与 GameEngine 解耦**：从 GameEngine 实例级 list 提升为全服单例，Phase 2D 通过构造函数依赖注入获取引用
- **random_karma() 双轨 fallback**：优先 Redis SRANDMEMBER（精品缓存），miss 时 fallback 到 MySQL ORDER BY RAND()

---

### 4.9 微信小程序前端需求分析

> 分析日期：2026-05-21 | 分析人：Claude Code | 代码基线：Phase 2A 完成（WebSocket 后端可用）

#### 4.9.1 小程序项目结构设计

```
client/
├── app.ts                  # 应用入口：全局数据、WS 初始化
├── app.json                # 页面路由注册 + window 配置
├── app.wxss                # 全局样式（修仙暗黑风）
├── project.config.json     # 微信开发者工具配置
├── tsconfig.json           # TypeScript 编译配置
├── typings/                # 微信小程序 API 类型声明
├── utils/
│   ├── ws.ts               # WebSocket 单例管理器
│   └── actions.ts          # Action Frame 常量（与后端 Action class 保持一致）
├── pages/
│   ├── game/
│   │   ├── game.ts         # 挂机主逻辑：WS 消息路由 → setData → 渲染
│   │   ├── game.wxml       # 模板：状态栏 + 日志区 + 选项按钮 + 故事展示
│   │   ├── game.wxss       # 样式
│   │   └── game.json       # 页面配置
│   ├── shop/
│   │   ├── shop.ts         # 局外黑市（Phase 2A' 仅占位）
│   │   ├── shop.wxml
│   │   └── shop.wxss
│   └── hall/
│       ├── hall.ts         # 名人堂（Phase 2A' 仅占位）
│       ├── hall.wxml
│       └── hall.wxss
```

**决策：** 使用微信原生框架（非 uni-app/Taro），语言选 TypeScript，保持与后端 Python 类型安全一致的技术理念。shop 和 hall 页面 Phase 2A' 仅创建占位骨架，不实现业务逻辑。

#### 4.9.2 WebSocket 单例设计（utils/ws.ts）

**核心职责：**
- 全局唯一 `wx.connectSocket` 实例，避免多页面重复连接
- 提供 `send(action, data)` 方法，自动 JSON 序列化
- 提供 `onMessage(callback)` 注册消息监听，支持多个回调
- 自动心跳：每 30s 发送 `CS_PING`
- 断线重连：指数退避（1s → 2s → 4s → 8s → max 16s）

**生命周期管理：**

| 事件 | 行为 |
|------|------|
| `App.onLaunch` | 初始化 WsManager 单例（不立即连接） |
| `game.onLoad` | `ws.connect(playerId)` → 发送 `CS_START_GAME` |
| `game.onUnload` | 不关闭 WS（保持后台挂机），仅解绑页面回调 |
| `App.onHide` | 继续维持 WS（后台挂机） |
| `App.onShow` | 若 WS 已断则重连 + 重推状态 |
| `App.onError` | 记录错误，尝试重连 |

**单例模式关键代码结构：**
```typescript
interface WsCallback {
  (action: string, data: Record<string, any>): void;
}

class WsManager {
  private _socket: WechatMiniprogram.SocketTask | null = null;
  private _listeners: WsCallback[] = [];
  private _reconnectAttempts: number = 0;
  private _heartbeatTimer: number | null = null;
  private _url: string = '';

  connect(playerId: string): void { /* wx.connectSocket + 注册 onOpen/onMessage/onClose/onError */ }
  send(action: string, data: Record<string, any>): void { /* wx.send({ data: JSON.stringify({action, ...data}) }) */ }
  onMessage(cb: WsCallback): () => void { /* 注册回调，返回 unsubscribe 函数 */ }
  private _onMessage(raw: WechatMiniprogram.SocketMessage): void { /* 解析 action，分发给所有回调 */ }
  private _startHeartbeat(): void { /* setInterval → CS_PING */ }
  private _reconnect(): void { /* 指数退避重连 */ }
  close(): void { /* 清理 timer + socket */ }
}
```

#### 4.9.3 Game 页面状态机

Game 页面根据后端下行帧切换 UI 状态，与后端 Stage 状态机形成镜像：

| 后端 Stage | 前端 UI 状态 | 显示内容 |
|------------|-------------|----------|
| `INIT` | `connecting` | 「连接中...」加载动画 |
| `IDLE` | `idle` | 状态栏（境界/修为/天谴/气运/根基）+ 滚动日志 |
| `EVENT_TRIGGER` | `await_decision` | 事件弹窗（天道人格/事件描述/因果提示）+ A/B/C 按钮 |
| `LLM_PROCESSING` | `streaming` | 打字机效果区域，逐字累积 `SC_STORY_STREAM` 的 chunk |
| `SETTLEMENT` | `settlement` | 结算面板（属性变化/死因/天道点） |
| `GAME_OVER` | `game_over` | 最终结算（存活时间/死因/天道点）+ 「再来一局」按钮 |

**关键交互：**
- IDLE 状态下点击「手动对线」→ 发送自定义骚话（强制触发 C 选项）
- EVENT_TRIGGER 状态下按钮 A/B 直接发送 `CS_PLAYER_DECISION`
- 按钮 C → 弹出 `<input>` 框，确认后发送 `CS_PLAYER_DECISION`（choice_id: "C", custom_text: 用户输入）
- 60s 倒计时显示（后端 `decision_timeout`），超时自动选 A

#### 4.9.4 Action Frame 协议前端映射

**上行帧构造（utils/ws.ts send 封装）：**

```typescript
// CS_START_GAME
ws.send('CS_START_GAME', { player_name: '张大仙' });

// CS_PING（自动心跳，无需手动调用）
ws.send('CS_PING', {});

// CS_PLAYER_DECISION
ws.send('CS_PLAYER_DECISION', { choice_id: 'B', custom_text: '' });
// 或自定义骚话：
ws.send('CS_PLAYER_DECISION', { choice_id: 'C', custom_text: '天道老儿你算什么东西！' });
```

**下行帧处理（game.ts onMessage 路由）：**

| Action | 处理逻辑 |
|--------|---------|
| `SC_GAME_LOG` | 更新状态栏数据 + 日志文本追加到 `logs[]` 数组 |
| `SC_HEAVEN_EVENT_TRIGGER` | 切换到 `await_decision` UI，显示 trigger 信息 + A/B/C 按钮 |
| `SC_STORY_STREAM` | `storyText += chunk` → setData → scroll-view 自动滚动到底部；`is_last=true` 时关闭打字机光标 |
| `SC_EVENT_SETTLEMENT` | 切换到 settlement UI，展示完整故事 + 属性变化 + 天道点 |
| `SC_PONG` | 更新最后心跳时间戳 |
| `SC_ERROR` | toast 提示错误信息 |

#### 4.9.5 setData 性能优化

`SC_STORY_STREAM` 以每字符一帧的频率高频推送（DeepSeek 流式输出可达 30-50 tokens/s），若每 chunk 都调用 `setData()` 会导致渲染卡顿和电量消耗。

**优化策略：**
- **帧合并：** 每 80ms 批量合并待发送的 chunk，一次性 `setData({ storyText: accumulated })`
- **滚动优化：** 使用 `scroll-top` 属性而非每次重新渲染整个 scroll-view
- **日志截断：** `logs[]` 数组最多保留 200 条，超出时 shift() 旧条目
- **状态栏节流：** 状态栏数据（cultivation/sin/luck）每 1s 最多更新一次

#### 4.9.6 与 Phase 2A 后端的集成点

| 集成点 | 后端（已完成） | 前端（Phase 2A'） |
|--------|--------------|-------------------|
| WS 连接端点 | `ws://host:8000/ws/game?player_id=xxx` | `wx.connectSocket({ url })` |
| player_id 生成 | 后端支持 `?player_id=` 参数，空则返回错误 | 前端 `wx.getStorageSync('player_id')` 或首次生成 UUID |
| Action Frame 常量 | `server/interface/ws.py:Action` class | `client/utils/actions.ts` 字面量常量 |
| 流式 chunk 接收 | `SC_STORY_STREAM` 每 char 一帧 | `onMessage` → 80ms 批量合并 → setData |
| 心跳 | 后端无主动心跳检测 | 前端每 30s 发 `CS_PING`，后端回复 `SC_PONG` |

**联调前提：** Phase 2A 后端已在 `--server` 模式运行。微信开发者工具需勾选「不校验合法域名」以连接本地 `ws://` 地址（生产环境需 `wss://` + 已备案域名）。

#### 4.9.7 客户端文件清单（Phase 2A' 新建 17 个）

| 文件 | 职责 |
|------|------|
| `client/app.ts` | 应用入口：WsManager 初始化 + 全局 player_id 管理 |
| `client/app.json` | 页面注册 + window 风格配置 |
| `client/app.wxss` | 全局修仙暗黑风样式变量 |
| `client/project.config.json` | 微信开发者工具项目配置 |
| `client/tsconfig.json` | TypeScript 编译配置（target/strict/paths） |
| `client/typings/wx.d.ts` | 微信小程序 API 类型声明补充 |
| `client/utils/ws.ts` | WebSocket 单例管理器 |
| `client/utils/actions.ts` | Action Frame 常量定义 |
| `client/pages/game/game.ts` | 挂机页面主逻辑 |
| `client/pages/game/game.wxml` | 挂机页面模板 |
| `client/pages/game/game.wxss` | 挂机页面样式 |
| `client/pages/shop/shop.ts` + `.wxml` + `.wxss` | 黑市占位页面 |
| `client/pages/hall/hall.ts` + `.wxml` + `.wxss` | 名人堂占位页面 |

#### 4.9.8 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 微信开发者工具 WebSocket 调试困难 | 在 `ws.ts` 中内置日志开关（`DEBUG=true`），所有收发帧打印到 Console |
| 小程序后台挂机被系统杀死 | `App.onShow` 重连后发送 `CS_START_GAME`（携带相同 player_id），后端 Phase 2D 将支持断线重连恢复状态 |
| `setData` 高频调用导致页面卡顿 | 80ms 帧合并 + 状态栏 1s 节流 |
| `wx.connectSocket` 最大连接数限制（5 个） | 单例模式天然保证全局只有 1 个连接 |
| 本地开发 `ws://` 非加密连接 | 开发者工具勾选「不校验合法域名」；生产环境使用 `wss://` |
| 用户 device 字体不支持生僻字 | 使用系统默认字体，避免引入自定义字体文件 |
