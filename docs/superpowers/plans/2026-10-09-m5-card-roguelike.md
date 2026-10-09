# M5 卡牌肉鸽实施计划

**Goal:** 交付全新国风怪诞漫画卡牌肉鸽浏览器样板局。
**Architecture:** Python 权威规则与 SQLite 独立存档；React DOM 界面与 Phaser 表现分离。
**Tech Stack:** React、TypeScript、Vite、Phaser、FastAPI、Pydantic、SQLite、pytest、Playwright。
**Spec:** `M5-card-roguelike.md`（用户已确认）。

## Global Constraints

- 初始生命 60；每回合 3 点灵力、抽 5 张牌；结束回合弃手牌，抽牌堆空时洗弃牌。
- 天谴每 30 点在回合结束触发 8 点雷罚，护盾可挡；死亡只由生命归零。
- 每场挑衅一次：灵力 +1、天谴 +8、敌人下一次攻击 +2。
- 18 种牌、6 法宝、三流派、4 普通敌人、1 精英、1 Boss、九层有限路线。
- 不接生产数据库、旧账号、支付、微信或真实 LLM，不修改旧客户端及旧规则。
- Domain 零框架依赖（纯 Pydantic 与纯函数）；接口 → 应用 → 领域，基础设施实现应用端口。
- 所有新增函数非空非注释行不超过 50；公开接口有用途、参数、返回及错误/副作用注释。
- Git 提交中文；每个独立阶段先文档、验证、commit、push。
- 前端禁止用模拟 API 返回值伪装规则完成；真实游戏规则在后端。
- 正式美术必须是真实原创位图；工具或授权缺失时明确缺口，不伪装完成。

## Task 1: 权威卡牌规则与独立存档 API

Ownership: 仅新增 `server/domain/roguelike/`、`server/application/roguelike/`、
`server/infrastructure/roguelike/`、`server/interface/roguelike_app.py`、
`server/tests/test_roguelike*.py`、`server/requirements-m5.txt`。
不要修改旧 domain、application、interface 文件，不修改文档与前端。

读取 Spec 的玩法及公共协议作为完整要求；实现真实内容而不是 mock。
模块按模型、目录、地图、牌堆、战斗、奖励/节点与存档职责拆分，禁止巨型统一规则函数。

接口：
- `create_app(db_path: str | Path = ".data/m5.sqlite3") -> FastAPI`；
  `app = create_app()` 供 uvicorn 使用，文件夹和连接只在生命周期或真实请求阶段创建。
- `GET /health`、`GET /api/v2/catalog`；
  `POST /api/v2/runs` 接受 `{archetype: "sword"|"fire"|"talisman"}`。
- `GET /api/v2/runs/{run_id}`、`POST /api/v2/runs/{run_id}/actions` 使用 Bearer 访问凭证。
- 响应 `{run: RunView, events: GameEvent[]}`；创建额外 `access_token`。
- 动作字段 `action_id`、`expected_revision`、`kind` 和类型化数据；
  类型覆盖 `choose_node/play_card/end_turn/taunt/choose_reward/skip_reward/choose_event/buy/remove_card/rest/upgrade_card/leave_shop`。
- Pydantic 明确描述局面和目录，生成可用 OpenAPI schema；
  实现后把实际动作 payload 与 schema 位置写入报告供前端读取。
- 公共模型必须完整显示选路、卡牌升级说明、敌人意图、雷罚预告、商店价格与状态、结算文本。
- 创建局面为 map 阶段；结束一次节点进入下一层；第九层只 Boss，终局不续图。
- SQLite 原子事务防止重复动作/并发扣款；非法动作不得落盘；
  缓存动作结果前比对请求内容，不能让同 action_id 的不同 payload 偷渡。
- 匿名访问凭证随机生成并安全比对；不是旧账号认证，不宣称生产可用。
- 历史只限该浏览器访问凭证所属档案，不能向任意访客曝光其他人的局面或战报。
- 随机源保存在服务端，刷新/重启不得重新抽奖励；固定种子入口只在规则测试，不公开客户端作弊参数。
- 函数注释、长度和架构符合 Global Constraints。

内容数值参考 Spec；完整实现十八牌与六法宝，消耗牌不参加战斗内洗牌。
敌人行动顺序、护盾清除、燃烧、虚弱、反伤和胜负优先级在测试中固定：
玩家手牌行动即时结算；结束回合时雷罚后敌方行动及燃烧结算；
任一方归零立即结束战斗，死者不继续行动；下一玩家回合清护盾、回灵力、抽牌。
本机因果属于匿名档案，可从已结束战报引用；无记录使用普通事件。

