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

### 2.2 数据持久化与三级缓存（infrastructure/storage）

- **MySQL 表结构建设：** 落地 player_account、dead_registry、immortal_hall、active_session、heaven_overlord_pool 五张核心表。
- **Redis 缓存提速：** 玩家每 10 秒 Tick 产生的灵石/修为/天谴变动，直接写入 Redis Hash（player:session:{player_id}）。
- **异步写回：** 后端每 30 秒或玩家触发重大状态变动（突破/对线结束）时，触发异步 Task 将 Redis 的快照快写入 MySQL active_session 表中，拒绝高频高并发 I/O。

### 2.3 弱联机"怨念残留"池（全服踩雷）

完美落实上一轮审查的 PRD 逻辑：

- 玩家暴毙满足门槛后，写入 heaven_overlord_pool 并定时每 10 分钟清洗 250 条精品死因到 Redis 怨念 Set 中。
- 修改日常 Tick 路由，使其有 10% 的概率抽取全服玩家怨念转换为【本地血红日志】或 5% 的概率转为【大模型心魔试炼】。

## 3. 交付物与验收标准

- **交付物：** 部署在 Linux 测试环境的 FastAPI 异步后端，+ 支持真机调试的基础小程序代码。
- **验收标准：** 启动 5 个测试脚本并发连接 WebSocket，挂机数值能高频刷新，输入骚话后能收到流式逐字喷出的故事，关闭脚本再重连能恢复状态。
