"""Check manifest-backed bitmaps; pending art is blocked, never a successful check."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class AssetReport:
    """Asset status, inspected count, and concrete validation errors."""

    status: Literal["passed", "failed", "blocked"]
    asset_count: int = 0
    errors: list[str] = field(default_factory=list)


def inspect_assets(root: Path) -> AssetReport:
    """Inspect a local asset directory; return blocked for pending, failed for invalid files."""
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        entries = _entries(manifest)
    except (OSError, ValueError, TypeError) as exc:
        return AssetReport("failed", errors=[str(exc)])
    if manifest.get("status") == "pending-generation":
        return AssetReport("blocked", len(entries))
    if manifest.get("status") != "ready":
        return AssetReport("failed", len(entries), ["Unknown manifest status"])
    errors = []
    for group, key, url in entries:
        error = _inspect_file(root, group, url)
        if error:
            errors.append(f"{group}/{key}: {error}")
    return AssetReport("failed" if errors else "passed", len(entries), errors)


def _entries(manifest: dict) -> list[tuple[str, str, str]]:
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be a JSON object")
    entries = []
    expected = {"characters": 1, "enemies": 6, "backgrounds": 2, "cards": 18}
    for group, count in expected.items():
        values = manifest.get(group)
        if not isinstance(values, dict) or len(values) != count:
            raise ValueError(f"{group}: expected {count} manifest entries")
        for key, url in values.items():
            if not isinstance(url, str) or not url.startswith("/assets/"):
                raise ValueError(f"{group}/{key}: invalid asset URL")
            entries.append((group, key, url))
    if len({url for _, _, url in entries}) != len(entries):
        raise ValueError("Formal assets must not reuse one image URL")
    return entries


def _inspect_file(root: Path, group: str, url: str) -> str | None:
    path = (root / url.removeprefix("/assets/")).resolve()
    if not path.is_relative_to(root.resolve()):
        return "outside asset root"
    if not path.is_file():
        return "missing bitmap"
    try:
        from PIL import Image
    except ImportError:
        return "Pillow is required: install tools/requirements-qa.txt"
    try:
        with Image.open(path) as image:
            image.load()
            return _inspect_bitmap(image, group)
    except (OSError, ValueError) as exc:
        return f"invalid bitmap: {exc}"


def _inspect_bitmap(image, group: str) -> str | None:
    if image.format not in {"PNG", "WEBP"}:
        return "expected real PNG or WebP"
    width, height = image.size
    minimum = (512, 256) if group == "backgrounds" else (256, 192)
    if width < minimum[0] or height < minimum[1]:
        return f"bitmap too small: {width}x{height}"
    if group in {"characters", "enemies"}:
        alpha = image.convert("RGBA").getchannel("A").getextrema()
        if alpha[0] == 255 or alpha[1] == 0:
            return "character needs visible pixels and transparent background"
    if group == "cards" and not 1.2 <= width / height <= 1.5:
        return "card illustration must preserve the 4:3 display composition"
    return None


def main() -> int:
    """Check assets from CLI; exit 0 passed, 1 failed, 2 blocked without changing files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("web-client/public/assets"))
    args = parser.parse_args()
    report = inspect_assets(args.root)
    print(f"Art {report.status}: {report.asset_count} manifest assets")
    for error in report.errors:
        print(error)
    return {"passed": 0, "failed": 1, "blocked": 2}[report.status]


if __name__ == "__main__":
    raise SystemExit(main())
