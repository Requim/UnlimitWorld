# 天道不正经 —— 大模型因果沙盒修仙肉鸽小程序

> **USP**：拒绝固定剧本。利用大模型（LLM）实现"千人千面"的无限流修仙剧情；允许玩家通过自定义文本与天道"骚话对线"；通过全服"死亡因果池"实现弱联机跨时空背刺。

---

## 一、核心玩法与情感定位

### 底层心理学逻辑

这款游戏能火的底层逻辑是 **"压力释放"** 与 **"黑天鹅喜剧"**。

| 传统修仙 | 你的修仙 |
|---------|---------|
| 唯唯诺诺、一键日常、机械囤资源（上班式坐牢） | 疯狂作死、当面骂天道、突发性暴毙（赌徒式狂欢） |

### 真正的"肉鸽"内核

传统修仙游戏的"随机"只是换个地图、刷个颜色。而你的游戏，**玩家玩的不是"变强"，玩的是"探索死亡的边界"**。大模型赋予了死因无限的文学可能性（被雷劈死、被自己吹的牛皮撑死、和天道对骂被降维打击），每一次暴毙都像开盲盒。

### 极致的文字发泄口

"输入骚话"是绝妙的设计。现在的年轻玩家极度反感游戏里当"跑腿工具人"。允许玩家输入骚话，就是允许玩家把对现实、对老板、对生活的满腔怨气，借由"修士"之口狠狠地砸向"天道"。

### 黑喜剧色彩

三次方暴毙公式和无条件天谴杀，意味着游戏"极其不公平且充满恶意"。但这种恶意因为大模型的荒诞幽默和局外商店的"功德洗白"，变成了可以自我解嘲的喜剧，非但不会让玩家劝退，反而会激发"老子下一把一定要卡出神级 Bug"的逆反心理。

---

## 二、核心循环

```
[局外：天道契约/天赋抽卡] ──(继承属性)──> [局内：修为挂机驱动]
       ▲                                         │
       │                                       (触发)
(结算天道点重开)                                  ▼
  [局外：身死道消/成仙夺舍] <───(暴毙判定)─── [天道对线事件(LLM)]
                                                 ▲
                                                 │ (引入)
                                        [全服前世因果/怨气池]
```

---

## 三、核心数值与属性系统

| 属性 | 范围 | 说明 |
|------|------|------|
| 修为/境界 (Cultivation/Realm) | 7 境界 | 挂机自动上涨，决定基础数据和劫难门槛 |
| 气运 (Luck) | 0-100 | 隐藏属性，越高 LLM 好事件概率越高 |
| 根基 (Foundation) | 0-100 | 硬实力，对抗暴毙的防御属性 |
| 天谴值 (Sin) | 0-S_max | 核心爽点，越高 LLM 敌意和暴毙率越高 |

### 境界表

| 境界 | realm_code | 修为范围 | 产出(修为/秒) | 基础暴毙率 | 天谴上限 | 核心机制 |
|------|-----------|---------|-------------|-----------|---------|---------|
| 练气期 | 1 | 100→1,000 | +1~5 | 5% | 50 | 极易暴毙，骚话最容易糊弄 |
| 筑基期 | 2 | 2,000→8,000 | +10~20 | 15% | 60 | 初涉因果，突破时面临天雷化劫 |
| 金丹期 | 3 | 1.5W→5W | +50~100 | 25% | 70 | 我命由我不由天，本命金丹淬炼 |
| 元婴期 | 4 | 10W→40W | +200~500 | 40% | 80 | 元婴出窍/夺舍危机，心魔入侵 |
| 化神期 | 5 | 100W→500W | +1000~3000 | 60% | 90 | 掌控天地法则，可解锁融入天道 |
| 渡劫期 | 6 | 1000W→5000W | +1W~3W | 85% | 100 | 80%事件路由LLM，死亡可融入天道 |
| 大乘期 | 7 | - | - | - | - | 飞升通关，永留仙尊名人堂 |

### 暴毙公式

$$P_{final} = P_{base} + (1 - P_{base}) \times \left( \frac{S_{current}}{S_{max}} \right)^{\alpha \times \beta(F)}$$

