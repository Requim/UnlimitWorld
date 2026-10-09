"""Myth seeds keep native pixels, honest dimensions, alpha and bounded paths."""

import importlib
import json
from pathlib import Path
import sys

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


def blocked_bundle(root):
    root.mkdir()
    blocked = {"version": "bifang-v1", "status": "blocked-generation",
               "seeds": {}, "animations": {}, "cards": {}}
    (root / "manifest.json").write_text(json.dumps(blocked), encoding="utf-8")
    (root / "existing-proof.bin").write_bytes(b"preserve-existing-asset")


def bundle_snapshot(root):
    return {path.relative_to(root): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


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
    assert hero["alpha_method"] == "provided-alpha-cutout"
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


def test_missing_source_preserves_existing_bundle_byte_for_byte(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    blocked_bundle(target)
    before = bundle_snapshot(target)
    (source / "bifang-seed.png").unlink()
    with pytest.raises(FileNotFoundError):
        pipeline().prepare_seeds(source, target)
    assert bundle_snapshot(target) == before


def test_image_save_failure_preserves_existing_bundle_byte_for_byte(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    blocked_bundle(target)
    before = bundle_snapshot(target)
    original_save, calls = Image.Image.save, 0

    def fail_second_save(image, path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected image save failure")
        return original_save(image, path, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_second_save)
    with pytest.raises(OSError, match="injected image save failure"):
        pipeline().prepare_seeds(source, target)
    assert bundle_snapshot(target) == before
    monkeypatch.setattr(Image.Image, "save", original_save)
    assert pipeline().prepare_seeds(source, target)["status"] == "seed-review"


@pytest.mark.parametrize("failed_output", ["manifest.json", "evidence.json"])
def test_publication_failure_restores_blocked_bundle(tmp_path, monkeypatch, failed_output):
    source, target, report_path = (
        tmp_path / "source", tmp_path / "assets", tmp_path / "evidence.json")
    seed_inputs(source)
    blocked_bundle(target)
    before = bundle_snapshot(target)
    original_replace = Path.replace
    failure_path = target / failed_output if failed_output == "manifest.json" else report_path

    def fail_selected_publish(path, destination):
        if Path(destination).resolve() == failure_path.resolve():
            raise OSError(f"injected {failed_output} publication failure")
        return original_replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_selected_publish)
    monkeypatch.setattr(sys, "argv", ["prepare_myth_assets.py", "--source-dir", str(source),
                                     "--asset-root", str(target), "--report", str(report_path)])
    assert pipeline().main() == 1
    assert bundle_snapshot(target) == before
    assert not report_path.exists()
    monkeypatch.setattr(Path, "replace", original_replace)
    assert pipeline().prepare_seeds(source, target, report_path)["status"] == "seed-review"
    assert report_path.is_file()


def test_existing_output_is_not_silently_overwritten(tmp_path):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    pipeline().prepare_seeds(source, target)
    with pytest.raises(FileExistsError):
        pipeline().prepare_seeds(source, target)


def test_existing_optional_report_is_not_overwritten(tmp_path):
    source, target, report_path = (
        tmp_path / "source", tmp_path / "assets", tmp_path / "evidence.json")
    seed_inputs(source)
    blocked_bundle(target)
    before = bundle_snapshot(target)
    report_path.write_bytes(b"existing user evidence")
    with pytest.raises(FileExistsError):
        pipeline().prepare_seeds(source, target, report_path)
    assert bundle_snapshot(target) == before
    assert report_path.read_bytes() == b"existing user evidence"


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


def test_cli_reports_files_without_resizing_when_dimensions_are_short(tmp_path, monkeypatch, capsys):
    source, target = tmp_path / "source", tmp_path / "assets"
    seed_inputs(source)
    monkeypatch.setattr(sys, "argv", ["prepare_myth_assets.py", "--source-dir", str(source),
                                     "--asset-root", str(target)])
    assert pipeline().main() == 0
    output = capsys.readouterr().out
    assert "Prepared 3 files without resizing" in output
    assert "dimensions_met=False" in output


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
