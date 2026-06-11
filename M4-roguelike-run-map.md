# Milestone 4：Roguelike 路线地图

> 当前进度以 [PROJECT_STATUS.md](PROJECT_STATUS.md) 为唯一事实源。本文档记录 M4 路线地图的需求分析、实施决策、验证结果和遗留风险。

## 0. 当前进度快照

- **当前阶段：** M4-1 已完成。
- **阶段目标：** 把每局游戏扩展为三路节点地图，让玩家在关键节点选择修炼路线。
- **验收状态：** 后端模型、WebSocket 协议、前端三路地图和定向测试已完成。

## 1. 需求分析记录

### 1.1 目标

- 保留现有“挂机修仙 + 天道对线 + 飞升 / 暴毙”主循环。
- 新增每局一张 roguelike 路线图，每个境界按三路、3-5 层节点推进。
- 首版节点类型限定为修炼、诱惑、赌命、黑市、天道、因果回声、休整。
- 普通节点复用 `normal_pools`，节点只决定事件池、风险倍率、奖励倍率和路线统计。

### 1.2 边界

- 不新增回合战斗、装备词条、敌人 AI 或 Boss 战。
- 不把普通节点升级为 `AWAIT_DECISION` 长流程。
- 黑市节点首版只做局内轻补给，不改局外账号经济。
- LLM 仍只处理天道、突破、天谴满、飞升等关键裁决。

### 1.3 关键决策

- `RunMap` 挂在 `PlayerState` 上，沿用现有 `to_dict/from_dict` 断线重连链路。
- `SC_RUN_MAP` 负责同步整张地图快照，`CS_CHOOSE_MAP_NODE` 负责选择当前可用节点。
- `SC_GAME_LOG` 增加 `node_id / node_type / route_label`，与 3K 字段一起作为局内展示元数据。
- 前端采用紧凑三列路线盘，放在挂机页内，不遮挡属性栏、执念和日志。
- 路线耗尽时为玩家当前境界刷新一张新地图，继续要求玩家选路，避免终章或异常状态卡死。

## 2. 实施记录

### 2.1 M4-1 路线地图最小闭环

> 实施日期：2026-06-11 | 实施人：Codex | 范围：RunMap 模型、节点推进、WebSocket 协议、小程序路线图、测试覆盖

已完成：

- 新增 `server/domain/run_map.py`，提供 `RunMap`、`RunMapNode`、地图生成、选节点、完成节点和前端快照。
- `GameEngine.new_game()` 开局生成地图；`tick()` 在未选节点时等待路线选择，选中节点后按节点事件池推进。
- 当地图没有当前节点且没有可选节点时，后端会自动为当前境界重开路线选择。
- 本地事件生成支持 `preferred_pool / reward_multiplier / risk_multiplier`，复用 3K `normal_pools`。
- `server/interface/ws.py` 新增 `SC_RUN_MAP / CS_CHOOSE_MAP_NODE`，开局、选节点、tick 和结算后同步地图。
- 小程序 `game` 页面新增三路节点图，展示可选、当前、已走、锁定节点，并发送选节点帧。
- 测试覆盖地图生成、节点推进、事件池复用、WebSocket 字段契约和核心回归。

验证结果：

- `python -m pytest server\tests\test_run_map.py server\tests\test_event_config.py server\tests\test_game_engine.py -q`：109 passed
- `python -m pytest server\tests\test_e2e_ws.py -q`：30 passed
- `python -m compileall server -q`：通过
- `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 与 `baseUrl` 弃用）

## 3. 遗留风险

- 微信开发者工具真机需要验证三路节点图在小屏上不挤压日志。
- 目前黑市节点只做轻补给，后续若要接入局内商品，需要单独设计局内经济边界。
- 终章路线耗尽目前采用刷新当前境界地图的保守降级；后续可增加终章提示或固定天道节点来强化仪式感。
