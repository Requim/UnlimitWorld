# Project Status：天道不正经

> 更新时间：2026-06-11  
> 作用：本文件是当前开发进度的唯一入口。Codex 每次进入本项目时，先读本文件，再按需读取 `AGENTS.md` 和当前里程碑文档。

## 当前阶段

- **当前里程碑：** M4 Roguelike 路线地图
- **当前进度：** 已完成到 Phase M4-1
- **下一阶段：** Phase 3L（国内云部署、ICP 备案、微信审核提交）或 M4 后续路线地图体验打磨
- **当前主文档：** [M4-roguelike-run-map.md](M4-roguelike-run-map.md)
- **历史里程碑：**
  - M1 已完成并归档：[M1-core-gameplay.md](M1-core-gameplay.md)
  - M2 已完成并归档：[M2-networking.md](M2-networking.md)
  - M3 已完成到玩法侧 3K-2，部署上架 3L 待继续：[M3-client-launch.md](M3-client-launch.md)

## 已完成主线

| Phase | 状态 | 说明 |
|-------|------|------|
| 3A | ✅ 完成 | 微信登录、openid 绑定、msgSecCheck 内容安全 |
| 3D/3E | ✅ 完成 | 前端体验补齐、道具消费闭环、内容安全处罚资产同步、协议补丁 |
| 3F | ✅ 完成 | 玩法扩展规划落档 |
| 3G | ✅ 完成 | 命格签系统：开局三选一与局内修正 |
| 3H | ✅ 完成 | 天道人格扩容 |
| 3I | ✅ 完成 | 本局执念、多榜单、盖棺定论 |
| 3J | ✅ 完成 | KarmaTrace 入池、普通事件触发、玩家主动遗言 |
| 3K-1 | ✅ 完成 | 普通事件分池、轻选择自动结算、人格权重、执念推进 |
| 3K-2 | ✅ 完成 | 轻选择前端展示、局内统计累计、差异化 KarmaTrace hook |
| M4-1 | ✅ 完成 | Roguelike 三路路线地图、节点推进、SC_RUN_MAP/CS_CHOOSE_MAP_NODE、小程序路线图 |

## 下一步

可选方向一：回到 Phase 3L，进入国内云部署、ICP 备案、微信审核提交的上架准备阶段。

优先范围：
- 确认正式域名、HTTPS、WebSocket 域名与微信小程序后台配置。
- 准备国内云部署与服务守护方案。
- 梳理 ICP、隐私合规、内容安全审核材料。

可选方向二：继续 M4 路线地图体验打磨。

优先范围：
- 微信开发者工具真机验证三路节点图。
- 补终章节点走完后的固定提示或终局引导。
- 设计局内黑市商品边界。

## 当前验证状态

- 3K-1 定向验证记录见 `M3-client-launch.md`：
  - `python -m pytest server\tests\test_event_config.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`：128 passed
  - `python -m pytest server\tests\test_hall.py server\tests\test_shop.py server\tests\test_wechat.py -q`：46 passed, 14 skipped
  - `python -m compileall server -q`：通过
- 3K-2 定向验证记录见 `M3-client-launch.md`：
  - `python -m pytest server\tests\test_event_config.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py server\tests\test_shop.py -q`：144 passed, 9 skipped
  - `python -m compileall server -q`：通过
  - `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 弃用）
- M4-1 定向验证记录见 `M4-roguelike-run-map.md`：
  - `python -m pytest server\tests\test_run_map.py server\tests\test_event_config.py server\tests\test_game_engine.py -q`：109 passed
  - `python -m pytest server\tests\test_e2e_ws.py -q`：30 passed
  - `python -m pytest server\tests\test_run_map.py server\tests\test_event_config.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`：139 passed
  - `python -m compileall server -q`：通过
  - `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 与 `baseUrl` 弃用）
- 当前全量测试有已知风险：旧并发/重连测试仍假设 `CS_START_GAME` 后第一帧是 `SC_GAME_LOG`，但 3I 后协议会先返回 `SC_DESTINY_OFFER`。修复测试前，不应把这类失败直接判定为业务回退。

## 文档读取顺序

1. `PROJECT_STATUS.md`：判断当前进度、下一步、已知风险。
2. `AGENTS.md`：读取编码规则、阶段门控、架构约束。
3. `M4-roguelike-run-map.md`：读取当前 M4 路线地图需求、实施记录和遗留风险。
4. 若回到上架准备，再读取 `M3-client-launch.md` 的 3L 部署与合规范围。
5. `README.md`：仅作为项目介绍和启动说明，不作为当前进度事实源。

## 后续需求进入规则

- 未决定做的需求：先放入本文件的 Backlog。
- 决定下一步做的需求：进入本文件“下一步”并写入对应 `M*.md` 的当前阶段章节。
- 已完成需求：更新本文件当前进度，并在对应 `M*.md` 追加实施记录。

## Backlog

| 优先级 | 需求 | 归属 | 备注 |
|--------|------|------|------|
| P2 | Hall 分享图按榜单类型生成差异化战报 | M3 后续 | 当前 Hall 已 Tab 化，分享图仍可继续增强 |
| P2 | KarmaTrace 真实死亡归因统计 | M3 后续 | `death_caused_count` 已预留 |
