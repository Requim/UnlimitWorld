"""Normalize approved cartoon strips with one scale, not pixel-art resampling."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw, ImageChops


NAMES = {
    "hero_idle", "hero_sword", "hero_cast", "hero_hurt", "hero_defeat",
    "bifang_idle", "bifang_charge", "bifang_strike", "bifang_hurt", "bifang_retreat",
}
SMOOTH_PROFILE = "smooth-v2"
SMOOTH_SPECS = {
    "hero_idle": (12, 12), "bifang_idle": (12, 12),
    "hero_sword": (16, 24), "hero_cast": (16, 24),
    "bifang_charge": (16, 24), "bifang_strike": (16, 24),
    "hero_hurt": (12, 24), "hero_defeat": (12, 24),
    "bifang_hurt": (12, 24), "bifang_retreat": (12, 24),
}


def _load(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        if image.mode != "RGBA" or image.getchannel("A").getextrema()[0] == 255:
            raise ValueError("Real alpha required, remove chroma key first")
        return image.copy()


def _content(image: Image.Image) -> Image.Image:
    bounds = image.getchannel("A").point(lambda value: 255 if value > 8 else 0).getbbox()
    if not bounds:
        raise ValueError("Animation contains an empty frame")
    return image.crop(bounds)


def _connected_mask(strip: Image.Image, center: tuple[int, int]) -> Image.Image:
    mask = strip.getchannel("A").point(lambda value: 255 if value > 8 else 0)
    if len(center) != 2:
        raise ValueError("Invalid pose center")
    x, y = center
    if not 0 <= x < strip.width or not 0 <= y < strip.height or mask.getpixel(center) != 255:
        raise ValueError("Pose center must identify a visible body pixel")
    ImageDraw.floodfill(mask, center, 128)
    return mask.point(lambda value: 255 if value == 128 else 0)


def _masked_pose(strip: Image.Image, selected: Image.Image) -> Image.Image:
    pose = strip.copy()
    pose.putalpha(ImageChops.multiply(strip.getchannel("A"), selected))
    return _content(pose)


def _pose_masks(strip: Image.Image, centers: list[tuple[int, int]],
                extras: list[tuple[int, int, int]] | None) -> list[Image.Image]:
    if len(centers) != 4:
        raise ValueError("Exactly four curated pose centers required")
    masks = [_connected_mask(strip, center) for center in centers]
    for index, x, y in extras or []:
        if index not in range(4):
            raise ValueError("Extra component owner must be 0..3")
        masks[index] = ImageChops.lighter(masks[index], _connected_mask(strip, (x, y)))
    return masks


def _missing_mask(strip: Image.Image, masks: list[Image.Image]) -> Image.Image:
    union = Image.new("L", strip.size)
    for mask in masks:
        union = ImageChops.lighter(union, mask)
    visible = strip.getchannel("A").point(lambda value: 255 if value > 8 else 0)
    return ImageChops.subtract(visible, union)


def _curated_frames(strip: Image.Image, centers: list[tuple[int, int]],
                    extras: list[tuple[int, int, int]] | None) -> tuple[list, dict]:
    masks = _pose_masks(strip, centers, extras)
    visible = strip.getchannel("A").point(lambda value: 255 if value > 8 else 0)
    total = visible.histogram()[255]
    lost = _missing_mask(strip, masks).histogram()[255]
    coverage = 1 - lost / max(1, total)
    if coverage < 0.998:
        raise ValueError(f"Unassigned alpha exceeds 0.2%: {lost}/{total}; inspect accessory components")
    return [_masked_pose(strip, mask) for mask in masks], {
        "visible_source_pixels": total, "unassigned_pixels": lost,
        "alpha_coverage": coverage, "minimum_alpha_coverage": 0.998,
    }


def _frames(strip: Image.Image, centers: list[tuple[int, int]] | None,
            extras: list[tuple[int, int, int]] | None, frame_count: int,
            source_columns: int) -> tuple[list, dict]:
    if centers:
        if frame_count != 4 or source_columns != 4:
            raise ValueError("Curated centers are only supported for legacy four-pose strips")
        return _curated_frames(strip, centers, extras)
    return _grid_frames(strip, frame_count, source_columns)


def _grid_frames(strip: Image.Image, frame_count: int,
                 source_columns: int) -> tuple[list, dict]:
    if frame_count % source_columns:
        raise ValueError("Frame count must fill complete source rows")
    rows = frame_count // source_columns
    if strip.width % source_columns or strip.height % rows:
        raise ValueError("Source grid dimensions must be divisible by columns and rows")
    slot_width, slot_height = strip.width // source_columns, strip.height // rows
    frames = []
    for index in range(frame_count):
        column, row = index % source_columns, index // source_columns
        box = (column * slot_width, row * slot_height,
               (column + 1) * slot_width, (row + 1) * slot_height)
        frames.append(_content(strip.crop(box)))
    visible = strip.getchannel("A").point(lambda value: 255 if value > 8 else 0)
    return frames, {"visible_source_pixels": visible.histogram()[255],
                    "unassigned_pixels": 0, "alpha_coverage": 1,
                    "source_slot_size": [slot_width, slot_height]}


def _compose(content: Image.Image, size: int, scale: float) -> Image.Image:
    dimensions = tuple(max(1, round(edge * scale)) for edge in content.size)
    resized = content.resize(dimensions, Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (size, size))
    frame.alpha_composite(resized, ((size - resized.width) // 2, size - resized.height))
    return frame


def _validate_poses(frames: list[Image.Image], minimum_unique: int = 3) -> None:
    contents = [_content(frame) for frame in frames]
    hashes = [sha256(str(frame.size).encode() + frame.tobytes()).digest()
              for frame in contents]
    if any(left == right for left, right in zip(hashes, hashes[1:])):
        raise ValueError("Strip contains duplicate poses without a readable action beat")
    if len(set(hashes)) < minimum_unique:
        raise ValueError(f"Strip contains fewer than {minimum_unique} distinct poses")


def _validate_spec(name: str, frame_size: int, fps: float, profile: str | None,
                   frame_count: int, source_columns: int) -> int:
    if name not in NAMES or type(frame_size) is not int or frame_size <= 0:
        raise ValueError("Invalid animation specification")
    if not isinstance(fps, (int, float)) or not 1 <= fps <= 60:
        raise ValueError("Invalid animation FPS")
    if type(frame_count) is not int or frame_count <= 0 or type(source_columns) is not int or source_columns <= 0:
        raise ValueError("Invalid animation grid")
    if profile is None:
        if frame_count != 4 or source_columns != 4:
            raise ValueError("Legacy animation requires four horizontal poses")
        return 1
    if profile != SMOOTH_PROFILE:
        raise ValueError("Unknown animation profile")
    expected_frames, expected_fps = SMOOTH_SPECS[name]
    if (frame_size, frame_count, source_columns, fps) != (704, expected_frames, 4, expected_fps):
        raise ValueError("Invalid smooth-v2 animation specification")
    return frame_count // source_columns


def _shared_scale(frame_size: int, maximum: int, profile: str | None) -> float:
    scale = frame_size / maximum
    if profile == SMOOTH_PROFILE:
        return min(1, scale)
    if scale > 1:
        raise ValueError("Refusing to upscale low-resolution animation")
    return scale


def prepare_animation(source: Path, anchor: Path, output_dir: Path, *,
                      name: str, frame_size: int = 768, fps: float = 8,
                      profile: str | None = None, frame_count: int = 4,
                      source_columns: int = 4,
                      pose_centers: list[tuple[int, int]] | None = None,
                      extra_centers: list[tuple[int, int, int]] | None = None) -> dict:
    """Package an RGBA strip/grid into square, common-scale production frames.

    Inputs are source strip, approved anchor PNG, a new output directory, semantic
    clip name, frame pixels, FPS, optional profile, count and source columns.
    Returns provenance/clip metadata. Frame one locks to the approved anchor.
    Uses the plugin's union-scale/bottom-center
    method with Lanczos for this non-pixel-art direction. No generation, resizing
    upward, or manifest changes. smooth-v2 reads four-column row-major grids and
    requires native source slots at least 704 square. Optional pose_centers selects
    four connected body components; extra_centers adds detached components using
    (zero-based pose owner, x, y). Below 99.8% assigned alpha coverage is rejected;
    smaller unassigned pixels are discarded and reported. Without centers, uses
    the declared row-major grid. Invalid/empty/adjacent-duplicate poses raise ValueError; an
    existing destination raises FileExistsError. Publication is transactional.
    """
    rows = _validate_spec(name, frame_size, fps, profile, frame_count, source_columns)
    root = output_dir.resolve()
    if root.exists():
        raise FileExistsError(root)
    strip, seed = _load(source), _content(_load(anchor))
    contents, coverage = _frames(strip, pose_centers, extra_centers, frame_count, source_columns)
    slot_size = coverage.get("source_slot_size", [strip.width // source_columns, strip.height // rows])
    if profile == SMOOTH_PROFILE and min(slot_size) < 704:
        raise ValueError("smooth-v2 source slot must be at least 704 pixels on each side")
    minimum_unique = frame_count - 2 if profile == SMOOTH_PROFILE else 3
    _validate_poses(contents, minimum_unique)
    seed_scale = contents[0].height / seed.height
    if seed_scale > 1:
        raise ValueError("Refusing to upscale the approved anchor")
    seed = seed.resize(tuple(max(1, round(edge * seed_scale)) for edge in seed.size),
                       Image.Resampling.LANCZOS)
    maximum = max(max(frame.size) for frame in [*contents, seed])
    scale = _shared_scale(frame_size, maximum, profile)
    frames = [_compose(frame, frame_size, scale) for frame in [seed, *contents[1:]]]
    _validate_poses(frames, minimum_unique)
    report = _metadata(source, anchor, name, strip.size, frames, scale, fps,
                       profile, source_columns, rows, slot_size)
    report.update(seed_scale=seed_scale, curated_pose_centers=pose_centers,
                  extra_component_centers=extra_centers, **coverage)
    root.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".animation-stage-", dir=root.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir()
        _save_bundle(stage, name, frames, report, source_columns)
        stage.rename(root)
    return report


def _metadata(source: Path, anchor: Path, name: str, source_size: tuple,
              frames: list[Image.Image], scale: float, fps: float,
              profile: str | None, columns: int, rows: int,
              source_slot_size: list[int]) -> dict:
    height = frames[0].getchannel("A").getbbox()[3] - frames[0].getchannel("A").getbbox()[1]
    size = frames[0].width
    clip = {"url": f"/assets/myth/animations/{name}.png",
            "frame_size": [size, size], "frames": len(frames), "fps": fps,
            "anchor": [0.5, 1], "reference_height": height}
    if profile:
        clip.update(profile=profile, columns=columns, rows=rows)
    report = {
        "name": name, "source_size": list(source_size),
        "source_slot_size": source_slot_size,
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "anchor_sha256": sha256(anchor.read_bytes()).hexdigest(),
        "shared_scale": scale, "local_upscaling": False,
        "frame_one_locked": True,
        "clip": clip,
    }
    if profile:
        report.update(profile=profile, columns=columns, rows=rows)
    return report


def _save_bundle(root: Path, name: str, frames: list[Image.Image], report: dict,
                 columns: int) -> None:
    rows = len(frames) // columns
    sheet = Image.new("RGBA", (frames[0].width * columns, frames[0].height * rows))
    for index, frame in enumerate(frames):
        frame.save(root / f"{index + 1:02d}.png")
        sheet.alpha_composite(frame, ((index % columns) * frame.width,
                                      (index // columns) * frame.height))
    target = root / f"{name}.png"
    sheet.save(target, optimize=True)
    report["output_sha256"] = sha256(target.read_bytes()).hexdigest()
    report["output_bytes"] = target.stat().st_size
    (root / "provenance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def inspect_unassigned(source: Path, centers: list[tuple[int, int]],
                       extras: list[tuple[int, int, int]] | None = None) -> list[dict]:
    """Return up to 256 unassigned-alpha component points and pixel counts.

    Reads a local RGBA strip and curated center ownership; never writes or makes
    requests. Raises validation/I/O errors for invalid centers or source images.
    Points are for human component assignment, not automatic accessory inference.
    """
    strip = _load(source)
    mask = _missing_mask(strip, _pose_masks(strip, centers, extras))
    components = []
    for _ in range(256):
        offset = mask.tobytes().find(b"\xff")
        if offset < 0:
            break
        point = (offset % strip.width, offset // strip.width)
        ImageDraw.floodfill(mask, point, 128)
        pixels = mask.histogram()[128]
        components.append({"point": list(point), "pixels": pixels})
        mask = mask.point(lambda value: 0 if value == 128 else value)
    return sorted(components, key=lambda value: value["pixels"], reverse=True)


def main() -> int:
    """Package local assets from CLI paths; returns 0 on success, 1 on validation.

    Writes a new directory of frames/strip/provenance only; never calls the API or
    updates game state/manifest. Existing output directories are not overwritten.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--name", choices=sorted(NAMES), required=True)
    parser.add_argument("--frame-size", type=int, default=768)
    parser.add_argument("--fps", type=float, default=8)
    parser.add_argument("--profile", choices=[SMOOTH_PROFILE])
    parser.add_argument("--frame-count", type=int, default=4)
    parser.add_argument("--source-columns", type=int, default=4)
    parser.add_argument("--pose-centers", help="Four body pixels x,y;x,y;x,y;x,y for unequal slots")
    parser.add_argument("--extra-centers", help="Curated detached components owner,x,y;owner,x,y")
    parser.add_argument("--inspect-components", action="store_true")
    args = parser.parse_args()
    try:
        centers = ([tuple(map(int, point.split(","))) for point in args.pose_centers.split(";")]
                   if args.pose_centers else None)
        extras = ([tuple(map(int, point.split(","))) for point in args.extra_centers.split(";")]
                  if args.extra_centers else None)
        if args.inspect_components:
            print(json.dumps(inspect_unassigned(args.input, centers or [], extras), indent=2))
            return 0
        report = prepare_animation(args.input, args.anchor, args.out_dir, name=args.name,
                                   frame_size=args.frame_size, fps=args.fps, profile=args.profile,
                                   frame_count=args.frame_count, source_columns=args.source_columns,
                                   pose_centers=centers, extra_centers=extras)
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"Animation packaging failed: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