- $\alpha = 3$ （天谴惩罚指数）
- $\beta(F) = 1 + \frac{F}{100}$ （根基缓释因子）
- **后端用公式算 `is_dead`，LLM 只负责编故事解释生死**
- **$S_{current} \ge S_{max}$ 时强制死亡，不依赖浮点运算**

---

## 四、双轨制事件驱动

| 轨道 | 发生率 | 触发方式 | 说明 |
|------|--------|---------|------|
| 本地普通轨道 | ~95% | 每 10s tick，PRD 判定 | Config_Normal_Events.json，零 API 成本 |
| 天道因果轨道 | ~5% | PRD ≥ 80 / 大境界突破 / 天谴满 100 | 调用 DeepSeek，异步推演 |

### PRD 参数
- 每 tick 累加 random(2-12)
- **动态阈值（按境界）**：练气:60, 筑基:70, 金丹:85, 元婴:100, 化神:110, 渡劫:120, 大乘:999
- 优先级链：飞升 > 天谴满 > PRD ≥ 境界阈值 > 大境界突破 > 本地日常
- PRD 作为"命运拦截器"优先于突破，防止突破必定触发 LLM 的设计死锁

---

## 五、天道人格系统（4 大 LLM System Prompt）

| 人格 | 风格 | 行为特征 |
|------|------|---------|
| 太上忘情 | 高冷文言 | 严格数值逻辑，冰冷仙气 |
| 混沌乐子人 | 荒诞网感 | 看玩家吃瘪，极度无厘头 |
| 唯爱护短 | 爽文宠溺 | 嘴甜有礼即给神级奖励 |
| 天道夺舍·恶意化身 | 高玩代行 | 高玩意志介入折磨低阶萌新（M3） |

---

## 六、LLM 输出契约

- **后端 → LLM**：PlayerContext（含天道人格 Prompt、玩家状态、历史因果、玩家骚话）
- **LLM → 后端**：强制 JSON，Pydantic 校验
  ```json
  {
    "event_title": "...",
    "story_text": "...",
    "is_dead": false,
    "attribute_changes": {"cultivation": 0, "sin_value": 0, "luck": 0, "foundation": 0},
    "next_action_required": "IDLE"
  }
  ```
- **容错**：修复重试 ×2（Pydantic 报错喂回 Prompt）→ 降级兜底（本地规则引擎）

---

## 七、七阶段状态机

```
[0: INIT] → [1: IDLE] → [2: EVENT_TRIGGER] → [3: AWAIT_DECISION]
                                                    ↓
[6: GAME_OVER] ← [5: SETTLEMENT] ← [4: LLM_PROCESSING]
       ↓
  结算天道点 → 写入因果池/名人堂 → 回到局外
```

- **只能前向转换**，不可逆退
- 60s 对线超时：自动选 A + 扣除当前修为 10%（道心蒙尘）
- 因果遮蔽卡：后端拦截 `is_dead=true`，推送固定拯救文案
- 飞升：修为满 5000W 时强行阻断挂机，触发终极大考

---

## 八、商业模式与数值杠杆

作为一款挂机微信小程序，它具有"开发成本极低、变现效率极高"的典型买量型/裂变型游戏特征。

### 核心变现出口（天道点与资源饥饿）

游戏通过高频、不可控的暴毙，高频切入"局外结算"。这就是内购或广告的黄金交叉点：

**广告变现（IAA）：**
- 突破失败、天谴值满 100 准备吃席时 → 观看 15 秒视频广告，获得【天道因果遮蔽卡】，原地锁血复活
- 开局前 → 观看广告免费赠送【功德洗白券】，降低 20 点初始天谴

**内购变现（IAP）：**
- 直接售卖永久卡、免广告特权
- 购买纯数值层面的"根基加成"（提升 $F$ 值，硬抗天谴）
- 局外商店直接售卖各种骚气十足的"特殊称号/开局天赋"（例如：自带【重度耳聋协议】开局）

### ROI 的致命优势

文字挂机没有美术成本、没有 3D 渲染，前端组件树简单到爆。唯一的成本是 DeepSeek 的 API 费用。

