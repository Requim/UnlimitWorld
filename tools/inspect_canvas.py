"""Sample an actual browser PNG; does not certify artwork or visual quality."""

from __future__ import annotations

from io import BytesIO
import json
import sys

from PIL import Image, UnidentifiedImageError


def inspect_png(payload: bytes) -> dict[str, int]:
    """Return PNG dimensions and color samples; invalid/non-PNG data raises ValueError."""
    try:
        with Image.open(BytesIO(payload)) as image:
            if image.format != "PNG":
                raise ValueError("Expected PNG screenshot")
            image.load()
            width, height = image.size
            probe = image.convert("RGBA").resize((64, 64), Image.Resampling.NEAREST)
            pixels = probe.load()
            colors = {pixels[x, y] for x in range(64) for y in range(64)}
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("Invalid PNG screenshot") from error
    return {"width": width, "height": height, "samples": 4096, "uniqueColors": len(colors)}


def main() -> int:
    """Read PNG bytes from stdin and print metrics as JSON; invalid input exits nonzero."""
    print(json.dumps(inspect_png(sys.stdin.buffer.read())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
