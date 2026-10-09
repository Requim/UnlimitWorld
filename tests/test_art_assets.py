"""Formal art checks must distinguish pending resources from delivered bitmaps."""

import json
from pathlib import Path

from tools.check_art_assets import inspect_assets


def _manifest(root: Path, status: str) -> None:
    values = {
        "status": status,
        "characters": {"cultivator": "/assets/characters/cultivator.png"},
        "enemies": {str(i): f"/assets/enemies/{i}.png" for i in range(6)},
        "backgrounds": {str(i): f"/assets/backgrounds/{i}.webp" for i in range(2)},
        "cards": {str(i): f"/assets/cards/{i}.webp" for i in range(18)},
    }
    (root / "manifest.json").write_text(json.dumps(values), encoding="utf-8")


def test_pending_is_blocked_not_passed(tmp_path: Path) -> None:
    _manifest(tmp_path, "pending-generation")
    result = inspect_assets(tmp_path)
    assert result.status == "blocked"
    assert result.asset_count == 27


def test_ready_without_files_is_failed(tmp_path: Path) -> None:
    _manifest(tmp_path, "ready")
    result = inspect_assets(tmp_path)
    assert result.status == "failed"
    assert len(result.errors) == 27


def test_asset_path_cannot_escape_root(tmp_path: Path) -> None:
    _manifest(tmp_path, "ready")
    content = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    content["characters"]["cultivator"] = "/assets/../../outside.png"
    (tmp_path / "manifest.json").write_text(json.dumps(content), encoding="utf-8")
    result = inspect_assets(tmp_path)
    assert any("outside asset root" in error for error in result.errors)


def test_unknown_manifest_status_is_failed(tmp_path: Path) -> None:
    _manifest(tmp_path, "fake-complete")
    assert inspect_assets(tmp_path).status == "failed"


def test_non_object_manifest_is_failed(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text("[]", encoding="utf-8")
    assert inspect_assets(tmp_path).status == "failed"


def test_duplicate_urls_cannot_count_as_full_art(tmp_path: Path) -> None:
    _manifest(tmp_path, "ready")
    path = tmp_path / "manifest.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    content["cards"]["1"] = content["cards"]["0"]
    path.write_text(json.dumps(content), encoding="utf-8")
    assert any("reuse" in error for error in inspect_assets(tmp_path).errors)


def _bitmaps(root: Path) -> None:
    from PIL import Image, ImageDraw

    content = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for group in ("characters", "enemies", "backgrounds", "cards"):
        for url in content[group].values():
            path = root / url.removeprefix("/assets/")
            path.parent.mkdir(parents=True, exist_ok=True)
            size = (512, 256) if group == "backgrounds" else (256, 192)
            image = Image.new("RGBA", size, (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((16, 16, 200, 170), fill=(200, 20, 20, 255))
            image.save(path)


def test_real_bitmap_formats_can_pass_file_checks(tmp_path: Path) -> None:
    _manifest(tmp_path, "ready")
    _bitmaps(tmp_path)
    result = inspect_assets(tmp_path)
    assert result.status == "passed"
    assert result.asset_count == 27


def test_opaque_actor_is_rejected(tmp_path: Path) -> None:
    from PIL import Image

    _manifest(tmp_path, "ready")
    _bitmaps(tmp_path)
    path = tmp_path / "characters" / "cultivator.png"
    Image.new("RGB", (256, 192), "white").save(path)
    assert any("transparent" in error for error in inspect_assets(tmp_path).errors)
