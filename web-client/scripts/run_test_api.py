"""为浏览器 smoke 启动隔离 SQLite 的真实 M5 API。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import uvicorn


def main() -> None:
    """启动本机测试 API；数据库位于系统临时目录，进程退出后不污染仓库。"""
    repository_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository_root))
    from server.interface.roguelike_app import create_app

    database = Path(tempfile.gettempdir()) / f"unlimitworld-m5-e2e-{os.getpid()}.sqlite3"
    uvicorn.run(create_app(database), host="127.0.0.1", port=8787, log_level="warning")


if __name__ == "__main__":
    main()
