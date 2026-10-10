# Task 4A 多帧规范化与运行时集成报告

## 状态

`DONE_WITH_CONCERNS`

技术通路已完成并通过受控合成素材验证；真实 `hero_sword` 候选因第 4 帧双剑和时序跳变被视觉门控拒绝，未发布正式 PNG、manifest 或 provenance。Task 4B 与实际样片认可不在本实施单元范围。

## 实际改动

- `tools/prepare_myth_animation.py`
  - 保留 legacy 四横帧行为，新增显式 `smooth-v2`、`frame_count`、`source_columns`。
  - 按 4 列行优先读取 12/16 帧，严格校验动作对应帧数/FPS、网格整除、空帧、相邻重复和最少唯一姿态数。
  - smooth 源槽每边必须至少 704；共享缩放为 `min(1, 704 / max_content)`，允许 704 原生槽内主体只有 620 高，不放大透明留白中的主体。
  - 首帧种子仅向下匹配源第一帧实际内容高度，最终统一底部居中并输出真实 4 列图集。
  - 元数据新增 profile、columns、rows、source size、source slot size；仍执行 99.8% alpha 归属门控和事务发布。
- `tests/test_myth_animation_assets.py`
  - 覆盖 12/16 帧成功路径、704 槽/620 内容留白、低于 704 源槽拒绝、严格档位、网格、空帧、重复帧、唯一数和首帧锁定。
- `web-client/src/myth/mythAssets.ts`、`mythAssets.test.ts`
  - manifest 可选识别 `smooth-v2`；legacy 不得偷带网格字段，新档位按动作键严格核验 704/4 列/3 或 4 行/12 或 24 FPS。
- `web-client/src/myth/mythClipPlayback.ts`、`mythClipPlayback.test.ts`
  - 新增小型播放模块，等待 Phaser 精确 `animationcomplete-<key>`，统一 AbortSignal、解绑、场景销毁和终局动作判定。
- `web-client/src/myth/createMythGame.ts`
  - 移除固定 900ms 截断；事件片段等待真实完成，取消后不再继续后续片段。
  - generation 隔离旧回调；destroy/减少动态使在途播放失效；败北/退场保留末帧直到结算。
  - 保持旧边界：strip 加载失败仍锁命令但场景 ready，减少动态继续短反馈，idle 正常循环。
- `web-client/e2e/myth.spec.ts`
  - 使用 `page.route` 注入单 clip 合成 4x4/4x3 SVG 图集，不增加对外 debug API。
  - 验证真实 Phaser 16 帧行优先顺序、减少动态取消、12 帧终局末帧保持；截图只代表技术 fixture，不代表生产美术或用户认可。

正式资源、正式 manifest、控制器维护的阶段文档和拒绝候选 provenance 均未由本提交修改。

## CLI

```powershell
.venv\Scripts\python.exe tools\prepare_myth_animation.py `
  --input <source-grid.png> --anchor <approved-seed.png> --out-dir <new-output-dir> `
  --name hero_sword --profile smooth-v2 --frame-count 16 --source-columns 4 `
  --frame-size 704 --fps 24
