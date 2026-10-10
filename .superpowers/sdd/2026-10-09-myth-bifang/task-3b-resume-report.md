# Task 3B 恢复实施报告

日期：2026-10-10
工作区：`C:/Users/95191/.codex/worktrees/m5-card-roguelike/UnlimitWorld`
分支：`codex/m5-card-roguelike`

## 交付结论

Task 3B 前端已完成 `/myth` 独立可玩入口：三流派建局、真实服务剧情、毕方战斗 HUD、
服务器权威快照、网络锁与演出锁、终局延迟、菜单、异常恢复、四视口共享几何均已接入。
经典 `/` 入口及经典会话 key 未改写；神话模式使用 3A 已提供的独立会话。

本轮只消费控制器发布的已批准卡通场景、角色种子与 9 条正式 strip。九张正式卡画尚未交付，
手牌使用领域信息和图标呈现，没有复用旧卡面。`bifang_retreat` 因候选质量不合格未进入
manifest，UI 如实显示“动作案卷缺页 1/10”，不得据此宣称十条动作或完整美术包验收。

## 主要实现

- `main.tsx` 仅在 `/myth` 与其子路径加载 `MythApp`，根路径继续加载原 `App`。
- 三流派入口直接调用 `useGameSession("myth_bifang")`；故事显示服务端全文、选择和完整代价。
- 战斗 HUD、预告、手牌、挑衅、结束回合及卡牌目标均来自服务端 `RunView`。
- 网络不确定性与逐事件演出分别上锁；设置在不确定状态仍可打开，命令使用两锁并集。
- 401 只清除神话样板凭证；409 同步权威局面；响应截断可用原 action id 重试。
- 表现队列逐事件应用 `state_after`，最后一个真实动作结束后才发布最终权威阶段。
- Phaser canvas 与 DOM 敌方目标共用 `mythLayout`；角色 alpha 边界、脚锚和四视口缩放一致。
- manifest 严格校验固定动作键、帧尺寸、帧数、fps、anchor 与 `reference_height`。
- 动作尺寸使用“布局可见身高 / reference_height”；先切换 clip 纹理再设置最终显示尺寸，
  避免继承 2048×3072 seed 比例导致动作角色缩成约四分之一。
- 玩家伤害按“hero 出招 -> bifang_hurt”播放；敌方伤害按
  “bifang_strike -> hero_hurt”播放。胜利末击因此会先播放真实受击，再处理缺失退场的短等待。
- 技术线条/盾反馈在源角色动作结束后、受击动作开始前出现，不再抢在起手之前；它只承担
  结构化事件可读性，不是 Task 4 最终法术 VFX 验收。
- `hero_idle` 与 `bifang_idle` 正常循环；开启“减少动态效果”后立即回到静态种子，动作反馈缩短。
- 360/390 手机命令行固定图标并允许挑衅代价换行；矮屏仍显示完整卡牌规则，不用隐藏正文换空间；
  顶栏保留生命、护盾和天谴三项关键数值，仅隐藏生命进度条。
- 大标题使用固定桌面字号和 720px 断点字号，不按 viewport 宽度缩放字体。

## OOM 与生命周期修复

旧草稿 OOM 的根因不是 Vitest 容量，而是非空 adapter 函数身份变化触发
`replaceAdapter -> synchronizeDisplay -> publish -> render` 循环。恢复后表现队列持有稳定 delegate，
每次调用读取最新 adapter；只有 adapter 从可用转为 `null` 才取消并同步权威局面。

另发现 React state setter 会把 Phaser presenter 函数当作 updater 立即执行。入口现使用
`setAdapter(() => next)` 保存函数值，并以稳定 `attachAdapter` 交给 Stage。focused hook 测试和
全量单元测试均未再出现挂起或 OOM。

## 动作与视觉验证

manifest 状态为 `animation-review`，已加载 9 条 4 帧、768×768、anchor `[0.5,1]` 的 strip：

- hero：idle 4fps/ref762、sword 8fps/ref634、cast/hurt/defeat 8fps/ref768。
- bifang：idle 4fps/ref764、charge 8fps/ref679、strike 8fps/ref662、hurt 8fps/ref768。
- `bifang_retreat` 缺失；没有静态 tween、旧图或拒绝候选替代。

逐条源图检查确认：idle 有持续呼吸/重心变化；sword/cast/charge/strike 有起势、主动作和收势；
hurt/defeat 有明确受击及败北结尾；武器、翅膀和肢体未被条带边界裁切。浏览器实际 canvas 另验证
动作角色尺寸、脚锚、突刺展开和终局延迟，而非只查看源条带。

## 测试与证据

最终验证命令在 `web-client` 执行：

- `npm test -- --reporter=dot`：25 files、112 tests 全部通过。
- `npm run typecheck`：通过。
- `npm run build`：通过；仅有既有 Phaser 大 chunk 警告。
- `npm run check:functions`：检查 65 个源码文件，0 个函数超过 50 有效行。
- `npm run test:e2e -- e2e/myth.spec.ts --reporter=line`：覆盖三流派真实建局、剧情、刷新恢复、
  响应丢失重试、409、401、双 idle、减少动态、真实服务败局、受控终击延迟和四视口；
  恢复服务后的最终 fresh run 为 8 passed（34.5s）。

E2E 不再只检查 dataURL 长度：每个视口用 `getImageData` 验证高不透明覆盖、彩色覆盖和亮度跨度；
左右角色区域分别验证 idle 像素变化；突刺时左侧角色区域显著变化。真实服务败局没有 route 或
伪造响应，从 UI 连续结束回合直至服务端返回 `game_over`，并捕捉毕方出招、主角受击、
`hero_defeat` 和最终页面。受控致命响应仅用于验证“最终权威阶段必须等待演出完成”。