**成本账：** 按照目前 DeepSeek 的价格，每次大模型对线消耗几百个 Token，成本不到 0.001 元人民币。而玩家看一个激励视频广告，开发者能拿到的分成远超这个数字。

**结论：** 只要用户留存及格，该项目的 QPS 账单和广告收益之间存在巨大的利差，稳赚不赔。

---

## 九、运营与社交自传播

文字游戏最怕默默无闻，但大模型让它天然具备"社交货币"属性。

### 仙尊名人堂与死因大观园（社交裂变核心）

当玩家触发精彩的、极具戏剧性的暴毙事件时，前端组件 `pages/hall/hall` 提供"一键生成朋友圈/抖音分享战报图"功能。

截图内容示例：
> "修士 [张大锤]，因对天道高喊'给本尊倒洗脚水'，触发三次方天谴公式，被天道用九霄赛博神雷将神魂打入区块链，当场暴毙。继承天道点：+150。"

这种极具反差感和沙雕味的图文，在微信群、贴吧、小红书上具有恐怖的病毒式自传播能力。

### 玩家骚话的"反向反哺"

上一把通关或高分暴毙玩家的骚话，会被后端清洗后变成下一把其他玩家挂机时的"世界随机事件"。例如：

> "你路过乱葬岗，发现前代仙尊 [张大锤] 的神魂正在一边斗地主一边骂天道……"

这种打破第四面墙的互动，让社区活跃度爆炸。数据表 `heaven_overlord_pool`（全服死因/天道霸主池）承载此机制。

---

## 十、落地核心风险与防线

在项目从 M1 CLI 向 M2/M3 推进时，有三个关键风险需要技术和产品打好配合：

### 大模型文案的内容合规（政治、色情、暴力）

- **风险：** 玩家一定会输入各种敏感词或政治段子来测试大模型的底线，一旦被微信查到，小程序直接封杀。
- **防线：** 在将玩家输入的"骚话"喂给 DeepSeek 之前，国内端必须前置过一遍敏感词过滤系统（微信官方内容安全接口服务 SecCheck）。对于违规内容，不触发 LLM，直接触发本地搞笑惩罚事件：
  > "由于你满嘴喷粪，天道对你使出了禁言术，并扣除 50 点功德。"

### 大模型的响应延迟（流式打字机视觉拯救）

- **风险：** 大模型思考通常需要 1-2 秒，如果网络抖动，卡顿会让挂机游戏的流畅感顿失。
- **防线：** 利用单例 WebSocket、打字机动画（setInterval）和微信原生的 `wx.vibrateShort()` 手机微震动。在等待 LLM 吐字的 1 秒内，屏幕全屏红光闪烁，手机高频微震，给玩家营造一种"天道正在蓄力憋大招、空间正在撕裂"的紧张视觉特效，用视觉和触觉动效完美掩盖网络延迟。

---

## 十一、WebSocket Action Frame 协议（M2 ✅）

全部 7 种消息类型已实现并测试通过：

**上行（Client → Server）**
| Action | 说明 |
|--------|------|
| `CS_START_GAME` | 开局，携带 player_name |
| `CS_PING` | 心跳保活 |
| `CS_PLAYER_DECISION` | 玩家对线决策（choice_id + custom_text） |

**下行（Server → Client）**
| Action | 说明 |
|--------|------|
| `SC_GAME_LOG` | 日常挂机日志 + 状态快照（cultivation/sin/luck/foundation/realm/sin_phase） |
| `SC_HEAVEN_EVENT_TRIGGER` | 天道事件触发（fixed_options、karma_brief、heaven_persona） |
| `SC_STORY_STREAM` | LLM 流式推送 chunk（is_last 标志收尾） |
| `SC_EVENT_SETTLEMENT` | 事件结算（settlement 含 dead_title/story_text/heaven_points_earned） |
| `SC_PONG` | 心跳响应 |
| `SC_ERROR` | 错误信息 |

**前端优化：** STORY_STREAM 80ms 帧合并、状态栏 1s 节流、日志上限 200 条

---

## 十二、数据库 Schema（M2 — Phase 2B ✅）

