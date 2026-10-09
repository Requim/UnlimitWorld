# M5 本地样板试玩

此版本与旧微信客户端、旧数据库和生产服务完全分离。
存档使用项目下 `.data/m5.sqlite3`；浏览器仅保留匿名凭证、运行编号和设置。
清除浏览器凭证后无法恢复原匿名档案，重装服务不会自动迁移旧账号。

## 安装

项目根目录（Windows PowerShell）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r server/requirements-m5.txt
cd web-client
npm ci
cd ..
```

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File tools/start-m5.ps1
```

启动器使用隐藏窗口，只绑定 `127.0.0.1`，不会关闭已有服务。
默认网页端口 5173、API 端口 8787；占用时自动换空闲端口，
实际地址及进程编号写入 `.data/m5-services.json` 并显示在输出中。
重复启动会复用健康的同工作区服务。
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
.\.venv\Scripts\python.exe -m pytest server/tests/test_roguelike_rules.py server/tests/test_roguelike_api.py tests/test_function_lengths.py -q
cd web-client
npm test
npm run typecheck
npm run build
```

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
当前是 `pending-generation`，并没有将不存在的图片标记为已交付。
等待图片生成能力授权及本机 API Key 后，按 `art-direction.md` 生成并验证
7 个角色、2 个场景和 18 个法术插图，再切换状态并验收真实加载结果。
