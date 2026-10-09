"""Screenshot pixel probes do not certify formal art or visual quality."""

from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from tools.inspect_canvas import inspect_png


def image_bytes(with_content: bool) -> bytes:
    image = Image.new("RGBA", (160, 100), "white")
    if with_content:
        ImageDraw.Draw(image).rectangle((30, 20, 90, 70), fill="black")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_blank_screenshot_has_one_sampled_color():
    result = inspect_png(image_bytes(False))
    assert result["uniqueColors"] == 1
    assert (result["width"], result["height"]) == (160, 100)


def test_rendered_content_has_multiple_sampled_colors():
    result = inspect_png(image_bytes(True))
    assert result["uniqueColors"] == 2
    assert result["samples"] == 4096


def test_corrupt_screenshot_is_not_reported_as_nonblank():
    with pytest.raises(ValueError, match="PNG"):
        inspect_png(b"not a screenshot")
