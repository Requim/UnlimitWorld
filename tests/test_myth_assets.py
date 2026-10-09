"""Myth seeds keep native pixels, honest dimensions, alpha and bounded paths."""

import importlib
import json

import pytest
from PIL import Image


def pipeline():
    return importlib.import_module("tools.prepare_myth_assets")


def seed_inputs(root, native=False):
    root.mkdir()
    for key in ("hero", "bifang"):
        size = (2048, 3072) if native else (32, 48)
        Image.new("RGB", size, (210, 210, 210)).save(root / f"{key}-seed.png")
        image = Image.new("RGBA", size, (0, 0, 0, 0))
        image.paste((255, 255, 255, 255), (8, 6, 24, 42))
        image.putpixel((6, 24), (180, 40, 30, 255))
        image.save(root / f"{key}-alpha.png")
    scene_size = (3840, 2160) if native else (64, 36)
    Image.new("RGB", scene_size, (60, 120, 110)).save(root / "zhang-e-mountain-seed.png")


def test_exact_native_sizes_are_reported_without_unlocking_animation_approval(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source, native=True)
    report = pipeline().prepare_seeds(source, target)
    assert report["dimensions_met"] is True
    assert report["status"] == "seed-review"
    assert all(asset["native_target_met"] for asset in report["assets"].values())
    with Image.open(target / "seeds/zhang-e-mountain.webp") as scene:
        assert scene.size == (3840, 2160)


def test_bundle_keeps_actual_pixels_and_does_not_claim_requested_resolution(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    report = pipeline().prepare_seeds(source, target)
    assert report["dimensions_met"] is False
    assert report["status"] == "seed-review"
    assert report["model_requested"] == "gpt-image-2"
    hero = report["assets"]["hero"]
    assert hero["requested_size"] == [2048, 3072]
    assert hero["source_size"] == [32, 48]
    assert hero["output_size"] == [32, 48]
    assert hero["native_target_met"] is False
    assert len(hero["source_sha256"]) == len(hero["output_sha256"]) == 64
    with Image.open(target / "seeds/hero.png") as image:
        assert image.size == (32, 48)
        assert image.getpixel((16, 24)) == (255, 255, 255, 255)
        assert image.getpixel((6, 24)) == (180, 40, 30, 255)
        assert image.getpixel((0, 0))[3] == 0
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["animations"] == {}
    assert manifest["cards"] == {}
    assert manifest["seeds"]["scene"]["size"] == [64, 36]


@pytest.mark.parametrize("color", [(255, 255, 255, 255), (0, 0, 0, 0)])
def test_fake_or_empty_alpha_preflight_does_not_write_bundle(tmp_path, color):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    Image.new("RGBA", (32, 48), color).save(source / "bifang-alpha.png")
    with pytest.raises(ValueError, match="alpha"):
        pipeline().prepare_seeds(source, target)
    assert not target.exists()


def test_alpha_must_keep_source_canvas_size(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    Image.new("RGBA", (16, 24), (0, 0, 0, 0)).save(source / "hero-alpha.png")
    with pytest.raises(ValueError, match="size"):
        pipeline().prepare_seeds(source, target)
    assert not target.exists()


def test_missing_source_preserves_existing_bundle(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    (source / "bifang-seed.png").unlink()
    with pytest.raises(FileNotFoundError):
        pipeline().prepare_seeds(source, target)
    assert not target.exists()


def test_existing_output_is_not_silently_overwritten(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    pipeline().prepare_seeds(source, target)
    with pytest.raises(FileExistsError):
        pipeline().prepare_seeds(source, target)


def test_empty_blocked_manifest_can_be_recovered_when_real_seeds_arrive(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    target.mkdir()
    blocked = {"version": "bifang-v1", "status": "blocked-generation",
               "seeds": {}, "animations": {}, "cards": {}}
    (target / "manifest.json").write_text(json.dumps(blocked), encoding="utf-8")
    report = pipeline().prepare_seeds(source, target)
    assert report["status"] == "seed-review"
    assert (target / "seeds/hero.png").is_file()


def test_blocked_label_does_not_allow_overwriting_nonempty_manifest(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    target.mkdir()
    blocked = {"version": "bifang-v1", "status": "blocked-generation",
               "seeds": {"hero": {"url": "/custom.png"}}, "animations": {}, "cards": {}}
    before = json.dumps(blocked)
    (target / "manifest.json").write_text(before, encoding="utf-8")
    with pytest.raises(FileExistsError):
        pipeline().prepare_seeds(source, target)
    assert (target / "manifest.json").read_text() == before


@pytest.mark.parametrize("invalid", ["[]", "null"])
def test_invalid_manifest_root_is_rejected_without_writes(tmp_path, invalid):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    target.mkdir()
    (target / "manifest.json").write_text(invalid, encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        pipeline().prepare_seeds(source, target)
    assert not (target / "seeds").exists()

def test_output_symlink_cannot_escape_asset_root(tmp_path):
    source, target, outside = tmp_path / "source", tmp_path / "assets", tmp_path / "outside"
    seed_inputs(source)
    target.mkdir()
    outside.mkdir()
    try:
        (target / "seeds").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks unavailable")
    with pytest.raises(ValueError, match="outside"):
        pipeline().prepare_seeds(source, target)
    assert not list(outside.iterdir())


def test_source_symlink_cannot_read_outside_source_root(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    outside = tmp_path / "outside.png"
    Image.new("RGBA", (32, 48), (0, 0, 0, 0)).save(outside)
    (source / "hero-alpha.png").unlink()
    try:
        (source / "hero-alpha.png").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks unavailable")
    with pytest.raises(ValueError, match="outside"):
        pipeline().prepare_seeds(source, target)
    assert not target.exists()
