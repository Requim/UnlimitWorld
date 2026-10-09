"""Normalize generated art for shipping without generating images or changing the manifest."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageOps


CHARACTER_SIZES = {"characters": (570, 840, 60), "enemies": (630, 900, 30)}
ILLUSTRATION_SIZES = {"cards": (768, 576), "backgrounds": (1600, 640)}


def prepare_character(image: Image.Image, group: str) -> Image.Image:
    """Fit an alpha sprite without cropping; return a new canvas, or raise on fake/empty alpha.

    The group determines its display aspect and bottom inset. Both sprite groups
    have visible bounds ending at y=330 in the existing battle layout, including
    props below the feet. This is not a semantic foot anchor. Input is not mutated.
    """
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] == 255 or alpha.getextrema()[1] == 0:
        raise ValueError("Character needs visible pixels and genuine alpha")
    width, height, bottom = CHARACTER_SIZES[group]
    subject = rgba.crop(alpha.getbbox())
    subject = ImageOps.contain(subject, (width - 72, height - bottom - 24), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(subject, ((width - subject.width) // 2, height - bottom - subject.height))
    return canvas


def prepare_illustration(image: Image.Image, group: str) -> Image.Image:
    """Return a resized illustration with its complete framing; reject incompatible aspect.

    Accepts cards or backgrounds and never crops the subject. Small rounding
    differences are allowed; the source image is not mutated.
    """
    width, height = ILLUSTRATION_SIZES[group]
    ratio = image.width / image.height
    if abs(ratio / (width / height) - 1) > 0.015:
        raise ValueError(f"{group}: incompatible aspect {image.width}x{image.height}")
    return image.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)


def prepare_assets(source_dir: Path, asset_root: Path, *, force: bool = False) -> list[dict]:
    """Prepare all manifest assets and return hashes/dimensions; leave manifest status unchanged.

    Reads `*-source.png` and alpha cutouts from source_dir, writes only within
    asset_root. All inputs are prepared before writes. Missing inputs, invalid
    images, escaping paths or existing outputs without force raise an exception.
    """
    manifest = json.loads((asset_root / "manifest.json").read_text(encoding="utf-8"))
    plans = _plans(manifest, source_dir.resolve(), asset_root.resolve(), force)
    prepared = [_prepare(plan) for plan in plans]
    return [_save(plan, image) for plan, image in zip(plans, prepared, strict=True)]


def _plans(manifest: dict, source: Path, root: Path, force: bool) -> list[dict]:
    plans = []
    for group in (*CHARACTER_SIZES, *ILLUSTRATION_SIZES):
        for key, url in manifest.get(group, {}).items():
            if not isinstance(url, str) or not url.startswith("/assets/"):
                raise ValueError("Invalid asset URL")
            target = (root / url.removeprefix("/assets/")).resolve()
            raw = (source / f"{key}-source.png").resolve()
            alpha = (source / f"{key}-alpha.png").resolve()
            if not target.is_relative_to(root) or not raw.is_relative_to(source):
                raise ValueError("Asset path outside intended root")
            if target.exists() and not force:
                raise FileExistsError(target)
            input_path = alpha if group in CHARACTER_SIZES else raw
            if not raw.is_file() or not input_path.is_file():
                raise FileNotFoundError(input_path)
            plans.append({"group": group, "key": key, "url": url,
                          "raw": raw, "input": input_path, "target": target})
    return plans


def _prepare(plan: dict) -> Image.Image:
    with Image.open(plan["input"]) as image:
        image.load()
        if plan["group"] in CHARACTER_SIZES:
            return prepare_character(image, plan["group"])
        return prepare_illustration(image, plan["group"])


def _save(plan: dict, image: Image.Image) -> dict:
    target = plan["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if plan["group"] in CHARACTER_SIZES:
        image.save(target, format="PNG", optimize=True)
    else:
        image.save(target, format="WEBP", quality=88, method=6)
    with Image.open(plan["raw"]) as source:
        source_size = list(source.size)
    return {
        "group": plan["group"], "key": plan["key"], "url": plan["url"],
        "source_sha256": sha256(plan["raw"].read_bytes()).hexdigest(),
        "prepared_input_sha256": sha256(plan["input"].read_bytes()).hexdigest(),
        "output_sha256": sha256(target.read_bytes()).hexdigest(),
        "source_size": source_size, "output_size": list(image.size),
        "bytes": target.stat().st_size,
    }


def main() -> int:
    """Normalize local art from CLI; write optional non-secret JSON evidence, exit 1 on error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, default=Path("web-client/public/assets"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        report = prepare_assets(args.source_dir, args.asset_root, force=args.force)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Prepared {len(report)} assets; {sum(item['bytes'] for item in report)} bytes")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Art preparation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
