# Project Status：天道不正经

> 更新时间：2026-10-10
> 作用：本文件是当前开发进度的唯一入口。Codex 每次进入本项目时，先读本文件，再按需读取 `AGENTS.md` 和当前里程碑文档。

## 当前阶段

- **当前里程碑：** M5 卡牌肉鸽重做（用户已确认计划）
- **当前进度：** Task3可玩入口完成，旧九条四帧动作保留；Task4A多帧技术子单元及两轮限定复审通过。首张16帧挥剑因双剑/时序跳变拒绝，新补帧资源发布0条；完整Task4/M5未完成
- **下一阶段：** 另行确认一次针对性挥剑收费重试，合格样片接入并获体验认可后补其余12/16帧动作、毕方退场、九张卡面与最终法术表现。技术通路通过不等于实际流畅度或整套美术完成
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
- 原装 ImageGen 首轮启动三张高质量 2K/4K 请求，毕方的 SDK `b64_json` 读取值为 None，
  CLI fail-fast 退出 1，未保存任何新图。没有追加收费重试、擅换模型或改原装工具；
  已询问用户是否允许项目内专用适配器。其余任务的远端生成/收费状态未知。
- 用户随后要求用同一 API 再试。本次原装 CLI 仅重试毕方一次，
  提示词、`gpt-image-2/high/2048x3072` 不变；约 37.1 秒后仍在
  `b64_json` 为 None 时解码失败，退出 1，没有新图。
  未启动修士、场景或追加重试；收费未知，未获自定义适配器授权。
- 参数诊断：原装 dry-run 再次通过，模型列表鉴权实际返回 200；
  本机 SDK 在 Base64 字段缺失、显式 null、仅 URL 三种输入下均会读取为 None。
  原工具只处理 Base64，供应商公开生图页面兼容 Base64 与 URL；
  此差异不证明前次实际返回 URL。此前「返回 null」措辞予以纠正。
  供应商文档还提供 `gpt-image-2-4k`，但不能据此判定毕方尺寸被拒绝；
  没有修改模型或追加生图。证据与未决项见
  [图片 API 诊断](docs/m5/myth/image-api-diagnosis.md)。
- 用户随后确认解决问题，授权项目专用单张诊断/适配。本轮一次真实 POST
  返回 200，`data[0]` 只有 URL、没有 Base64 字段，确认原工具的解析不兼容。
  `tools/jojocode_image.py` 已支持 Base64、URL、data URL；无自动重试，
  图片下载不继承客户端认证、默认参数、头或 Cookie。
  原模型、提示词、质量与请求尺寸不变；毕方实际返回 2352×3520 PNG，
  9,105,945 bytes，已校验解码与摘要，未在本地插值放大。
  该尺寸高于请求的 2048×3072，但并不完全一致，不能冒充精确尺寸匹配。
  修士、场景和动作未追加生成，收费金额与供应商内部处理仍不可验证。
- 适配器经独立审查修复三项 Important 后复审通过；45 项回归通过，
  相关资源工具合计 84 passed、2 skipped；61 个函数无超长。
  脱敏真实响应见 `docs/m5/myth/image-response-20261009-1.json`。
  原图留在本工作区 `.data/imagegen/myth-seeds/diagnostic-20261009-1/`；
  本轮只修复图像工具，没有发布新版战场或将单张图写成三图验收完成。
- 2026-10-10 用户要求继续计划，修士与场景各一次请求成功：
  修士 2352×3520，场景 3840×2160，均未本地放大；使用原 API/模型/提示词，
  无自动重试，脱敏响应已保留。随后用户明确要求更卡通、诙谐幽默搞怪，
  认为当前太写实；三张写实图仅保留来源记录，不当作认可种子。
  写实资源未写入游戏 manifest，3B 实施已中止并保留交接；新卡面/动作未生成。
  原有写实提示词须替换，不再继续按原画面风格扩批。
