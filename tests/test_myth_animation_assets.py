"""Production-strip packaging tests, independent of image provider requests."""

import importlib
import json
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageDraw
import pytest


def pipeline():
    return importlib.import_module("tools.prepare_myth_animation")


def fixture_strip(path: Path, empty=False):
    image = Image.new("RGBA", (1200, 400))
    for frame in range(4):
        if empty and frame == 2:
            continue
        # Deliberately different limbs; one shared scale must not resize each pose.
        shape = Image.new("RGBA", (80 + frame * 10, 260), (20, 110, 100, 255))
        image.alpha_composite(shape, (frame * 300 + 100, 120))
    image.save(path)
    return path


def test_packaged_strip_has_real_frames_shared_anchor_and_no_upscale(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    reference = Image.new("RGBA", (300, 400))
    reference.alpha_composite(Image.new("RGBA", (80, 260), (20, 110, 100, 255)), (100, 120))
    reference.save(tmp_path / "anchor.png")
    report = pipeline().prepare_animation(
        source, tmp_path / "anchor.png", tmp_path / "output",
        name="hero_sword", frame_size=256, fps=8)
    with Image.open(tmp_path / "output/hero_sword.png") as strip:
        assert strip.size == (1024, 256)
        assert strip.mode == "RGBA"
        bounds = [strip.crop((i * 256, 0, (i + 1) * 256, 256)).getbbox() for i in range(4)]
    assert [box[3] for box in bounds] == [256] * 4
    assert bounds[0][2] - bounds[0][0] < bounds[3][2] - bounds[3][0]
    assert report["local_upscaling"] is False
    assert report["clip"]["frame_size"] == [256, 256]
    assert report["clip"]["anchor"] == [0.5, 1]
    assert report["clip"]["reference_height"] == 256
    assert report["clip"]["frames"] == 4
    assert report["clip"]["fps"] == 8
    assert report["clip"]["url"] == "/assets/myth/animations/hero_sword.png"


def test_empty_frame_cannot_be_published_as_real_animation(tmp_path):
    source = fixture_strip(tmp_path / "raw.png", empty=True)
    with pytest.raises(ValueError, match="empty"):
        pipeline().prepare_animation(source, source, tmp_path / "output",
                                     name="hero_hurt", frame_size=256)
    assert not (tmp_path / "output").exists()


def test_packager_rejects_low_resolution_upscaling(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    # The anchor must be a single sprite with actual transparent margin.
    anchor = Image.new("RGBA", (100, 280))
    anchor.alpha_composite(Image.new("RGBA", (80, 260), (20, 110, 100, 255)), (10, 10))
    anchor.save(tmp_path / "anchor.png")
    with pytest.raises(ValueError, match="upscale"):
        pipeline().prepare_animation(source, tmp_path / "anchor.png", tmp_path / "output",
                                     name="hero_sword", frame_size=512)
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("name", ["../escape", "other", "hero_sword.png"])
def test_animation_name_is_bounded_before_output(tmp_path, name):
    source = fixture_strip(tmp_path / "raw.png")
    with pytest.raises(ValueError):
        pipeline().prepare_animation(source, source, tmp_path / "output",
                                     name=name, frame_size=256)
    assert not (tmp_path / "output").exists()


def test_curated_connected_poses_keep_weapon_across_a_nominal_slot_boundary(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    with Image.open(source) as image:
        image.load()
        ImageDraw.Draw(image).rectangle((260, 200, 440, 210), fill=(20, 110, 100, 255))
        image.save(source)
        anchor = image.crop((0, 0, 300, 400))
        anchor.save(tmp_path / "anchor.png")
    report = pipeline().prepare_animation(
        source, tmp_path / "anchor.png", tmp_path / "output",
        name="hero_sword", frame_size=256,
        pose_centers=[(120, 210), (430, 210), (730, 210), (1040, 210)])
    with Image.open(tmp_path / "output/02.png") as pose:
        bounds = pose.getbbox()
        assert bounds[2] - bounds[0] >= 220
    assert report["curated_pose_centers"] == [(120, 210), (430, 210), (730, 210), (1040, 210)]


def test_adjacent_duplicate_pose_cannot_be_disguised_by_anchor_replacement(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    with Image.open(source) as image:
        image.load()
        image.paste(image.crop((0, 0, 300, 400)), (300, 0))
        image.crop((0, 0, 300, 400)).save(tmp_path / "anchor.png")
        image.save(source)
    with pytest.raises(ValueError, match="duplicate"):
        pipeline().prepare_animation(source, tmp_path / "anchor.png", tmp_path / "output",
                                     name="hero_sword", frame_size=256)
    assert not (tmp_path / "output").exists()


def test_recovery_may_return_to_initial_pose_without_claiming_four_unique_poses(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    with Image.open(source) as image:
        image.load()
        first = image.crop((0, 0, 300, 400))
        image.paste(first, (900, 0))
        first.save(tmp_path / "anchor.png")
        image.save(source)
    report = pipeline().prepare_animation(
        source, tmp_path / "anchor.png", tmp_path / "output",
        name="hero_sword", frame_size=256)
    assert report["clip"]["frames"] == 4
    with Image.open(tmp_path / "output/01.png") as first, Image.open(tmp_path / "output/04.png") as last:
        assert first.tobytes() == last.tobytes()


def test_anchor_identity_is_locked_and_short_pose_uses_common_scale(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    with Image.open(source) as image:
        image.load()
        image.paste((0, 0, 0, 0), (600, 0, 900, 400))
        image.alpha_composite(Image.new("RGBA", (100, 130), (20, 110, 100, 255)), (700, 250))
        image.save(source)
    anchor = Image.new("RGBA", (100, 400))
    anchor.alpha_composite(Image.new("RGBA", (80, 260), (220, 50, 40, 255)), (10, 120))
    anchor.save(tmp_path / "anchor.png")
    pipeline().prepare_animation(source, tmp_path / "anchor.png", tmp_path / "output",
                                 name="hero_defeat", frame_size=256)
    with Image.open(tmp_path / "output/01.png") as first, Image.open(tmp_path / "output/03.png") as third:
        assert first.getpixel((128, 160))[:3] == (220, 50, 40)
        assert third.getpixel((128, 220))[:3] == (20, 110, 100)
        assert third.getbbox()[3] - third.getbbox()[1] <= 132


def test_encoding_failure_does_not_publish_partial_clip(tmp_path, monkeypatch):
    source = fixture_strip(tmp_path / "raw.png")
    with Image.open(source) as image:
        image.crop((0, 0, 300, 400)).save(tmp_path / "anchor.png")
    save = Image.Image.save

    def fail_third(image, target, **kwargs):
        if Path(target).name == "03.png":
            raise OSError("Injected encoding failure")
        return save(image, target, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_third)
    with pytest.raises(OSError):
        pipeline().prepare_animation(source, tmp_path / "anchor.png", tmp_path / "output",
                                     name="hero_sword", frame_size=256)
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".animation-stage-*"))


def test_connected_extraction_rejects_silent_loss_of_detached_accessory(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    with Image.open(source) as image:
        image.load()
        image.alpha_composite(Image.new("RGBA", (30, 30), (210, 50, 40, 255)), (20, 20))
        image.save(source)
        image.crop((0, 0, 300, 400)).save(tmp_path / "anchor.png")
    with pytest.raises(ValueError, match="Unassigned"):
        pipeline().prepare_animation(
            source, tmp_path / "anchor.png", tmp_path / "output",
            name="hero_sword", frame_size=256,
            pose_centers=[(120, 210), (430, 210), (730, 210), (1040, 210)])
    assert not (tmp_path / "output").exists()


def test_curated_extra_component_preserves_detached_accessory(tmp_path):
    source = fixture_strip(tmp_path / "raw.png")
    with Image.open(source) as image:
        image.load()
        image.alpha_composite(Image.new("RGBA", (30, 30), (210, 50, 40, 255)), (20, 20))
        image.save(source)
        image.crop((0, 0, 300, 400)).save(tmp_path / "anchor.png")
    report = pipeline().prepare_animation(
        source, tmp_path / "anchor.png", tmp_path / "output",
        name="hero_sword", frame_size=256,
        pose_centers=[(120, 210), (430, 210), (730, 210), (1040, 210)],
        extra_centers=[(0, 35, 35)])
    assert report["alpha_coverage"] == 1
    assert report["unassigned_pixels"] == 0


def test_published_animation_evidence_matches_manifest_and_real_pixels():
    root = Path(__file__).resolve().parents[1]
    evidence = root / "docs/m5/myth"
    assets = root / "web-client/public/assets/myth"
    manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads((evidence / "cartoon-animation-provenance.json").read_text(encoding="utf-8"))
    assert set(manifest["animations"]) == {item["id"] for item in provenance["published"]}
    assert manifest["status"] == "animation-review"
    for rejected in provenance["rejected"]:
        assert rejected["id"] not in manifest["animations"]
        assert not (assets / "animations" / f"{rejected['id']}.png").exists()
    for name, clip in manifest["animations"].items():
        report = json.loads((evidence / f"{name.replace('_', '-')}-packaged-provenance.json").read_text(encoding="utf-8"))
        target = root / "web-client/public" / clip["url"].lstrip("/")
        assert report["clip"] == clip
        assert sha256(target.read_bytes()).hexdigest() == report["output_sha256"]
        with Image.open(target) as image:
            image.load()
            width, height = clip["frame_size"]
            assert image.size == (width * clip["frames"], height)
            assert image.mode == "RGBA"
            frames = [image.crop((i * width, 0, (i + 1) * width, height)) for i in range(clip["frames"])]
        pipeline()._validate_poses(frames)
        bounds = frames[0].getchannel("A").getbbox()
        assert bounds[3] - bounds[1] == clip["reference_height"]
        assert all(frame.getchannel("A").getextrema() == (0, 255) for frame in frames)
        assert report["local_upscaling"] is False
