"""Opt-in single-image JOJO adapter; never changes the bundled ImageGen tool."""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import nullcontext
from hashlib import sha256
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import time
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError


ENDPOINT = "https://api2.jojocode.com/v1/images/generations"
MODEL = "gpt-image-2"
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
IMAGE_EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
JOB_FIELDS = {"model", "prompt", "size", "quality", "output_format", "n", "out"}


class ImageGenerationError(RuntimeError):
    """A safe, fixed error code; messages never contain provider payloads or URLs."""


def build_payload(job: dict) -> dict:
    """Validate one PNG job and return its API payload without modifying its prompt.

    Accepts the existing single-job JSONL shape, n=1 and the approved model only.
    Raises ImageGenerationError before network or filesystem effects for invalid
    fields, filenames, quality or locally unsupported sizes.
    """
    if not isinstance(job, dict) or set(job) - JOB_FIELDS:
        raise ImageGenerationError("INVALID_JOB_FIELDS")
    if job.get("model", MODEL) != MODEL or type(job.get("n", 1)) is not int:
        raise ImageGenerationError("INVALID_MODEL_OR_COUNT")
    if job.get("n", 1) != 1 or job.get("output_format", "png") != "png":
        raise ImageGenerationError("SINGLE_PNG_REQUIRED")
    prompt = job.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 32000:
        raise ImageGenerationError("INVALID_PROMPT")
    quality = job.get("quality", "high")
    if quality not in ("low", "medium", "high", "auto"):
        raise ImageGenerationError("INVALID_QUALITY")
    name = job.get("out", "image.png")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}\.png", name):
        raise ImageGenerationError("INVALID_OUTPUT_NAME")
    size = job.get("size", "auto")
    _validate_size(size)
    return {"model": MODEL, "prompt": prompt, "size": size,
            "quality": quality, "output_format": "png", "n": 1}


def _validate_size(size: str) -> None:
    if size == "auto":
        return
    match = re.fullmatch(r"([0-9]{1,4})x([0-9]{1,4})", size) if isinstance(size, str) else None
    if not match:
        raise ImageGenerationError("INVALID_SIZE")
    width, height = map(int, match.groups())
    valid = (min(width, height) > 0 and max(width, height) <= 3840
             and width % 16 == height % 16 == 0
             and max(width, height) <= 3 * min(width, height)
             and 655360 <= width * height <= 8294400)
    if not valid:
        raise ImageGenerationError("INVALID_SIZE")


def _request_metadata(payload: dict) -> dict:
    return {**{key: value for key, value in payload.items() if key != "prompt"},
            "prompt_characters": len(payload["prompt"]),
            "prompt_sha256": sha256(payload["prompt"].encode("utf-8")).hexdigest()}


