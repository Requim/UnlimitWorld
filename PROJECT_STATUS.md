# Project Status：天道不正经

> 更新时间：2026-10-09
> 作用：本文件是当前开发进度的唯一入口。Codex 每次进入本项目时，先读本文件，再按需读取 `AGENTS.md` 和当前里程碑文档。

## 当前阶段

- **当前里程碑：** M5 卡牌肉鸽重做（用户已确认计划）
- **当前进度：** M5-1 技术样板保留；毕方权威规则、剧情、结构化事件及独立会话与可取消表现队列（3A）已实施并通过独立审查；尚无三张新图或可见新场景
- **下一阶段：** 图像返回格式适配等待用户授权；取得真实高清种子后接入可见入口与场景（3B），动作与九张卡面待种子视觉认可；完整 Task 2、Task 3 和 M5 未完成
- **当前主文档：** [M5-card-roguelike.md](M5-card-roguelike.md)
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
| M4 体验补强 | ✅ 完成 | 路线耗尽续图提示、终章回响引导、全局路线图、挂机页事件优先国风动漫 UI |

## 下一步

用户于 2026-10-09 确认从挂机玩法转向抽牌式卡牌肉鸽：

- 浏览器优先，国风怪诞漫画美术与 UI 全部重做。
- 九层有限路线、三流派、可预判且可反制的天谴、独立 SQLite 存档。
- 首版不接旧账号、支付、微信、真实 AI 或生产数据库。
- 在 `codex/m5-card-roguelike` 隔离分支实施；原工作区配置改动保持不变。
- M5-1 必需验收项见 M5 文档；未达标不能宣称整局完成。
- 用户已授权自有图片 API；27 张正式位图已生成并接入，真实浏览器解码和四视口验证通过。
- 用户随后明确否定当前美术品质，确认需要真正的出招、法术与受击动作。
- 最新方向为庄严壮阔、有压迫感的国风神话，魔改中保留怪诞幽默；
  已批准先做高清精绘 2D、序列帧动作与分层场景的「章莪山·毕方」单场样板。
- 当前详细设计为
  [毕方样板设计](docs/superpowers/specs/2026-10-09-myth-bifang-design.md)，
  用户随后明确要求直接实施；实施计划为
  [毕方实施任务](docs/superpowers/plans/2026-10-09-myth-bifang.md)。
  此授权不等于尚未生成的种子图已获视觉认可，动作批量生成仍遵守种子审核门控。
- 先验收样板实际画质、动作和剧情，再扩展其他怪物；不立即重新批量生成全部 27 张。
- 原装 ImageGen 本轮启动三张高质量 2K/4K 请求，毕方返回 `b64_json` 为 null，
  CLI fail-fast 退出 1，未保存任何新图。没有追加收费重试、擅换模型或改原装工具；
  已询问用户是否允许项目内专用适配器。其余任务的远端生成/收费状态未知。
- 在此阻塞下先完成 3A 的独立会话与纯表现队列，不提前发布空战场；
  3B 全部原要求保留，基础接入真实场景后仍需重新验证。
- 本地 SQLite 已一致备份 `.data/m5-before-bifang-20261009.sqlite3`，
  integrity check 为 ok；回退不得直接假设旧代码能读新增字段。
- 已复现的旧回归门控仍待处置，不自动进入下一里程碑。
- 生成凭据仅在本次进程内使用，不写入代码、Git、前端或全局环境；已建议轮换聊天中暴露的 Key。
- 浏览器试玩的美术与好玩程度需用户认可，自动测试不代替体验判断。
- 原 M4、3L 下列后续方向暂时冻结，未完成项仍保持未完成。

可选方向一：回到 Phase 3L，进入国内云部署、ICP 备案、微信审核提交的上架准备阶段。

优先范围：
- 确认正式域名、HTTPS、WebSocket 域名与微信小程序后台配置。
- 准备国内云部署与服务守护方案。
- 梳理 ICP、隐私合规、内容安全审核材料。

可选方向二：继续 M4 路线地图体验打磨。

优先范围：
- 微信开发者工具真机验证全局路线图和小屏日志区域。
- 设计终章固定天道节点或更强终局引导。
- 设计局内黑市商品边界。

## 当前验证状态

- 毕方权威模式、三选择、结构化中间快照已通过独立审查；
  剧情因果、可选模式类型和领域双向依赖已修正。
  本轮规则/API/工具实际复跑 105 passed、2 skipped。
  新资源整理 16 passed、2 skipped（物理符号链接权限限制），事务修复复审通过。
  3A 完成并独立审查通过：模式存档隔离、GET resync 保留 unknown 动作、
  顺序事件、中间快照、取消/重附着、同步重入与旧回调隔离均有回归。
  最后相关前端变更后 20 files / 78 passed；类型与生产构建通过，
  50 个源文件函数检查无超长，Phaser 包体警告保留。
  修改及相关范围 255 个 Python 函数无超长；旧全仓超限不冒充已修复。
  已验证进程归属后重启本地 API，三流派乘三选择 9 组真实规则、
  精确重试和 GET 恢复验证通过；最终真实 Chrome 29 passed，
  包含经典开局/刷新/异常恢复、四视口与旧资源解码。不是毕方新画面或动作验收。
  新图实际生成失败，尚无高清种子、动作帧或毕方前端试玩验收。
- M5 启动基线：`python -m pytest server/tests/test_run_map.py server/tests/test_event_config.py -q`，48 passed。
- M5 新规则/API/工具：61 passed；前端 54 Vitest、29 Chrome E2E；
  Node QA 10 passed，类型/构建/离线协议再生成通过。
