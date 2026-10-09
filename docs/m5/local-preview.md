# M5 本地样板试玩

此版本与旧微信客户端、旧数据库和生产服务完全分离。
存档使用项目下 `.data/m5.sqlite3`；浏览器仅保留匿名凭证、运行编号和设置。
清除浏览器凭证后无法恢复原匿名档案，重装服务不会自动迁移旧账号。

## 安装

项目根目录（Windows PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements-m5.txt
.\.venv\Scripts\python.exe -m pip install -r tools/requirements-qa.txt
cd web-client
npm ci
cd ..
```

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-m5.ps1
```

启动器使用隐藏窗口，只绑定 `127.0.0.1`，不会关闭无关进程。
默认网页端口 5173、API 端口 8787；占用时自动换空闲端口，
实际地址及进程编号写入 `.data/m5-services.json` 并显示在输出中。
重复启动会复用健康的同工作区服务。
部分服务退出时复用仍健康的 API；API 重启后仅重启同工作区的托管网页进程。
网页子进程设置 `CI=true`，避免后台输入流关闭导致 Vite 自动退出。
隐藏 PowerShell 宿主持续持有网页进程和日志流，退出状态记录在
`.data/m5-web-lifecycle.log`；不是自动重启守护器。
日志为 `.data/m5-api*.log`、`.data/m5-web*.log`。

也可开两个终端手动运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.interface.roguelike_app:app --host 127.0.0.1 --port 8787
```

```powershell
cd web-client
npm run dev
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest server/tests/test_roguelike_rules.py server/tests/test_roguelike_api.py tests/ -q
node --test tests/playtest-policy.test.mjs tests/playtest-canvas.test.mjs tests/playtest-selection.test.mjs
node tools/playtest-m5.mjs --url http://127.0.0.1:5173 --out .data/playtest
cd web-client
npm test
npm run typecheck
npm run build
npx playwright test --config playwright.external.config.ts --workers=1
```

完整浏览器脚本使用本机 Chrome；可用 `PLAYWRIGHT_CHANNEL` 改为已安装的浏览器通道。
它只使用正常游戏动作，不注入测试局面；截图和 JSON 结果写入被忽略的 `.data/`。
`playwright.external.config.ts` 只复用已启动的 5173/8787 服务，不自行启停进程。
Playwright 通道可用 `M5_BROWSER_CHANNEL` 覆盖。
正式素材未生成时，技术路径通过也不代表美术通过。
画布非空检测采样实际浏览器 PNG，并隐藏 DOM 战斗覆盖层；
不读取 WebGL 非保留绘制缓冲，也不以该检查代替角色取景与视觉验收。
更新检查通过真实设置启用减少动态，用同尺寸的静态前后帧验证正常挑衅；
不注入刷新初始化来覆盖被测设置。已选卡牌不再次点击取消后强制出牌。
浏览器验证命令和验收结果补充于 `M5-card-roguelike.md` 的当前实施记录。
旧全量测试存在已记录的失败；新样板测试通过不能替代旧版本验收。

美术文件检查（不代替原创来源与人工视觉验收）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r tools/requirements-qa.txt
.\.venv\Scripts\python.exe tools/check_art_assets.py
```

返回状态 `blocked` 表示正式位图仍未交付，不是测试通过。

## 美术状态

`public/assets/manifest.json` 明确声明资源状态与正式路径。
当前为 `ready`：7 个透明角色、2 个场景和 18 个法术插图已在项目中，
真实浏览器全部解码通过；生成与整理记录见 `art-direction.md`，
最终文件摘要见 `art-provenance.json`。运行样板不需要图片 API Key。
自动技术检查不替代用户对美术和好玩程度的认可，M5 整体仍未完成。

原图还在当前工作区 `.data/imagegen/output/` 时，可以不调用 API 重新整理：

```powershell
.\.venv\Scripts\python.exe tools/prepare_art_assets.py --source-dir .data/imagegen/output --force --report docs/m5/art-provenance.json
.\.venv\Scripts\python.exe tools/check_art_assets.py
```

整理器缺少原图/去底图、图片比例不符、路径越界或未允许覆盖时会失败，
不会自动把 manifest 标记为 `ready`。供应商生成请求不属于游戏启动流程。