- 2026-10-10 用户以「可以」确认国风动画与一本正经搞怪的单张样张方案。
  原 API/模型仅一次新请求成功，卡通毕方精确 2048×3072 PNG，
  3,570,719 bytes，无本地放大；保留独足、青身赤纹白喙。
  同画布透明预览来自本地色键处理，细羽仍有少量紫边、留白小于目标，
  仅供风格审核，尚未获得实际视觉认可，也未写入游戏 manifest。
  未请求新修士、场景、动作或卡面；旧写实来源记录不改写为认可。
  证据见 `docs/m5/myth/cartoon-provenance.json`。
- 随后用户查看实际毕方样张并反馈「这个可以」，毕方获得视觉认可。
  按该风格只补修士/场景各一张，原 API/模型不变，两项都成功，
  实际分别精确 2048×3072 与 3840×2160；无自动重试、本地放大、
  毕方重画、动作或卡面请求。两张配套图仍待实际视觉认可。
  修士同画布 alpha 与三图静态合成只用于审核，发丝少量紫边待精修，
  场景保留部分绘画纹理；合成不是动画或浏览器试玩证据。
  来源见 `docs/m5/myth/cartoon-companion-provenance.json`，
  原图、预览与合成参数在本工作区 `.data/imagegen/myth-seeds/` 保留。
- 2026-10-10 用户反馈「认可，战斗状态是 角色是会动的」：
  修士、毕方和章莪山三张卡通种子均获实际视觉认可（3/3）。
  恢复原计划 3B 与 Task 4；动作必须包含真实姿态变化，不能用静态立绘
  平移、缩放、晃动替代。种子认可不代表透明边缘、动作或整场试玩已验收。
- 参考图编辑扩展独立复审通过；原供应商/模型下十项动作各一次 POST，
  九项规范化条带已逐帧查看并发布到独立 myth 清单（animation-review）。
  每条四帧768×768、共同缩放脚锚；修士挥剑原图实际3840×1648，
  其余3840×1280，不本地上采样。毕方退场双腿/畸形喙拒绝，
  无重试；九张专属卡面尚未生成。动作仍待用户实际体验认可。
  当前表现 hook 生命周期与纹理切换缩小问题已修复；
  Task3技术入口在修复加载门控后独立复审通过，不冒充Task4已验收。
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

- 2026-10-10 用户反馈动作太卡：只读采样本机Chrome1440×900与390×844，
  5秒未见>50ms长帧，但修士仅4种姿态、20次变化（4fps）；
  这是本机浏览器调度/像素证据，不是实体手机性能保证。
  证据为 `.data/motion-diagnosis-20261010/report.json`。
  用户随后确认待机12帧12fps、攻击/施法16帧24fps、
  受击/倒地/退场12帧24fps，先做挥剑样片再展开全套。
  目前多帧技术子单元已过审，合格真实样片仍缺，M5/Task4未完成。
- 补帧首样片沿用原API/model/high，仅一次edit返回精确2816×2816、
  4,515,197 bytes，原图/脱敏响应已保留，无自动重试。
  人工检查确认第4帧双剑刃和连续姿态跳变，拒绝发布；
  实际画面仍为旧四帧，不能宣称卡顿已解决；新候选未接入manifest，
  未请求其他动作或九卡，追加收费重试尚未授权。
- Task4A技术源码HEAD `4d4025b`：多帧工具/运行时及两轮限定复审通过；
  resize等待悬挂、减少动态后resize比例错误均有RED/GREEN，最终无阻塞finding。
  控制器最终136 Vitest、43 Chrome（1.3分钟）、类型/构建、71文件函数检查通过；
  本轮Python182 passed/2权限跳过，后续前端修复未改Python，159相关函数无超长。
  正常UI真服攻击、刷新、四视口像素/命中/截图核对通过，pageerror0；
  synthetic16/12帧只验证引擎，不是新正式美术或实体手机性能保证。
  中间终局fixture旧revision竞态导致41/1失败，修正后43/43；原失败日志保留，
  原trace ZIP未另行归档。既有Vite退出根因和Phaser包体风险仍未解决；
  390/360顶部资源条末项旧裁切及全套资源内存/DPR继续待处理。
  当前只归档已复审技术子单元与失败图片证据，不标记完整4A/4B/M5完成。
  归档 `87b4b1f` 已推送隔离分支，远端完整SHA核对一致；
  此后只补推送事实，不改变已验证源码与未发布的样片状态。

