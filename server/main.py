"""
天道不正经 入口

M1 CLI:   python -m server.main
M2 服务器: python -m server.main --server
"""

import sys
import asyncio
from pathlib import Path

# 确保项目根目录在 PYTHONPATH 中
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

if __name__ == "__main__":
    if "--server" in sys.argv:
        from server.config import settings
        import uvicorn

        uvicorn.run(
            "server.interface.app:app",
            host=settings.server_host,
            port=settings.server_port,
            reload=settings.app_env == "development",
        )
    else:
        from server.interface.cli import cli_main
        asyncio.run(cli_main())
