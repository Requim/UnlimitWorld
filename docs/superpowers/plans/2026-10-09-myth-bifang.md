# 毕方神话战斗样板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将已确认的毕方设计落实为隔离于经典九层局的权威剧情战斗，并用用户认可的高清种子展开真实动作与新 UI。

**Architecture:** Python 分层 DDD 管理模式、剧情与实际结算；React 管理界面及会话，Phaser 管理有序表现。服务器快照是唯一规则事实源。

**Tech Stack:** 现有 Python/Pydantic/FastAPI/SQLite、React/TypeScript/Vite/Phaser/Lucide；原装 ImageGen CLI 和用户指定接口，不更换技术栈以增加迁移风险。

**Spec:** `docs/superpowers/specs/2026-10-09-myth-bifang-design.md`

**2026-10-10 恢复与调整：** 修士/毕方/场景写实原图已取得，但用户明确要求
更卡通、诙谐搞怪。旧种子与旧提示词不再作为当前美术验收输入；
3B 实施中止并保留交接。用户随后确认新单张方案，卡通毕方一次生成成功，
实际 2048×3072。用户随后认可实际毕方；配套修士 2048×3072、
场景 3840×2160 各一次生成成功，已核验并合成静态构图。
用户随后反馈「认可，战斗状态是 角色是会动的」，三种子实际认可完成。
现恢复 3B 草稿与 Task 4；先验证参考图 edit 路径，再按动作各一次请求。
真实姿态变化是硬验收项，静态立绘晃动不算角色动作。
Task 1 与 3A 保持已完成，不重新派已完成任务。当前三种子已整理入独立目录，
九条实际动作发布为 animation-review；畸形退场拒绝且无重试，九张卡面未生成，
3B技术入口、浏览器验证及加载门控修复已独立复审通过；
完整动作体验仍待用户判断，不称 Task4 或 M5 完成。

## Global Constraints

- 工作目录为已验证的 `codex/m5-card-roguelike` linked worktree；不改原工作区微信配置，不合并 main，不部署或接生产数据库。
- 函数不超过 50 个有效行；公开接口注释说明用途、参数、返回值及错误/副作用；中文 Git 提交。手动编辑用 apply_patch。
- 依赖方向 interface -> application -> domain；infrastructure 实现端口。客户端不算伤害、生死或剧情收益，不上传局面。
- `mode` 只能是 `classic | myth_bifang`，省略/旧档缺字段时为 classic。样板独立浏览器存档键，经典九层局保持可用。
- 剧情 ID `bifang_trial`、内容版本 `bifang-v1`；选择 ID `borrow_fire`、`seal_evidence`、`destroy_scroll`，收益与代价在提交前由服务器完整展示。
- 借火：玩家 wrath +16、敌人 burn 3；封存：玩家 block 10、敌人 block 6；毁卷：首回合 energy 4、下一真实敌攻每段 +2。初始化战斗之后应用；防御不消耗加值。
- 样板 10 牌为 4 flying_sword、3 guard、1 focus、2 流派牌；sword: charge_sword/myriad_swords，fire: fire_seed/borrow_fire，talisman: demon_mirror/lightning_talisman。不改经典牌组或单卡数值。
- 独立 boss `bifang` HP 48，循环 defend 8 -> burn 5（双方存活时 wrath +3）-> multi 5（2 段）。不混入经典随机池；样板胜利直接 completed，无选牌奖励。
- 事件保持 kind/text/amount/target，并新增可选 source/card_id/visual/absorbed/state_after；快照不得含 RNG 或隐藏牌序。攻击被全挡也有命中事件，按真实结算顺序保存。
- 表现按 run_id/revision/event_index 去重，网络锁与演出锁分离；最后一击演完才切结算，旧世代/unmount/重附着必须取消回调。
- 首轮只生成 3 张种子。角色请求 2048x3072、场景 3840x2160、quality high、model gpt-image-2；核验真实返回像素。不插值充高清，不自行换模型。
- 种子取得实际用户视觉认可后才生成动作条带和 9 卡面。没有动作条带不能把静态移动称为完成。自动测试不代替用户认可。
- 图像凭据只用隐藏输入和进程环境，不进文件/Git/前端/日志；收费请求每项最多一次，本轮不自动扩批。
- 数据库新格式写入前做 SQLite 一致备份，历史旧测试失败和 Phaser 包体风险如实保留。