- `f5aa4f9` 固定源码八项浏览器技术路径全部通过：九层通关（47 HP）、
  四视口、重试/409/401、死亡因果、休整、刷新与设置持久化。
- 14:15 实际 API 重启保持完整存档与旧 Unicode 动作缓存，
  同编号异内容 409 不改变局面，健康服务复用通过。
- 短屏文字、图像命中、未知结果和迟到响应已修复并审查；
  测试初始化及重抽选牌的 QA 假设已局部纠正，保留失败报告和回归。
- 正式位图检查 passed：27 张 PNG/WebP、真实浏览器解码、来源摘要一致性通过；
  总计 5,727,133 bytes，角色经单色去底，场景 5:2、卡面 4:3，不裁掉法术主体。
- `.data/playtest-formal-art-final/report.json`：本轮正式资源八项全部 passed，
  九层通关剩余 50 HP，无自动恢复动作；四视口、静态画布更新、刷新、
  设置持久化、网络重试/409/401、死亡因果及休整通过。
- 人工查看过七角色与十八法术图总览、两个场景、开局和桌面/手机正式战斗截图。
  用户已否定本版美术品质；技术解码和布局通过不等于美术验收通过。
  `createBattleGame.ts` 当前只展示静态角色与浮动文字，没有完整出招、受击、
  护盾和雷罚演出；上述旧画布检查不证明真正的攻击动画已经实现。
  毕方权威规则已实施，但新图、可见场景与动画尚未完成，不宣称 M5 已完成；
  旧定向回归失败保持独立记录。
- 本地试玩：`http://127.0.0.1:5173`。分支 `codex/m5-card-roguelike`，
  历史技术快照为 `f5aa4f9`；本轮正式美术按文档、验证、中文提交与推送闭环归档，
  最新代码以该隔离分支 HEAD 为准，没有合并 main 或部署。
- 毕方规则与 3A 基础归档 `00d524e` 已推送，远端完整 SHA 已核对一致；
  后续推送事实记录为文档变更，最终源码以隔离分支 HEAD 为准。
- 原代码 `525f4ce` 全量复跑：14 failed、284 passed、14 skipped；
  旧并发/引擎/集成失败与旧随机事件断言抖动保留，不宣称全量通过。
- 旧路线/事件/引擎最新定向复跑：111 passed、1 failed。
  失败为随机首节点进入天道轨道，导致本地事件 mock 不执行；
  原始工作区定向固定 `heaven` 已复现，相关旧代码未修改。

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
- M4 路线终章续图提示验证记录见 `M4-roguelike-run-map.md`：
  - `python -m pytest server\tests\test_run_map.py server\tests\test_game_engine.py server\tests\test_e2e_ws.py -q`：67 passed, 34 skipped（当前环境缺 `pytest-asyncio`，既有 async 单测跳过；本次新增终章断言已同步执行）
  - `python -m compileall server -q`：通过
  - `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 与 `baseUrl` 弃用）
- M4 全局路线图与国风暗卷 UI 验证记录见 `M4-roguelike-run-map.md`：
  - `git diff --check -- client\pages\game\game.ts client\pages\game\game.wxml client\pages\game\game.wxss`：通过
  - `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 与 `baseUrl` 弃用）
- M4 挂机页事件优先国风动漫 UI 验证记录见 `M4-roguelike-run-map.md`：
  - `git diff --check -- client\pages\game\game.ts client\pages\game\game.wxml client\pages\game\game.wxss PROJECT_STATUS.md M4-roguelike-run-map.md`：通过
  - `npx -p typescript tsc -p client\tsconfig.json --noEmit`：未通过，仍受既有工具链阻塞影响（缺 `wechat-miniprogram` 类型，TypeScript 6 提示 `moduleResolution/baseUrl` 与 `baseUrl` 弃用）
- 当前全量测试有已知风险：旧并发/重连测试仍假设 `CS_START_GAME` 后第一帧是 `SC_GAME_LOG`，但 3I 后协议会先返回 `SC_DESTINY_OFFER`。修复测试前，不应把这类失败直接判定为业务回退。

## 文档读取顺序

1. `PROJECT_STATUS.md`：判断当前进度、下一步、已知风险。
2. `AGENTS.md`：读取编码规则、阶段门控、架构约束。
3. `M5-card-roguelike.md`：当前卡牌肉鸽重做需求、实施记录和验收边界。
4. 若处理旧玩法，读取 `M4-roguelike-run-map.md`；旧主线当前冻结。
5. 若回到上架准备，再读取 `M3-client-launch.md` 的 3L 部署与合规范围。
6. `README.md`：仅作为项目介绍和启动说明，不作为当前进度事实源。

## 后续需求进入规则

- 未决定做的需求：先放入本文件的 Backlog。
- 决定下一步做的需求：进入本文件“下一步”并写入对应 `M*.md` 的当前阶段章节。
- 已完成需求：更新本文件当前进度，并在对应 `M*.md` 追加实施记录。

## Backlog

| 优先级 | 需求 | 归属 | 备注 |
|--------|------|------|------|
| P2 | Hall 分享图按榜单类型生成差异化战报 | M3 后续 | 当前 Hall 已 Tab 化，分享图仍可继续增强 |
| P2 | KarmaTrace 真实死亡归因统计 | M3 后续 | `death_caused_count` 已预留 |
