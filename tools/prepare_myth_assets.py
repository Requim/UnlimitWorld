"""Package myth seed images at their actual native resolution without generation."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from PIL import Image


SEEDS = {
    "hero": ("hero-seed.png", "hero-alpha.png", "hero.png", (2048, 3072)),
    "bifang": ("bifang-seed.png", "bifang-alpha.png", "bifang.png", (2048, 3072)),
    "scene": ("zhang-e-mountain-seed.png", None, "zhang-e-mountain.webp", (3840, 2160)),
}


def prepare_seeds(source_dir: Path, asset_root: Path, report_path: Path | None = None) -> dict:
    """Validate and transactionally publish three native-size myth seed files.

    Args:
        source_dir: Directory containing original PNGs and provided alpha cutouts.
        asset_root: Independent myth asset directory that receives seeds and manifest.
        report_path: Optional JSON evidence file published in the same transaction.

    Returns:
        Provenance data with actual sizes, hashes, alpha method, visible pixel bounds
        and target status. Bounds use left/top/right/bottom with exclusive far edges.

    Raises:
        OSError or ValueError for invalid input, unsafe paths, encoding, validation or
        publication failures. No resizing or generation occurs. A failure removes only
        files created by this invocation and restores a replaced blocked manifest.
        Existing seed and report files are rejected before staging.
    """
    source, root = source_dir.resolve(), asset_root.resolve()
    manifest_path = _bounded(root, "manifest.json")
    report_target = report_path.resolve() if report_path else None
    _validate_manifest_slot(manifest_path)
    _validate_report_slot(report_target)
    prepared = [_prepare(key, spec, source, root) for key, spec in SEEDS.items()]
    with TemporaryDirectory(prefix=".myth-stage-", dir=_existing_ancestor(root)) as directory:
        stage = Path(directory)
        report = _stage_bundle(prepared, stage)
        plan = _publication_plan(prepared, stage, manifest_path, report_target, report)
        _publish_transaction(plan, stage / "backups")
    return report


def _validate_manifest_slot(path: Path) -> None:
    if not path.exists():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Invalid manifest object")
    recoverable = (
        manifest.get("version") == "bifang-v1"
        and manifest.get("status") == "blocked-generation"
        and all(manifest.get(key) == {} for key in ("seeds", "animations", "cards"))
    )
    if not recoverable:
        raise FileExistsError(path)


def _validate_report_slot(path: Path | None) -> None:
    if path and path.exists():
        raise FileExistsError(path)


def _bounded(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Image path outside intended root")
    return target


def _existing_ancestor(path: Path) -> Path:
    current = path.parent
    while not current.exists():
        current = current.parent
    return current


def _load(path: Path) -> Image.Image:
    if not path.is_file():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        image.load()
        return image.copy()


def _prepare(key: str, spec: tuple, source: Path, root: Path) -> dict:
    original, alpha, output, expected = spec
    raw_path = _bounded(source, original)
    input_path = _bounded(source, alpha or original)
    target = _bounded(root, f"seeds/{output}")
    if target.exists():
        raise FileExistsError(target)
    raw, image = _load(raw_path), _load(input_path)
    if image.size != raw.size:
        raise ValueError(f"{key}: alpha canvas size differs from original")
    image = _validate_alpha(key, image) if alpha else image.convert("RGB")
    return {
        "key": key, "raw_path": raw_path, "input_path": input_path,
        "target": target, "image": image, "expected": expected,
        "source_size": raw.size, "alpha": bool(alpha),
    }


def _validate_alpha(key: str, image: Image.Image) -> Image.Image:
    converted = image.convert("RGBA")
    minimum, maximum = converted.getchannel("A").getextrema()
    if minimum == 255 or maximum == 0:
        raise ValueError(f"{key}: genuine visible alpha required")
    return converted


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _stage_bundle(prepared: list[dict], stage: Path) -> dict:
    assets = {item["key"]: _stage_asset(item, stage) for item in prepared}
    report = {
        "version": "bifang-v1", "status": "seed-review",
        "model_requested": "gpt-image-2", "quality_requested": "high",
        "dimensions_met": all(item["native_target_met"] for item in assets.values()),
        "assets": assets,
    }
    _write_json(stage / "manifest.json", _manifest(report))
    return report


def _stage_asset(item: dict, stage: Path) -> dict:
    output = stage / "seeds" / item["target"].name
    output.parent.mkdir(parents=True, exist_ok=True)
    if item["alpha"]:
        item["image"].save(output, format="PNG", optimize=True)
    else:
        item["image"].save(output, format="WEBP", quality=92, method=6)
    _validate_staged_image(output, item)
    return {
        "url": f"/assets/myth/seeds/{output.name}",
        "requested_size": list(item["expected"]),
        "source_size": list(item["source_size"]), "output_size": list(item["image"].size),
        "visible_bounds": list(item["image"].getchannel("A").getbbox()) if item["alpha"]
        else [0, 0, *item["image"].size],
        "native_target_met": item["source_size"] == item["expected"],
        "alpha_method": "provided-alpha-cutout" if item["alpha"] else "not-applicable",
        "source_sha256": _digest(item["raw_path"]),
        "prepared_input_sha256": _digest(item["input_path"]),
        "output_sha256": _digest(output), "bytes": output.stat().st_size,
    }


def _validate_staged_image(path: Path, item: dict) -> None:
    with Image.open(path) as image:
        image.load()
        if image.size != item["source_size"]:
            raise ValueError(f"{item['key']}: staged image size changed")
        if item["alpha"]:
            _validate_alpha(item["key"], image)


def _manifest(report: dict) -> dict:
    return {
        "version": report["version"], "status": report["status"],
        "dimensions_met": report["dimensions_met"],
        "seeds": {key: {"url": value["url"], "size": value["output_size"],
                        "bounds": value["visible_bounds"]}
                  for key, value in report["assets"].items()},
        "animations": {}, "cards": {},
    }


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if loaded != value:
        raise ValueError(f"Staged JSON validation failed: {path.name}")


def _publication_plan(prepared: list[dict], stage: Path, manifest: Path,
                      report_path: Path | None, report: dict) -> list[tuple[Path, Path]]:
    plan = [(stage / "seeds" / item["target"].name, item["target"])
            for item in prepared]
    plan.append((stage / "manifest.json", manifest))
    if report_path:
        staged_report = stage / "report.json"
        _write_json(staged_report, report)
        plan.append((staged_report, report_path))
    destinations = [destination for _, destination in plan]
    if len(set(destinations)) != len(destinations):
        raise ValueError("Publication destinations must be unique")
    return plan


def _publish_transaction(plan: list[tuple[Path, Path]], backup_root: Path) -> None:
    published: list[tuple[Path, Path | None]] = []
    created_dirs: list[Path] = []
    try:
        for index, (staged, destination) in enumerate(plan):
            _create_parent_dirs(destination.parent, created_dirs)
            backup = _backup_existing(destination, backup_root / f"{index}.bak")
            staged.replace(destination)
            published.append((destination, backup))
    except OSError:
        _rollback(published, created_dirs)
        raise


def _create_parent_dirs(parent: Path, created: list[Path]) -> None:
    missing, current = [], parent
    while not current.exists():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        directory.mkdir()
        created.append(directory)


def _backup_existing(destination: Path, backup: Path) -> Path | None:
    if not destination.exists():
        return None
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(destination, backup)
    return backup


def _rollback(published: list[tuple[Path, Path | None]], created_dirs: list[Path]) -> None:
    for destination, backup in reversed(published):
        if backup:
            backup.replace(destination)
        elif destination.exists():
            destination.unlink()
    for directory in reversed(created_dirs):
        if directory.exists():
            directory.rmdir()


def _size_summary(report: dict) -> str:
    return ", ".join(
        f"{key}:{value['output_size'][0]}x{value['output_size'][1]}"
        for key, value in report["assets"].items()
    )


def main() -> int:
    """Run the packaging CLI; return 0 on success or 1 after a rollback-safe error.

    Command-line inputs select the source directory, myth asset root and optional
    report destination. Successful execution publishes all outputs together and
    prints actual dimensions; failures print the cause and leave prior files intact.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, default=Path("web-client/public/assets/myth"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = prepare_seeds(args.source_dir, args.asset_root, args.report)
        print("Prepared 3 files without resizing; "
              f"dimensions_met={report['dimensions_met']}; sizes={_size_summary(report)}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Myth seed preparation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