## Task 1: 权威模式、剧情与结构化战斗事件

独立实施单元。控制器推进三张种子时，单个实现代理负责本任务，不派生代理。

**Files**
- Modify: `server/domain/roguelike/models.py`, `catalog.py`, `combat.py`
- Create: `server/domain/roguelike/myth.py`, `server/domain/roguelike/presentation.py`
- Modify: `server/application/roguelike/factory.py`, `service.py`, `views.py`
- Modify: `server/interface/roguelike_app.py`
- Create: `server/tests/test_myth_bifang.py`
- Modify: `server/tests/test_roguelike_api.py`
- Generate: `web-client/src/api/openapi.json`, `schema.ts`; Modify: `web-client/src/api/types.ts` only for necessary aliases
- Update: `M5-card-roguelike.md` Task 1 implementation record only; controller owns PROJECT_STATUS and asset sections

**Protocol**
- CreateRunRequest.mode defaults classic; RunState/RunView.mode defaults classic. Invalid mode -> 422.
- Myth run begins at phase event with a one-node boss map; public `story` contains id/version/title/body, server choices with consequence text and selected choice (nullable).
- Existing `choose_event` selects myth story when mode is myth_bifang; invalid choice or repeated phase -> 422 without mutation. Exact duplicate action returns cached response.
- RunState persists story id/version/selected choice; never infer selection from history text.
- Define public combat presentation snapshot with player hp/block/wrath/reflect and enemy hp/block/burn/weak, plus turn/energy when available. Each event state_after records then-current public attributes, not the final state copied to every event.
- source is player/enemy/heaven/system; visual uses stable snake_case semantic values such as sword/fire/shield/thunder/hit/defeat/idle. Card actions preserve card_id on their effects, including fully blocked hits; environment effects do not fabricate card IDs.
- Centralize event snapshots/metadata in a small domain helper without framework imports or repeated literal snapshot blocks. Annotate all actual battle mutations and preserve old event meanings.

**Steps**
- [x] Read relevant existing rule/API/tests and spec sections 4 and 6 before editing.
- [x] Add actual tests, observe RED, then implement. A minimal first test:

```python
def test_myth_start_has_story_and_sample_deck(client):
    response = client.post("/api/v2/runs", json={
        "archetype": "sword", "mode": "myth_bifang",
    })
    assert response.status_code == 201
    run = response.json()["run"]
    assert run["phase"] == "event"
    assert run["mode"] == "myth_bifang"
    assert run["story"]["version"] == "bifang-v1"
    assert len(run["deck"]) == 10
```

- [x] Domain tests cover each archetype deck; all three starting modifiers after initialization; defense preserves destroy_scroll bonus; burn attack wrath even when shielded; multi two hits; weak/taunt intent; victory choice-specific epitaph; defeat.
- [x] API tests cover all choices, exact retry, changed-payload 409, stale revision 409, invalid selection/phase unchanged, restart persistence and legacy JSON absent mode/story defaults.
- [x] Structured events test intermediate snapshots (not all final), shield absorption including zero HP damage, multi ordering, lightning redirect, and lethal no postmortem damage.
- [x] Classic API/rule tests stay green and catalog remains compatible (18 cards/6 relics; independent boss may make enemies 7).
- [x] Export OpenAPI with existing tool and regenerate types; TypeScript generated compatibility must pass.
- [x] Run `.venv/Scripts/python.exe -m pytest server/tests/test_myth_bifang.py server/tests/test_roguelike_rules.py server/tests/test_roguelike_api.py tests -q`, function checker, compileall and git diff check.
- [x] Self-review, document actual tests/risks, stage only Task 1 files and Chinese commit. Do not push; controller performs review and phase archival push.

