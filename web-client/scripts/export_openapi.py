"""离线导出 M5 FastAPI OpenAPI；输入为仓库代码，输出到命令行指定文件。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    """导出 app.openapi()；需要输出路径，失败时以非零状态退出。"""
    repository_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository_root))
    from server.interface.roguelike_app import app

    output_path = Path(sys.argv[1]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