- 2026-10-10 3B 可见场景与真实逐帧动作当前修复HEAD `c622716`：
  121 Vitest通过，类型/构建/68源码文件函数检查通过；
  当前服务完整Chrome38 passed（经典29+神话9，45.8秒）。
  正常UI真服胜局与败局、刷新/重开、四视口截图和实际像素变化已核对。
  独立审查两个Important（减少动态延迟导入旧值、条带失败仍ready）及
  清单协议Minor已修复；延迟import/真实Phaser404均有RED/GREEN，限定复审双PASS，
  无新增Critical/Important。旧草稿OOM是已修复的历史失败，不再当作当前阻塞。
  九动作仍待用户体验认可，退场/九卡画/最终VFX未完成。
  原始最终输出在工作区 `.data/myth-final-{unit,chrome,python,build}.log` 保留。
  Task3B文档归档`b7c237b`已推送隔离分支，远端完整SHA核对一致；
  后续推送事实记录不改变验证源码。
- 首次3B最终E2E期间5173 Node于2026-10-10 12:45:16以`0xC0000409`退出，
  最初测试和控制器胜局试玩连接失败。保留诊断、恢复同工作区服务后复跑通过；
  native根因未定位，不称环境问题彻底修复。Phaser包体与runner提示继续保留。
- 2026-10-10 动作资源/工具当前版本：相关 Python 172 passed、2 skipped；
  聚焦工具83 passed、2 skipped，147函数无超长，diff检查通过。
  edit 唯一POST/无fallback、帧去重、首帧锁/共同scale、原子发布、
  断开配件拒绝/显式保留及实际发布PNG/摘要/manifest一致性均有回归。
  工具独立复审无新增Critical/Important；十个实际生成进程均已结束。
  两项skipped是Windows符号链接创建权限。细羽/发缘残留色键仍是风险，
  不把种子尺寸或自动测试当作最终动作清晰度与美术认可。

- 2026-10-10 配套卡通种子：适配器 45 passed；两个原 PNG 完整解码、
  精确目标尺寸、来源摘要与脱敏响应一致。修士 alpha 保持 2048×3072，
  不透明像素 RGB 改动为 0；4K 静态合成未放大角色、未改场景画布，
  两个角色完整在图内且共用脚底线。已查看实际原图、alpha 和合成；
  当时用户仅认可毕方；最新三种子3/3已认可。正式透明边缘与
  全部真实动作体验仍未最终验收。
- 2026-10-10 卡通毕方单张样张：适配器 45 passed；真实响应、请求摘要、
  PNG 完整解码、字节数与 SHA256 一致性通过。原图与两版 alpha 画布均为
  2048×3072，保留原图，无插值；预览不透明像素 RGB 改动为 0。
  已人工查看原图与两版去底预览；卡通程度、幽默感仍待用户评价。
  本轮只生成样张和记录来源，不运行或宣称新的前端、动作及整局验收。
- 2026-10-10 此前中止时的未提交 3B 草稿尚未接入主入口，新行为用例未转绿，
  表现 hook 测试发生 OOM；无新场景截图/E2E 证据。恢复时先定位循环，
  不将此前 3A 或经典模式的绿色结果冒充草稿已验证。
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
  原装 API 单张重试失败证据保留，原装工具摘要未改变；
  随后专用适配器一次真实请求成功取回 2352×3520 毕方图，
  45 项适配器测试及 84 passed、2 skipped 的相关资源工具验证通过。
  当时仍缺修士/场景种子；随后取得的三张写实图已被用户否定其方向。
  新卡通方向的三张原图现已取得，仅毕方获认可；仍缺正式边缘精修、
  修士/场景认可、动作帧与毕方前端试玩验收。
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
- 本地试玩：新版 `http://127.0.0.1:5173/myth`，经典 `http://127.0.0.1:5173/`。
  分支 `codex/m5-card-roguelike`，
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