## Task 2: 三张高清种子与来源核验

控制器负责，独立于 Task 1 的文件。必须遵守用户实际视觉审核门控。

**Files**
- Create: `docs/m5/myth/seed-direction.md`, `docs/m5/myth/prompts/seeds.jsonl`
- Create: `docs/m5/myth/seed-provenance.json`
- Output ignored originals: `.data/imagegen/myth-seeds/`
- Final seeds: `web-client/public/assets/myth/seeds/`
- Create: `web-client/public/assets/myth/manifest.json`
- Tests/tool if needed: `tests/test_myth_assets.py`, `tools/prepare_myth_assets.py`

**Steps**
- [x] Prompts: guofeng animation-style adult swordsman and one-legged Bifang on flat magenta; bare jade mountain and clear combat terrace. No rendered UI/text or existing IP copying.
  三张新提示词与原图已取得，旧 `seeds.jsonl` 仅作为历史请求；毕方已认可，
  三张卡通实际图片已获得用户视觉认可。
- [x] Original CLI generate-batch uses exact user host, gpt-image-2/high, 3 jobs and max-attempts 1; no extra paid attempts if returns wrong size.
  首轮返回解析失败已归档；2026-10-09 用户授权项目适配器并取得毕方。
  2026-10-10 用户要求继续实施，缺失修士/场景沿用已验证适配器各请求一次，
  原参数与提示词不变，保留脱敏证据，不再运行已知无法解析 URL 的原工具。
- [x] Inspect all returned images and actual dimensions; preserve SHA256 and requested/actual dimensions without credential. Only correctly sized images labelled native-target-met.
  卡通三图实际精确目标尺寸，来源分开记录；不继承被拒绝写实图的认可状态。
- [x] Original chroma-key tool removes backgrounds; inspect full limbs/weapon/beak/feather edges, never claim original alpha.
  已检查并整理进入独立种子目录；少量细发/羽缘紫边保留为精修风险，
  不等于所有动作或整场视觉已验收。
- [x] Save final images in independent myth directory and manifest status seed-review, not animation-ready. Existing assets remain intact.
  先 seed-review 发布；接入九条动作后变为 animation-review，而非 ready。
- [x] Add preparation checks (dimension mismatch, invalid target/path, alpha preservation) before implementation when a normalization tool is needed; do not upscale low-resolution source.
- [x] Show the three local files to user with actual decoded dimensions. No card/sprite generation until user approves these actual seeds.
  2026-10-10 三张卡通实际种子获用户认可；正式边缘与动作仍须单独验证。
- [x] Record actual test/visual result in M5 and Chinese commit/push reviewed seed unit.
  资源/工具独立归档 `44f5682`，远端完整SHA已核对；
  九条动作部分发布不代表 Task4 完成。

## Task 3: 独立入口与生命周期安全的表现队列

依赖 Task 1 协议；可以在种子待审核阶段落地技术入口，不伪称正式动作完成。
本轮图像返回格式阻塞时，先独立交付 3A（会话与纯队列基础）。
3B（可见入口、场景、实际视觉试玩）保留全部要求，待真实种子可用后接入；
不发布空战场冒充画面重做，也不将 3A 完成标记为整个 Task 3 完成。

### 3A 可独立验收的基础

**Scope**
- Modify: `web-client/src/api/client.ts`, `api/types.ts`, `state/storage.ts`, `hooks/useGameSession.ts`
- Create: `web-client/src/myth/presentationQueue.ts`, `presentationQueue.test.ts`
- Add mode tests: storage/client/session lifecycle test files；现有经典测试必须保持通过。

