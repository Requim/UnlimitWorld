"""Shipping normalization must preserve art, alpha, framing and safe output paths."""

import importlib
import json

import pytest
from PIL import Image, ImageDraw


def pipeline():
    return importlib.import_module("tools.prepare_art_assets")


@pytest.mark.parametrize("group,size,bottom,weapon_pixel", [
    ("characters", (570, 840), 780, (160, 260)),
    ("enemies", (630, 900), 870, (170, 295)),
])
def test_character_preserves_white_robe_weapon_and_standing_baseline(group, size, bottom, weapon_pixel):
    source = Image.new("RGBA", (120, 240), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(source)
    drawing.rectangle((30, 20, 90, 220), fill=(255, 255, 255, 255))
    drawing.rectangle((5, 80, 29, 90), fill=(190, 40, 30, 255))
    result = pipeline().prepare_character(source, group)
    assert result.size == size
    bounds = result.getchannel("A").getbbox()
    assert bounds[0] > 0 and bounds[2] < size[0]
    assert bounds[3] == bottom
    assert result.getpixel((size[0] // 2, size[1] // 2)) == (255, 255, 255, 255)
    assert result.getpixel(weapon_pixel) == (190, 40, 30, 255)
    assert result.getpixel((0, 0))[3] == 0


@pytest.mark.parametrize("color", [(255, 255, 255, 255), (0, 0, 0, 0)])
def test_character_rejects_opaque_or_empty_fake_transparency(color):
    with pytest.raises(ValueError, match="alpha"):
        pipeline().prepare_character(Image.new("RGBA", (40, 60), color), "characters")


@pytest.mark.parametrize("group,size", [("cards", (768, 576)), ("backgrounds", (1600, 640))])
def test_illustration_preserves_matching_aspect_and_edge_subjects(group, size):
    source = Image.new("RGB", size, (20, 120, 110))
    result = pipeline().prepare_illustration(source, group)
    assert result.size == size
    assert result.getpixel((0, 0)) == (20, 120, 110)
    assert result.getpixel((size[0] - 1, size[1] - 1)) == (20, 120, 110)


def test_illustration_refuses_wrong_aspect_instead_of_cropping_or_stretching():
    with pytest.raises(ValueError, match="aspect"):
        pipeline().prepare_illustration(Image.new("RGB", (1024, 1024)), "cards")


def test_output_url_cannot_escape_asset_root(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    manifest = {"cards": {"flying_sword": "/assets/../../outside.webp"}}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        pipeline().prepare_assets(tmp_path / "source", root)
    assert not (tmp_path / "outside.webp").exists()


def test_missing_source_does_not_replace_existing_art(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    manifest = {"cards": {"flying_sword": "/assets/cards/flying_sword.webp"}}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        pipeline().prepare_assets(tmp_path / "source", root)
    assert not (root / "cards").exists()


def test_batch_writes_real_webp_and_reports_source_and_output_hashes(tmp_path):
    root, source = tmp_path / "assets", tmp_path / "source"
    root.mkdir()
    source.mkdir()
    manifest = {"cards": {"flying_sword": "/assets/cards/flying_sword.webp"}}
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    Image.new("RGB", (1024, 768), (20, 120, 110)).save(source / "flying_sword-source.png")
    report = pipeline().prepare_assets(source, root)
    with Image.open(root / "cards/flying_sword.webp") as image:
        assert image.format == "WEBP"
        assert image.size == (768, 576)
    assert len(report) == 1
    assert len(report[0]["source_sha256"]) == 64
    assert len(report[0]["output_sha256"]) == 64
    assert report[0]["url"] == "/assets/cards/flying_sword.webp"
    with pytest.raises(FileExistsError):
        pipeline().prepare_assets(source, root)