def _redacted_structure(value, depth: int = 0):
    if depth > 20:
        return {"type": "depth-limit"}
    if isinstance(value, str):
        return {"type": "string", "characters": len(value)}
    if isinstance(value, dict):
        return {_safe_field_name(key): _redacted_structure(item, depth + 1)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redacted_structure(item, depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return {"type": type(value).__name__}


def _safe_field_name(name: str) -> str:
    if len(name) <= 64 and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    return "redacted-field-" + sha256(name.encode("utf-8")).hexdigest()[:12]


def _write_report(root: Path, report: dict) -> None:
    staged = root / "response-report.json.part"
    staged.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    staged.replace(root / "response-report.json")


def _finish_report(root: Path, report: dict) -> None:
    try:
        _write_report(root, report)
    except OSError:
        saved = report["status"] == "saved"
        code = "IMAGE_SAVED_REPORT_WRITE_FAILED" if saved else "REPORT_WRITE_FAILED"
        report.update(status="saved-report-error" if saved else "failed", error_code=code)
        try:
            with (root / "failure-report.json").open("x", encoding="utf-8") as output:
                output.write(json.dumps(report, indent=2) + "\n")
        except OSError:
            pass
        raise ImageGenerationError(code) from None


def _bounded_body(response: httpx.Response, limit: int) -> bytes:
    chunks, size = [], 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > limit:
            raise ImageGenerationError("RESPONSE_TOO_LARGE")
        chunks.append(chunk)
    return b"".join(chunks)


def _generate_response(client: httpx.Client, payload: dict, key: str, report: dict) -> dict:
    report["image_posts"] = 1
    request = httpx.Request("POST", ENDPOINT, json=payload,
                            headers={"Authorization": f"Bearer {key}"})
    response = client.send(request, auth=None, stream=True, follow_redirects=False)
    try:
        report["http_status"] = response.status_code
        body = _bounded_body(response, MAX_RESPONSE_BYTES)
    finally:
        response.close()
    report["response_bytes"] = len(body)
    report["response_sha256"] = sha256(body).hexdigest()
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError):
        raise ImageGenerationError("NON_JSON_RESPONSE") from None
    report["response_structure"] = _redacted_structure(value)
    if report["http_status"] != 200:
        raise ImageGenerationError(f"API_HTTP_{report['http_status']}")
    return value


def _single_image(value: dict) -> dict:
    data = value.get("data") if isinstance(value, dict) else None
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ImageGenerationError("INVALID_IMAGE_DATA")
    return data[0]


def _decode_base64(value: str) -> bytes:
    if len(value) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ImageGenerationError("IMAGE_TOO_LARGE")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ImageGenerationError("INVALID_IMAGE_BASE64") from None
    if not decoded or len(decoded) > MAX_IMAGE_BYTES:
        raise ImageGenerationError("IMAGE_TOO_LARGE_OR_EMPTY")
    return decoded


def _public_image_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.port not in (None, 443)):
            raise ImageGenerationError("UNSAFE_IMAGE_URL")
        try:
            addresses = [ipaddress.ip_address(parsed.hostname)]
        except ValueError:
            addresses = [ipaddress.ip_address(item[4][0]) for item in
                         socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)]
        if not addresses or not all(address.is_global for address in addresses):
            raise ImageGenerationError("NON_PUBLIC_IMAGE_DESTINATION")
    except (ValueError, OSError):
        raise ImageGenerationError("INVALID_IMAGE_DESTINATION") from None


def _download_image(client: httpx.Client, url: str) -> bytes:
    for _ in range(4):
        _public_image_url(url)
        request = httpx.Request("GET", url)
        response = client.send(request, auth=None, stream=True, follow_redirects=False)
        try:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ImageGenerationError("MISSING_IMAGE_REDIRECT")
                url = urljoin(url, location)
                continue
            if response.status_code != 200:
                raise ImageGenerationError(f"IMAGE_HTTP_{response.status_code}")
            return _bounded_body(response, MAX_IMAGE_BYTES)
        finally:
            response.close()
    raise ImageGenerationError("TOO_MANY_IMAGE_REDIRECTS")


def _decode_data_url(url: str) -> bytes:
    header, separator, encoded = url.partition(",")
    if not separator or header not in (
            "data:image/png;base64", "data:image/jpeg;base64", "data:image/webp;base64"):
        raise ImageGenerationError("INVALID_IMAGE_DATA_URL")
    return _decode_base64(encoded)


def _image_bytes(client: httpx.Client, value: dict, report: dict, root: Path) -> bytes:
    item = _single_image(value)
    encoded = item.get("b64_json")
    if isinstance(encoded, str) and encoded.strip():
        report["source"] = "b64_json"
        _write_report(root, report)
        return _decode_base64(encoded)
    url = item.get("url")
    if isinstance(url, str) and url.strip():
        report["source"] = "data_url" if url.startswith("data:") else "url"
        _write_report(root, report)
        return _decode_data_url(url) if report["source"] == "data_url" else _download_image(client, url)
    raise ImageGenerationError("NO_IMAGE_BASE64_OR_URL")


def _inspect_image(data: bytes) -> tuple[str, tuple[int, int]]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            format_name, size = image.format, image.size
            if format_name not in IMAGE_EXTENSIONS or size[0] * size[1] > 16777216:
                raise ImageGenerationError("UNSUPPORTED_IMAGE")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ImageGenerationError("INVALID_IMAGE_BYTES") from None
    return format_name, size