**Exact Contracts**
- `RunMode` 从正式 `CreateRunInput["mode"]` 派生，排除 undefined；不得另写不同模式枚举。
- 存档旧键 `tiandao.cardRogue.session.v1` 不变；样板键为 `tiandao.cardRogue.mythBifang.session.v1`。设置键共享，凭据与局号完全隔离。
- `loadSession(mode = "classic")`、`saveSession(session, mode = "classic")`、`clearSession(mode = "classic")`；旧无模式调用行为不变。
- `useGameSession(mode = "classic")`；建局经典调用继续省略模式，样板显式 myth_bifang。还原与响应需校验模式，缺 mode 只视为 classic；模式不匹配保留凭据、给出可恢复错误，不悄悄覆盖另一档。
- 模式变化/重开/卸载使旧世代的成功、错误及 finally 均失效。所有 GET 同步与 POST 仍走既有操作边界。
- 新公开 `resync()` 只读 GET 用于未来演出错误恢复；未知动作仍待原编号重放时不能借同步清空未决锁，409 的同步重试仍只 GET。
- `PresentationBatch = {runId, revision, events}`；events 使用生成的 GameEvent，不解析文字、不计算 HP。
- `PresentationAdapter` 接收事件和 AbortSignal，返回 Promise；状态与完成回调只由当前世代触发，支持结构化 state_after，网络命令不进入纯队列。
- 纯队列按 run_id/revision/event_index 去重，顺序消费全部事件；普通精确重放、过期 revision、取消后资源重附着不重复攻击。
- cancel/dispose 及时释放表现锁并使在途回调失效；新局旧事件不能回写。错误释放锁并回调同步入口，不吞错、重发 POST 或伪造结算。

**Steps**
- [x] TDD 验证两键隔离/默认兼容/模式错配/旧模式迟到响应与 finally。
- [x] TDD 验证三事件依次完成，中途事件快照不被末尾结果替代，最后事件前不发完成回调。
- [x] 通过 deferred promises 验证重复 revision、旧 revision、run 切换、cancel、dispose、失败、重附着与旧异步完成；测试不得靠固定睡眠。
- [x] 验证 resync 只 GET，未知动作锁不被清除，失败保留凭据/同步重试，迟到同步不覆盖新局。
- [x] 跑 npm test、typecheck、build、check:functions；经典真实 Chrome smoke/恢复路径不回退。自审、独立审查。
- [x] 控制器补文档、中文归档与 push；完成后在本计划 ledger 记录确切远端 SHA。

### 3B 可见入口与场景（技术验证完成）

**Files**
- Modify: `web-client/src/main.tsx`, `api/client.ts`, `state/storage.ts`, `hooks/useGameSession.ts`
- Create: `web-client/src/myth/MythApp.tsx`, `MythStory.tsx`, `myth.css`
- Create: `web-client/src/myth/presentationQueue.ts`, corresponding tests
- Create: `web-client/src/myth/MythStage.tsx`, `createMythGame.ts`, `mythLayout.ts`
- Create: `web-client/src/myth/useMythPresentation.ts`, corresponding tests
- Modify only necessary shared aliases, never rewrite classic scene to use unapproved art.
- Add: mode/storage tests and `web-client/e2e/myth.spec.ts`

**Steps**
- [x] Route by pathname `/myth` without adding router dependency; root remains existing App.
- [x] Mode-aware API create optional parameter; hook mode optional classic; mode-specific storage preserves root credential and default existing key. Test independent keys, restore mismatch rejection and late response after mode/reset.
- [x] Myth first screen is actual three-archetype choice; story shows complete tradeoffs from server. All commands go through existing idempotent queue.
- [x] Scene fills available space with shared portrait/landscape geometry for target hitboxes. Pending seed art explicitly marked unaccepted via UI state, never silently substituted with old comic character.
- [x] Implement pure injectable presentation queue TDD: events ordered, revision duplicate ignored, final outcome delayed, cancellation generation isolation, adapter failure unlock and authority resync; test with deferred promises (no arbitrary sleeps).
- [x] DOM HP/resource display consumes event.state_after during presentation then authoritative run; selection commands disabled during presentation and network uncertainty separately.
- [x] Technical runtime supports texture animation clips from manifest; no strips means pending required actions, not movement of a static seed called real animation.
- [x] Test startup/story/all choices/battle refresh/reset, 401/409/exact retry/unmount and lethal ending delay. Four viewport screenshots and actual canvas pixel/target checks.
- [x] Run npm test, npm run typecheck, npm run build, npm run check:functions, relevant Chrome E2E; self-review, document and Chinese commit; independent task review then controller push.
  技术与独立复审完成：`5c776a6`、修复`c622716`；
  最新121单测/38Chrome/类型构建/68文件函数检查通过，
  两项Important及清单Minor已处理，文档归档`b7c237b`已推送，
  远端完整SHA与本地核对一致。本项仅技术交付，Task4不因此完成。

