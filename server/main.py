"""
天道不正经 M1 CLI 入口
"""

import sys
import asyncio
from pathlib import Path

# 确保项目根目录在 PYTHONPATH 中
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from server.interface.cli import cli_main


if __name__ == "__main__":
    asyncio.run(cli_main())