5 张表 ORM 定义完成：`player_account` / `dead_registry` / `immortal_hall` / `active_session` / `heaven_overlord_pool`

缓存策略：内存(Dict) → Redis(Hash, Set, List) → MySQL(异步 30s 快照)

Repository 层封装：`PlayerAccountRepository` / `DeadRegistryRepository` / `ImmortalHallRepository` / `ActiveSessionRepository` / `HeavenOverlordPoolRepository` + `GameRepository` 聚合入口

---

## 十三、技术栈

| 层 | 选型 |
|----|------|
| 后端框架 | FastAPI + Pydantic v2 + uvicorn |
| 大模型 | DeepSeek（国内节点，OpenAI 兼容 API） |
| 数据库 | MySQL + Redis（M2 Phase 2B ✅） |
| 前端 | 微信原生小程序 TypeScript（M2 Phase 2A' ✅） |
| 部署 | 腾讯云/阿里云国内节点（M3） |
| 配置管理 | .env + pydantic-settings |
| 测试 | pytest (244 项，含 E2E WebSocket 26 项 + 并发 13 项 + 微信 19 项） |

---

## 十四、项目结构

```
/
├── server/                          # Python 后端
│   ├── config.py                    # 配置管理（pydantic-settings）
│   ├── main.py                      # 入口（--server 启动 WebSocket / 默认 CLI）
│   ├── requirements.txt             # Python 依赖
│   ├── domain/                      # 领域层：纯对象与公式
│   │   ├── __init__.py
│   │   ├── player.py                # 玩家属性、境界、暴毙公式
│   │   └── event.py                 # 事件模型、LLM 契约（EventTrigger/EventSettlement）
│   ├── application/                 # 应用层：状态机编排
│   │   ├── __init__.py
│   │   ├── game_engine.py           # 核心 Tick、7 阶段状态机、事件结算
│   │   └── heaven_persona.py        # 4 大天道人格 Prompt 工厂
│   ├── infrastructure/              # 基础设施层：外部 IO
│   │   ├── __init__.py
│   │   ├── llm_client.py            # DeepSeek 异步流式客户端 + LLMOrchestrator
│   │   ├── event_config.py          # 本地事件加载与三池路由
│   │   ├── db.py                    # SQLAlchemy async engine (aiomysql)
│   │   ├── models.py                # ORM 五表定义
│   │   ├── redis.py                 # Redis 异步连接池 + 怨念池操作
│   │   ├── storage.py               # Repository 层（5 子仓储 + GameRepository 聚合）
│   │   ├── shared_state.py          # 全服单例：DeadRegistryManager + ImmortalHallManager
│   │   └── karma_pool.py            # 怨念池清洗/评分/抽取 + 分布式锁
│   ├── interface/                   # 接口适配器
│   │   ├── __init__.py
│   │   ├── cli.py                   # M1 控制台交互
│   │   ├── app.py                   # FastAPI 应用工厂 + ConnectionManager
│   │   └── ws.py                    # WebSocket 路由 + 每连接 tick loop
│   ├── tests/                       # 测试套件（212 项）
│   │   ├── test_player.py           # 领域层单元测试
│   │   ├── test_game_engine.py      # 引擎单元测试
│   │   ├── test_llm_client.py       # LLM 客户端测试
│   │   ├── test_heaven_persona.py   # 人格系统测试
│   │   ├── test_event_config.py     # 事件配置测试
│   │   ├── test_router.py           # 事件路由测试
│   │   ├── test_integration.py      # 黑盒集成测试
│   │   ├── smoke_test_ws.py         # WebSocket 冒烟测试（4 项）
│   │   └── test_e2e_ws.py           # 端到端测试（26 项）
│   └── data/
│       └── Config_Normal_Events.json
├── client/                          # 微信小程序前端（M2 Phase 2A' ✅）
│   ├── app.ts                       # 入口：WsManager 单例、player_id 生成
│   ├── app.json                     # 页面路由注册
│   ├── app.wxss                     # 全局样式（修仙暗黑主题）
│   ├── utils/
│   │   ├── ws.ts                    # WebSocket 管理器（自动重连+心跳+消息回调）
│   │   └── actions.ts               # Action Frame 常量 + UIState 枚举
│   └── pages/
│       ├── game/                    # 挂机主页面（6 态切换）
│       │   ├── game.ts              # WS 消息路由 + 状态机 + setData 优化
│       │   ├── game.wxml            # 模板：状态栏/日志/事件卡片/流式/结算
│       │   └── game.wxss            # 样式：修仙暗黑主题
│       ├── shop/                    # 商店页面（占位）
│       └── hall/                    # 名人堂页面（占位）
└── README.md
```

---

## 十五、Milestone 开发排期

当前开发进度以 [PROJECT_STATUS.md](PROJECT_STATUS.md) 为准；README 只保留项目介绍与启动说明。

| 里程碑 | 状态 | 说明 |
|--------|------|------|
| M1 核心因果流 | ✅ 已归档 | Python 后端 + CLI 原型闭环 |
| M2 弱联机连接 | ✅ 已归档 | WebSocket + MySQL/Redis + 基础小程序 |
| M3 客户端合流与微信生态 | 🔄 当前 | 已完成到 Phase 3K-2，下一步为 Phase 3L |

---

## 十六、当前进度

请先读取 [PROJECT_STATUS.md](PROJECT_STATUS.md)。该文件维护：
- 当前阶段与下一阶段；
- 已完成 Phase；
- 已知测试风险；
- 后续需求 Backlog；
- 推荐文档读取顺序。

---

## 十七、快速启动

### Docker Compose 一键部署（推荐）

全栈一键启动：FastAPI + MySQL 8.0 + Redis 7，自动建表、健康检查、数据持久化。

```bash
# 1. 配置环境变量（API Key 等）
cp server/.env.example server/.env
# 编辑 server/.env，填入 DEEPSEEK_API_KEY

# 2. 构建并启动所有服务
docker compose up -d

# 3. 查看日志
docker compose logs -f app

# 4. 验证
curl http://localhost:8000/docs
```

**数据持久化：** MySQL 和 Redis 数据通过 Docker Volume 保存在宿主机，`docker compose down` 不会丢失数据。如需彻底清除：

```bash
docker compose down -v
```

**环境变量覆盖：** `docker-compose.yml` 自动将容器内 `MYSQL_HOST=mysql`、`REDIS_HOST=redis` 注入 `server/.env` 之外，无需手动修改数据库连接地址。

**无 API Key 运行：** 不配置 `DEEPSEEK_API_KEY` 时，LLM 调用自动降级为本地 mock 故事生成器，状态机、暴毙公式、事件池仍可完整测试。

---

### 手动启动（开发调试）

**M1 CLI 原型：**

```bash
cd server
pip install -r requirements.txt
cd ..
python -m server.main
```

**M2 WebSocket 服务器：**

```bash
# 先启动 MySQL 和 Redis（可单独 docker compose up mysql redis -d）
cd server
pip install -r requirements.txt
cd ..
python -m server.main --server
# 监听 0.0.0.0:8000，WebSocket 端点 /ws/game?player_id=xxx
```

**仅启动依赖服务（MySQL + Redis），应用在宿主机运行：**

```bash
docker compose up -d mysql redis
cd server && pip install -r requirements.txt
# 修改 server/.env 中 mysql_host=127.0.0.1, redis_host=127.0.0.1
python -m server.main --server
```

---

### 运行测试

```bash
cd server

# 全量测试（212 项）
python -m pytest tests/ -v

# 仅 WebSocket E2E（26 项）
python -m pytest tests/test_e2e_ws.py -v

# WebSocket 冒烟测试（4 项，独立脚本）
python -m tests.smoke_test_ws
```

### 微信小程序

使用微信开发者工具打开 `client/` 目录，修改 `app.ts` 中的 WebSocket 地址指向后端服务器。

---

## 十八、总结

这是一个**产品创意驱动、技术架构解耦、数值控制绝对主权**的降维打击项目。它避开了中小团队去和厂牌硬碰硬拼美术、拼玩法的死路，把所有的弹药都打在了大模型的实时叙事魅力和硬核数值挂机肉鸽的交汇点上。

**一句话评估：立意新颖、成本低廉、变现顺畅、裂变极快。**
