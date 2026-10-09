"""Package myth seed images at their actual native resolution without generation."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image


SEEDS = {
    "hero": ("hero-seed.png", "hero-alpha.png", "hero.png", (2048, 3072)),
    "bifang": ("bifang-seed.png", "bifang-alpha.png", "bifang.png", (2048, 3072)),
    "scene": ("zhang-e-mountain-seed.png", None, "zhang-e-mountain.webp", (3840, 2160)),
}


def prepare_seeds(source_dir: Path, asset_root: Path) -> dict:
    """Validate all seeds, write native-size files/manifest, return provenance.

    source_dir contains original PNGs and original-tool alpha cutouts. asset_root
    is the independent myth directory. No resizing or generation occurs. Invalid
    alpha, escaping paths, missing inputs or existing outputs raise before writes.
    Only an empty bifang-v1 blocked-generation manifest may be replaced on recovery.
    Resolution shortfalls remain explicit in returned data and manifest; they are
    never corrected by interpolation or silently labelled as native high-res.
    """
    source, root = source_dir.resolve(), asset_root.resolve()
    manifest_path = _bounded(root, "manifest.json")
    _validate_manifest_slot(manifest_path)
    prepared = [_prepare(key, spec, source, root) for key, spec in SEEDS.items()]
    assets = {item["key"]: _save(item) for item in prepared}
    report = {
        "version": "bifang-v1", "status": "seed-review",
        "model_requested": "gpt-image-2", "quality_requested": "high",
        "dimensions_met": all(item["native_target_met"] for item in assets.values()),
        "assets": assets,
    }
    _write_manifest(manifest_path, report)
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


def _bounded(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Image path outside intended root")
    return target


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
    if alpha:
        image = image.convert("RGBA")
        channel = image.getchannel("A")
        if channel.getextrema()[0] == 255 or channel.getextrema()[1] == 0:
            raise ValueError(f"{key}: genuine visible alpha required")
    else:
        image = image.convert("RGB")
    return {
        "key": key, "raw_path": raw_path, "input_path": input_path,
        "target": target, "image": image, "expected": expected,
        "source_size": raw.size, "alpha": bool(alpha),
    }


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _save(item: dict) -> dict:
    target, image = item["target"], item["image"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if item["alpha"]:
        image.save(target, format="PNG", optimize=True)
    else:
        image.save(target, format="WEBP", quality=92, method=6)
    return {
        "url": f"/assets/myth/seeds/{target.name}",
        "requested_size": list(item["expected"]),
        "source_size": list(item["source_size"]), "output_size": list(image.size),
        "native_target_met": item["source_size"] == item["expected"],
        "alpha_method": "original-chroma-key-tool" if item["alpha"] else "not-applicable",
        "source_sha256": _digest(item["raw_path"]),
        "prepared_input_sha256": _digest(item["input_path"]),
        "output_sha256": _digest(target), "bytes": target.stat().st_size,
    }


def _write_manifest(path: Path, report: dict) -> None:
    manifest = {
        "version": report["version"], "status": report["status"],
        "dimensions_met": report["dimensions_met"],
        "seeds": {key: {"url": value["url"], "size": value["output_size"]}
                  for key, value in report["assets"].items()},
        "animations": {}, "cards": {},
    }
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    """Package CLI input seeds and optional JSON evidence; errors exit 1, never generate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, default=Path("web-client/public/assets/myth"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = prepare_seeds(args.source_dir, args.asset_root)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Prepared 3 native seed files; dimensions_met={report['dimensions_met']}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Myth seed preparation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