TDD：
- 先写规则/API/重启恢复行为测试，运行确认缺失规则失败，再实现。
- 覆盖剑意爆发、燃烧、反伤、引雷、雷罚 29/30/60、挑衅次数、零灵力、目标无效、消耗洗牌。
- 覆盖奖励生成持久化、地图锁定、Boss 终局、购物余额不足、重复购买、升级两次、移除最低牌数。
- 覆盖错误令牌、错版本、重复动作、同编号不同内容、两并发请求、非法动作不改变记录、重启续局。
- 至少一个可通过正常动作走到终局的 API 路径，不在生产接口加测试作弊动作。
- 测试报告包含 RED/GREEN 命令和真实输出；自查所有新增函数行数。
- 只提交自己文件，中文 commit；由主代理完成文档归档和推送。

## Task 2: 原创位图美术

Ownership: `web-client/public/assets/`、`docs/m5/art-direction.md`。
使用已授权的 ImageGen 路径生成一位修士、六敌人、两场景与十八法术插图，
保存原始提示词、工具身份和最终文件清单。没有授权不得访问收费 API。
同一漫画粗线条世界：夸张清晰剪影、朱红/青绿/亮黄与灰白中性色，
角色为透明底，场景不含文字或预嵌 UI，卡牌可读并统一比例。
先验证一张战斗关键屏的素材再扩展，不下载媒体绕过展示限制。
真实资源导入项目，禁止只放全局生成目录；不使用无来源素材。

## Task 3: 新 Web 客户端与游戏界面

Ownership: `web-client/`（不修改 public/assets）、根目录启动说明由主代理负责。
先读实际服务 OpenAPI 与任务 1 报告，不自行编造第二套协议。

- React + Vite + TypeScript，Phaser 场景读局面与表现事件；卡牌/菜单是 DOM。
- 通过 openapi-typescript 从独立服务的 OpenAPI 生成已提交的类型文件，
  类型生成需可离线重跑（先导出 schema 再生成），不依赖生产或旧服务。
- Vite 默认 5173，代理 `/api` 和 `/health` 到本地后端 8787；
  服务地址可用 env 覆盖，不硬编码生产域名。
- 开局真实三选一，已有档案优先续局；创建新局时沿用浏览器档案凭证以接入本机因果。
- 加载目录并渲染完整所有 phase；不为无法识别状态使用虚假的成功页面。
- 开局、地图、战斗、奖励、奇遇、商店、休整、牌组查看、胜负结算、重开、设置全可操作。
- 出牌需指定手牌实例及目标；选中查看，点敌人出牌，非指向牌可确认直接使用。
- 手牌手机横向滚动，桌面悬停；不依赖拖拽；稳定卡牌、命令栏和数值尺寸。
- 用 Lucide 的工具图标与 tooltip，不用 emoji 代替正式视觉资产。
- 完整文字标注能预告各卡牌、雷罚和挑衅的实际数值。
- 网络不确定时保留原动作编号可重试；409 读取快照；401 提供恢复或新局入口，不无限重试。
- localStorage 只存访问凭证、运行 ID 和设置；恢复校验，不上传任意局面。
- 命令进行中禁用重复交互，Phaser 动画不决定生死，不让过期异步请求覆盖新局。
- 角色/场景/法术都用统一 manifest；加载失败明确显示重试，不能默默用空画布。
- 提供动画、音效、音量、静音、减少动态效果与文档不干扰战场的设置菜单。
- 手机 390x844 / 430x932；桌面 1440x900；确保短屏 360x740 也可操作，无页面水平溢出。
- 版式为全宽战场，不做 dashboard，不做营销落地页，不叠层大卡片。
- 新增测试用真实 API 或真实状态边界，不以 mock 截图证明联通。
- 执行测试、类型检查、生产构建；中文 commit。
- 未有正式位图时明确标为美术待验收，不把占位可运行当作完整交付。

## Task 4: 集成验证、归档及本地试玩

Ownership: 验证脚本、启动器、说明、M5 与状态文档。
用 Playwright 实际操作开局、出牌、结束回合、奖励、选路、商店、休整、Boss/死亡、重开。
核验 HTTP 错误、刷新、恢复、手机/桌面截图、实际 PNG/WebP 加载和 canvas 非空像素。
截图写入项目验证目录，测试脚本可重复执行，必要时把发现写为回归测试。
完整运行新规则/API测试、前端测试/类型/构建、旧引擎/路线/事件池定向回归，
检查函数长度与 Git diff；既有全量风险单列，不能伪称全部通过。
记录 AC-1..AC-7 为通过/失败/阻塞/待人工认可。
补 M5 实施记录与 PROJECT_STATUS；只有必需项达标才能写阶段完成。
运行中文 commit 和 push 到隔离分支，不擅自合并 main 或部署。
启动本地前后端，给用户真实可用 URL；长驻服务使用隐藏后台窗口，
最终关闭所有非服务验证会话，不终止用户正在使用的服务。