def _save_image(root: Path, name: str, data: bytes, payload: dict, report: dict) -> None:
    format_name, size = _inspect_image(data)
    target = root / Path(name).with_suffix(IMAGE_EXTENSIONS[format_name]).name
    staged = root / "image.part"
    with staged.open("xb") as output:
        output.write(data)
    if target.exists():
        raise FileExistsError(target)
    staged.rename(target)
    requested = None if payload["size"] == "auto" else [
        int(edge) for edge in payload["size"].split("x")]
    report.update(status="saved", file=target.name, actual_format=format_name,
                  actual_size=list(size), requested_size=requested,
                  native_target_met=list(size) == requested if requested else None,
                  bytes=len(data), sha256=sha256(data).hexdigest())


def generate_image(job: dict, output_dir: Path, api_key: str, *,
                   allow_paid_request: bool = False,
                   client: httpx.Client | None = None) -> dict:
    """Generate one image, preserve native bytes and return a redacted evidence report.

    Args:
        job: Single approved-model job; prompt and API parameters are not augmented.
        output_dir: New attempt directory; existing directories are never reused.
        api_key: In-memory provider credential, sent only to the fixed API endpoint.
        allow_paid_request: Explicit opt-in for exactly one potentially billed POST.
        client: Optional hook-free client for offline transport tests; not closed here.
    Returns:
        Saved-image metadata including actual pixels, source format and SHA256.
    Raises:
        ImageGenerationError for API, download or image failures; FileExistsError
        for an existing attempt. A started attempt retains redacted diagnostics.
        No POST is retried, and no game assets or manifests are changed.
        Final report publication failure retains a verified image, raises a distinct
        safe error code and attempts to write failure-report.json for recovery.
    """
    payload = build_payload(job)
    if not allow_paid_request or not isinstance(api_key, str) or not api_key.strip():
        raise ImageGenerationError("API_KEY_REQUIRED" if allow_paid_request else "PAID_OPT_IN_REQUIRED")
    if client and any(client.event_hooks.values()):
        raise ImageGenerationError("CLIENT_HOOKS_NOT_SUPPORTED")
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {"status": "pending", "request": _request_metadata(payload),
              "image_posts": 0, "http_status": None, "billing_status": "unknown"}
    _write_report(root, report)
    started = time.monotonic()
    scope = nullcontext(client) if client else httpx.Client(timeout=600, trust_env=False)
    try:
        with scope as active:
            value = _generate_response(active, payload, api_key, report)
            _write_report(root, report)
            data = _image_bytes(active, value, report, root)
            _save_image(root, job.get("out", "image.png"), data, payload, report)
    except (ImageGenerationError, httpx.RequestError, httpx.InvalidURL, OSError) as error:
        code = str(error) if isinstance(error, ImageGenerationError) else type(error).__name__
        report.update(status="failed", error_code=code)
        raise ImageGenerationError(code) from None
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        _finish_report(root, report)
    return report


def main() -> int:
    """Run one JSON/JSONL job; default to a redacted dry-run with no network effects.

    Inputs are --input, --out-dir and optional --allow-paid-request. Live mode reads
    OPENAI_API_KEY only from process environment. Returns 0 on verified image save
    or dry-run, 1 on safe errors; never prints provider URLs, prompts or credentials.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--allow-paid-request", action="store_true")
    args = parser.parse_args()
    try:
        job = json.loads(args.input.read_text(encoding="utf-8"))
        payload = build_payload(job)
        if not args.allow_paid_request:
            print(json.dumps({"dry_run": True, **_request_metadata(payload)}, indent=2))
            return 0
        report = generate_image(job, args.out_dir, os.environ.get("OPENAI_API_KEY", ""),
                                allow_paid_request=True)
        print(json.dumps(report, indent=2))
        return 0
    except (ImageGenerationError, OSError, ValueError) as error:
        code = str(error) if isinstance(error, ImageGenerationError) else type(error).__name__
        if code == "IMAGE_SAVED_REPORT_WRITE_FAILED":
            print("Image saved; final report publication failed; do not regenerate.")
        else:
            print(f"Image generation failed: {code}; no automatic retry.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