控制器另用独立 Chrome profile 做了不计入上述 E2E 数字的正常 UI 真服胜局：sword + borrow_fire，
16 个 UI 命令、revision 17、completed、玩家 45/60、毕方 0 HP；无 route/mock/规则修改，刷新保持
completed，重新审案返回三流派且无 pageerror。证据为
`.data/playtest-myth-3b/myth-real-service-victory.png`。

首次最终 E2E 运行时，既有 hidden 5173 Node 在 2026-10-10 12:45:16 以 Windows native
`0xC0000409` 退出，首条等待入口超时，后续均为 `ERR_CONNECTION_REFUSED`；这不是前端业务断言失败。
控制器保留诊断日志并用既有脚本恢复同工作区服务后，未修改 launcher/runtime，完整 8 条复跑通过。

忽略目录中的人工复核证据：

- `.data/playtest-myth-3b/myth-1440x900.png`
- `.data/playtest-myth-3b/myth-390x844.png`
- `.data/playtest-myth-3b/myth-430x932.png`
- `.data/playtest-myth-3b/myth-360x740.png`
- `.data/playtest-myth-3b/myth-hero-sword-action.png`
- `.data/playtest-myth-3b/myth-real-defeat-0.png` 至 `myth-real-defeat-8.png`
- `.data/playtest-myth-3b/myth-real-service-game-over.png`

## 边界与遗留风险

本报告结论仅代表 Task 3B 技术入口、权威状态和动作运行时交付，不代表 Task 4 美术全部完成或
BF3 最终法术表现通过。

- 本任务不修改或暂存控制器拥有的 manifest、图片、来源记录、图片工具、资源测试、M5 或
  `PROJECT_STATUS.md`；资源归档由控制器独立提交。
- 九张正式卡画未交付，当前不能称卡牌美术完成。
- `bifang_retreat` 未交付，当前不能称十条动作完成；胜利仍会正确等待最后一击 hurt 和短结算，
  但没有退场姿态。
- 当前法术线条/盾圈为技术反馈，不是最终粒子、冲击、命中或法术演出资产。
- 未执行 push；Task 3B 只建立中文本地 commit，交由控制器后续整合。
- 复用了控制器已启动的 5173/8787 服务，没有启动冲突服务或停止其他进程。

## Fix Round 1：runtime 就绪与资源失败门控

复审指出两个生命周期竞态，本轮仅修复对应前端边界：

- `MythStage` 用 ref 跨越动态 import 等待，创建 runtime 和发布 adapter 前均读取最新
  `reducedMotion`。因此用户在模块尚未返回时切换设置，runtime 不会按旧值启动。
- Phaser loader 的任一 `loaderror` 会写入 world 失败状态；`createWorld` 同时核验三张 seed、
  manifest 中每条已登记 strip 的纹理和动画登记结果。失败时不调用 `ready`，不会发布 presenter。
- combat 阶段在 presenter 尚未 ready 或已因资源错误撤销时，将该状态并入命令锁；卡牌、目标、
  挑衅和结束回合不可提交。设置、素材重试和既有恢复/同步入口保持可用。
- manifest 现保留并核验 `version: bifang-v1`，status 只接受 `seed-review` / `animation-review`；
  动作条目必须为 4 帧、768×768、anchor `[0.5,1]`，idle 4fps、其他动作 8fps。
- 运行时只要求 manifest 已登记的 9 条 strip；被人工拒绝且未登记的 `bifang_retreat` 仍是
  如实展示的 1/10 未完成边界，不会被误报为下载失败，也不会用静态计时伪造退场动作。

### TDD 记录

RED：

- `npm test -- --run src/myth/MythStage.test.tsx src/myth/mythAssets.test.ts`：17 项中 9 项按预期失败；
  延迟 import 收到旧 `false`，清单未保留 version 且错误版本/status/帧协议未被拒绝。
- `npx playwright test e2e/myth.spec.ts --grep "已登记动作条带加载失败"`：拦截
  `hero_idle.png` 返回 404 后，错误可见但 `end-turn` 仍为 enabled，证明资源错误未进入命令锁。

GREEN：

- `npm test -- --run src/myth/MythStage.test.tsx src/myth/mythAssets.test.ts src/myth/createMythGame.test.ts src/myth/MythApp.test.tsx`：
  4 files、22 tests 全部通过。
- `npm test -- --reporter=dot`：27 files、121 tests 全部通过，无 OOM 或挂起。
- `npx playwright test e2e/myth.spec.ts --grep "双角色 idle|已登记动作条带加载失败"`：2 passed；
  正常九条清单仍启动双 idle，减少动态仍停在静态种子；单条已登记 strip 404 时命令锁与安全操作通过。
- `npm run typecheck`：通过。
- `npm run build`：通过；仅保留既有 Phaser 1,350.47 kB 大 chunk 警告。
- `npm run check:functions`：检查 68 个源码文件，0 个函数超过 50 有效行。
- `git diff --check`：通过；只报告工作区既有 CRLF 转换提示。

覆盖文件：`MythStage.test.tsx` 覆盖延迟 import 设置竞态；`mythAssets.test.ts` 覆盖当前资源协议；
`createMythGame.test.ts` / `mythRuntimeAssets.ts` 覆盖已登记纹理全集和未登记 retreat 边界；
`MythApp.test.tsx` 覆盖 runtime ready 前命令锁；`e2e/myth.spec.ts` 用真实 Phaser 加载失败验证不发布
可操作战场。未重复控制器已完成的全套 Chrome；本轮未出现新的 dev server native 退出。