## Task 4: 认可种子后的动作、卡面与最终验收

必须在 Task 2 实际图片取得用户视觉认可后执行；不以直接实施授权替代视觉审核。

### 4A 本次实施：连续挥剑样片与多帧通路

2026-10-10 用户已确认补帧方案。本次只先生成一条挥剑样片，实际体验
认可后才展开其余动作；Task4全套尚未完成，不重新实施Task1/2/3。

**实施者范围**
- Modify: `tools/prepare_myth_animation.py`、`tests/test_myth_animation_assets.py`；
  必要时新增单一职责的网格切片辅助模块与对应测试，不改原装插件。
- Modify: `web-client/src/myth/mythAssets.ts`、`mythAnimation.ts`、对应测试、
  `createMythGame.ts`；必要时新增单一职责的可取消播放辅助模块与测试。
- Add focused real-browser regression in `web-client/e2e/myth.spec.ts`；
  既有经典入口、规则、存档、加载失败门控保持不变。
- 控制器独占提示词、收费API、正式PNG/manifest/provenance及阶段文档；
  实施者不生成图片、不重写manifest、不派生代理、不push。

**精确契约**
- 新清单每clip可选 `profile: "smooth-v2"`；缺字段为既有四帧档位，
  仍验证768方帧、idle4fps/其他8fps、anchor[0.5,1]及原版本/状态。
- smooth-v2统一704×704运行帧、四列、按行顺序，无边距无间隔；
  `columns:4`，`rows:3`或`rows:4`必须与帧数匹配。
- hero_idle/bifang_idle：12帧12fps；hero_sword/hero_cast/bifang_charge/
  bifang_strike：16帧24fps；hero_hurt/hero_defeat/bifang_hurt/bifang_retreat：
  12帧24fps。未知profile、错误帧数/fps/几何/锚点必须拒绝，不放宽成任意数值。
- 规范化工具保留旧调用和四帧行为；新增显式frame_count及source_columns，
  源网格按行切片，非整除/空槽/相邻重复/少于frame_count-2种不同姿态拒绝。
  共同scale≤1、首帧锁认可种子、bottom-center、配件alpha覆盖≥99.8%、
  来源/最终摘要、损失记录及原子发布继续成立。输出为四列真实网格，
  元数据包含profile、columns、rows、实际源尺寸与source-slot尺寸。
- smooth源槽每边必须≥704；带留白的原生槽允许透明padding，
  共享scale=min(1,704/max_content)，绝不放大内容。小于704的源槽拒绝；
  legacy原有低清拒绝不变。测试原生704槽/620内容padding与低清槽负例。
- 不用复制或插值姿态补帧；曲线、纹理尺寸等界面代码不得计算伤害或生死。
- Phaser按全部真实帧播放，动作不得因固定900ms上限提前结束；
  动作完整结束后才命中/受击/结算，保持AbortSignal、destroy、世代隔离，
  取消及时释放资源和旧回调。倒地/退场最后姿态不得先跳回待机再结算。
- 减少动态仍使用简短静态反馈；资源缺失或加载失败不得解锁战斗命令。
- 现有完成9/10数量不是smooth-v2完成数；如显示进度，应明确区分档位，
  不能因旧clip存在就宣称全套补帧完成。不要添加无关UI或对外新调试API。

**测试与报告**
- TDD先观察12/16帧网格、坏尺寸/空槽/重复、源/最终去重、scale/锚点/
  首帧锁、事务失败及legacy兼容的预期失败，再实现。
