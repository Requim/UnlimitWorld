# Milestone 4：Roguelike 路线地图

> 当前进度以 [PROJECT_STATUS.md](PROJECT_STATUS.md) 为唯一事实源。本文档记录 M4 路线地图的需求分析、实施决策、验证结果和遗留风险。

## 0. 当前进度快照

- **当前阶段：** M4-1 已完成；M4 路线体验补强已补入终章续图提示与全局路线图 UI。
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
- 终章路线耗尽不改变自动续图策略，只通过一次性 `route_notice / route_notice_level` 强化“此卷已尽、再开一卷”的引导。
- 小程序路线图展示 1-6 境界总览，当前境界展开节点，其余境界压缩展示，避免玩家误以为只有一个阶段。

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

### 2.2 M4 路线终章续图提示补强

> 实施日期：2026-06-13 | 实施人：Codex | 范围：路线耗尽提示、WebSocket 字段、小程序展示、定向测试

已完成：

- `RunMap` 快照新增 `route_notice / route_notice_level`，用于携带路线续卷或终章回响提示；玩家选择新节点后自动清空。
- `GameEngine` 在路线耗尽并自动刷新地图时写入一次性提示：普通章节为“路线续卷”，第 6 章耗尽为“终章回响”。
- `SC_GAME_LOG` 同步下发路线提示字段，`SC_RUN_MAP` 快照保留提示，前端主动刷新地图时不会丢失提示。
- 小程序 `game` 页面在路线盘下方渲染紧凑提示条，并按 `finale` 等级使用更醒目的终章样式。
- 前端日志状态拼装拆分为 `buildRunStats / buildRouteNoticeState / buildPhase3kState`，避免 `_onGameLog` 继续膨胀。

验证结果：

- `python -m pytest server\tests\test_run_map.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`：67 passed, 34 skipped；当前环境未安装 `pytest-asyncio`，既有 async 单测仍跳过，本次新增的终章续图断言已改为同步执行。
- `python -m compileall server -q`：通过
- `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 与 `baseUrl` 弃用）

### 2.3 M4 全局路线图与国风暗卷 UI 补强

> 实施日期：2026-06-14 | 实施人：Codex | 范围：挂机页全局路线展示、信息层级重排、国风暗卷视觉

已完成：

- 小程序 `game` 页新增 `RunMapStageView` 视图模型，把后端已下发的 1-6 境界 `chapters` 转成六境阶段条、当前境界展开节点、其他境界压缩预览。
- 挂机页 idle 结构重排为“执念薄横幅 / 全局命途盘 / 最近遭遇 / 修行手札”，移除挂机大修士动画对首屏空间的占用。
- 视觉改为原创国风暗卷方向：暗色山水背景、铜金/朱砂/青玉节点状态、符牌式节点和命盘式阶段条；不引入外部素材或复刻特定游戏 UI。
- 后端 `SC_RUN_MAP / CS_CHOOSE_MAP_NODE` 协议保持不变，路线玩法规则仍是一次只选择当前可用节点。

验证结果：

- `git diff --check -- client\pages\game\game.ts client\pages\game\game.wxml client\pages\game\game.wxss`：通过
- `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 与 `baseUrl` 弃用）

## 3. 遗留风险

- 微信开发者工具真机需要验证全局路线图在小屏上不挤压日志，且六境阶段条文字不溢出。
- 目前黑市节点只做轻补给，后续若要接入局内商品，需要单独设计局内经济边界。
- 终章路线耗尽已补固定提示，但仍采用刷新当前境界地图的保守降级；后续若要更强仪式感，可设计固定天道节点或终局引导。