```

输出目录必须不存在。12 帧动作将 `--frame-count` 改为 12，并按 brief 使用 12 或 24 FPS。工具不写 manifest。

## RED / GREEN

### Python 规范化

- RED：`.venv\Scripts\python.exe -m pytest tests\test_myth_animation_assets.py -q`
  - 初始结果：10 failed、14 passed；缺少 profile/frame_count/source_columns 及新档位实现。该次仅保留在任务终端记录，未伪造补写日志。
- GREEN：同命令，24 passed in 2.74s。
  - 输出：`.data/playtest-myth-smooth-4a/python.log`

### manifest 与播放 helper

- RED：`npm test -- --run src/myth/mythAssets.test.ts src/myth/mythClipPlayback.test.ts`
  - 初始结果：5 个 smooth 契约失败且 helper 模块不存在；另有一次 legacy 携带 columns/rows 被错误接受的 1 条 RED。仅保留在任务终端记录。
- GREEN：聚焦 assets/helper/create/game-animation 共 44 passed；最终全量 Vitest 为 28 files、136 passed。
  - 输出：`.data/playtest-myth-smooth-4a/unit.log`

### 浏览器契约

- 真实业务 RED：将取消门限收紧到 300ms 后，旧实现取消当前 `hero_sword` 仍继续 `bifang_hurt`，`data-presentation-busy` 未及时复位；修复为片段返回 cancelled 后立即停止事件余下片段。
- 测试工具问题：早期采样器在 canvas 尚未挂载/已销毁时取 `getContext`，不计作业务 RED；修正生命周期后才执行帧序断言。
- 首次完整 Chrome 40 passed / 1 failed：取消 fixture 使用 `end-turn` 未证明合成动作已提交；保留于 `.data/playtest-myth-smooth-4a/full-chrome.log`。
- 第二次串行完整 Chrome 40 passed / 1 failed：POST 已收到且无 pageerror，但重复的精确 RGB 等待探针未命中；这是采样探针问题，保留于 `.data/playtest-myth-smooth-4a/full-chrome-serial.log`。最终 fixture 改为合成图集实际请求完成、`taunt` POST 类型、busy 进入与 300ms 取消的直接证据；16 帧精确像素序列由相邻独立用例负责。
- GREEN 聚焦：`npx playwright test e2e/myth.spec.ts -g 'synthetic smooth-v2 (挥剑|演出)' --workers=1 --reporter=line`，2 passed。
  - 输出：`.data/playtest-myth-smooth-4a/focused-cancel-final.log`
- GREEN 全量 Chrome：`npx playwright test --workers=1 --reporter=line`，41 passed in 1.2m。
  - 输出：`.data/playtest-myth-smooth-4a/full-chrome-final.log`

另一次并行全量在前 5 条通过后，Playwright 管理的原生 Vite 进程提前退出，最终 exit code 1、5 passed / 36 failed，后续失败均为 5173 `ECONNREFUSED` 或等待根节点；该次原始输出保留在任务执行记录。随后未修改 launcher，也未宣称根因修复；使用既有 `tools/start-m5.ps1` 恢复持久 5173/8787，再复用服务以单 worker 完成上述 41/41。

## 最终验证

- Python：24 passed。
- Vitest：28 files、136 passed。
- TypeScript：`npm run typecheck` 通过；输出 `.data/playtest-myth-smooth-4a/typecheck.log`。
- 构建：`npm run build` 通过；输出 `.data/playtest-myth-smooth-4a/build.log`。
- Chrome：41 passed；合成 16 帧顺序、取消、12 帧终局均包含在内。
- 函数长度：Python 42 个函数、前端 src 70 个函数，均无超过 50 个有效行；输出 `python-functions.log`、`frontend-functions.log`。
- 截图：`synthetic-hero-sword-mid.png`、`synthetic-cancelled-to-seed.png`、`synthetic-bifang-retreat-final.png`，均位于 `.data/playtest-myth-smooth-4a/`，只作技术验证。

## 自审

- 未加入插值、复制帧、动态补帧或静态图伪动作。
- 未改变经典模式接口、现有插件、正式资源或 UI 文案。
- legacy 仍拒绝低清上采样；smooth 仅允许原生至少 704 槽中的透明留白，不会放大主体。
- 取消、destroy、减少动态和新一代播放均解绑旧回调；终局末帧不被 idle 抢回。
- 公开 TypeScript/Python 接口均补充用途、入参/返回及关键错误或副作用注释。
- 新增职责拆入独立 helper，未把等待逻辑继续堆入长函数。

## 限制与关注项

- 真实候选 `.data/imagegen/myth-smooth/hero-sword-16-1/hero-sword-smooth-sheet.png` 虽通过 2816x2816、16x704、source slot 704、scale 1、reference height 594 和 hash 技术门控，但因双剑与时序问题被拒绝；本任务没有真实新动作样片交付，也没有用户认可结论。
- 单张 2816x2816 RGBA 理论解码约 31.7 MB（约 30.3 MiB）；未来 12/16 帧全套会显著增加加载与内存。本阶段未发布，不扩建 LOD/压缩架构。
- 受控单 clip 在本机 Chrome 通过，不能代表实体手机加载全套资源的性能；原生 704 槽、实际约 594 内容高度也不能等同 768 细节或全 DPR 保证。
- 构建仍有 Phaser 约 1,350.47 kB（gzip 350.57 kB）大 chunk 警告；Vitest 仍有 jsdom runner 性能提示。
- Windows 原生开发服务器提前退出的历史风险仍未定位；最终串行验证只隔离了业务正确性，没有修复或掩盖该风险。