- 前端TDD验证两档位严格解析、全帧播放/终局末帧、取消/destroy与减少动态，
  守住404资源门控；真实Chrome验证发布样片完整帧序与四视口无剪切/命中偏移。
- 聚焦迭代；提交前一次完整前端单测、typecheck/build/check:functions，
  Python相关工具测试及函数长度/diff检查。不要把旧全仓失败改写为通过。
- 自审、中文仅代码提交；详细报告写入本计划工作区，含RED/GREEN命令、
  原始输出位置、实际文件、未验证项和既有警告；控制器安排独立双维度审查。

**控制器资源与验收**
- 原API/model gpt-image-2/high/png/n=1，单次edit请求2816×2816，
  同一认可修士参考，4×4连续16姿态。保留实际返回像素，不自动重试。
- 原图逐帧检查后规范化，版本化发布hero_sword_smooth_v2.png并更新
  对应clip元数据，不覆盖其余旧动作；实际样片仍为animation-review。
- 正常UI真服攻击、四视口截图/像素/帧序证据、样片动图；记录实际解码尺寸/
  内存与DPR边界，不把本机Chrome采样当作实体手机性能保证。
- 文档、独立审查、最终验证、中文commit/push闭环；样片交给用户判断。

**本次检查点**
- 多帧技术子单元完成：实现8baa00d，修复82122c2/c941640；
  限定复审Spec/Quality Approved，最终136单测/43Chrome/类型构建/71文件
  函数检查通过，Python相关182passed/2权限跳过。
- 真实样片未完成：第4帧双剑与时序跳变拒绝，正式PNG/manifest不变，
  新规格发布0条；需要另行确认一次收费重试，不自动扩批。
- 当前只归档技术子单元与失败来源；完整4A样片仍待用户实际体验认可，
  4B和M5均未完成。实体手机/全套多帧内存/DPR、旧包体/服务器风险保留。
- 技术子单元归档87b4b1f已推送隔离分支，远端完整SHA核对一致；
  后续仅补写推送事实，不提前通过真实样片或展开4B。

### 4B 后续：其余动作、九卡画与最终VFX

本项保留在同一已确认计划中，依赖4A实际样片体验认可，不在本次先收费扩批。

**Files**
- Create: `docs/m5/myth/prompts/animations.jsonl`, `cards.jsonl`
- Final: `web-client/public/assets/myth/animations/`, `cards/`, update myth manifest/provenance
- Integrate: Task 3 runtime animation clips/effects; no changes to authoritative damage calculations
- Update: `M5-card-roguelike.md`, `PROJECT_STATUS.md`

**Steps**
- [ ] Approved seed reference -> whole four-column grid with consistent anchors, not independent frame generation. Use the approved smooth-v2 12/16-frame contracts for hero idle/sword/cast/hurt/defeat and Bifang idle/charge/strike/hurt/retreat.
- [ ] Original normalization scripts, inspect every pose/limb/one-leg, record source/frame dimensions/count/duration/anchor and DPR suitability.
  原参考图 canvas/色键工具配合 cartoon Lanczos 共同缩放规范化；
  九条旧四帧已检查并记录768像素、FPS与reference_height，不计为补帧完成；
  新规格按4A记录原生槽、704运行帧、实际内容与共同scale。
  退场畸形未通过、新挥剑候选被拒绝、最终DPR/实际动作体验尚未全验收，不打勾。
- [ ] Generate only the 9 spec card illustrations at 1536x1152; DOM renders readable text.
- [ ] Connect real sprite clips to ordered effects: sword/fire feather/shield/thunder/redirect/last hit. Reduced motion turns off shake/strong flashes without losing state feedback.
- [ ] Use actual current server and normal UI through three archetypes, choices, wins/deaths/reset/refresh/restart, unknown response/exact retry/409/401/late callbacks.
- [ ] Verify 1440x900,390x844,430x932,360x740 images/canvas changes/hitboxes; record timings and failures honestly.
- [ ] Independent whole-change review, BF-1 through BF-10 evidence and outstanding human judgement, tests/types/build/function checks, Chinese commit and branch push. No next milestone before full acceptance.
