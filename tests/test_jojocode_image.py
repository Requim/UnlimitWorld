"""Single-image provider compatibility, safe diagnostics and bounded downloads."""

import base64
import importlib
import io
import json
from pathlib import Path
from email.parser import BytesParser
from email.policy import default
from hashlib import sha256
import socket
import sys

import httpx
import pytest
from PIL import Image


KEY = "test-secret-not-a-real-key"
API = "https://api2.jojocode.com/v1/images/generations"
URL = "https://cdn.example.com/seed.png?signature=private-download-token"
JOB = {"prompt": "A majestic Bifang, full body.", "size": "2048x3072",
       "quality": "high", "output_format": "png", "n": 1, "out": "bifang-seed.png"}


def adapter():
    return importlib.import_module("tools.jojocode_image")


def bitmap(format_name="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", (32, 48), (40, 110, 160)).save(stream, format=format_name)
    return stream.getvalue()


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])


def execute(tmp_path, payload, image_bytes=None, status=200):
    calls = []

    def handle(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(status, json=payload)
        return httpx.Response(200, content=image_bytes or bitmap())

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = adapter().generate_image(
            JOB, tmp_path / "attempt", KEY, allow_paid_request=True, client=client)
    return result, calls


@pytest.mark.parametrize("base64_value", [None, ""])
def test_url_image_is_saved_when_base64_is_null_or_empty(tmp_path, base64_value):
    raw = bitmap()
    result, calls = execute(
        tmp_path, {"created": 123, "data": [{"b64_json": base64_value, "url": URL}]}, raw)
    assert (tmp_path / "attempt/bifang-seed.png").read_bytes() == raw
    assert result["source"] == "url"
    assert result["actual_size"] == [32, 48]
    assert result["requested_size"] == [2048, 3072]
    assert result["native_target_met"] is False
    assert [request.method for request in calls] == ["POST", "GET"]
    assert calls[0].url == API
    assert calls[0].headers["authorization"] == f"Bearer {KEY}"
    assert "authorization" not in calls[1].headers
    assert json.loads(calls[0].content) == {
        "model": "gpt-image-2", "prompt": JOB["prompt"], "size": "2048x3072",
        "quality": "high", "output_format": "png", "n": 1}


def test_url_image_is_saved_when_base64_field_is_missing(tmp_path):
    result, _ = execute(tmp_path, {"data": [{"url": URL}]})
    assert result["source"] == "url"
    assert result["status"] == "saved"
    report = json.loads((tmp_path / "attempt/response-report.json").read_text())
    assert report["response_structure"]["data"][0]["url"]["type"] == "string"
    assert "b64_json" not in report["response_structure"]["data"][0]


def test_base64_image_avoids_unnecessary_url_download(tmp_path):
    raw = bitmap()
    result, calls = execute(
        tmp_path, {"data": [{"b64_json": base64.b64encode(raw).decode(), "url": URL}]})
    assert result["source"] == "b64_json"
    assert (tmp_path / "attempt/bifang-seed.png").read_bytes() == raw
    assert len(calls) == 1


def test_inline_data_url_is_decoded_without_a_download(tmp_path):
    raw = bitmap()
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    result, calls = execute(tmp_path, {"data": [{"url": url}]})
    assert result["source"] == "data_url"
    assert (tmp_path / "attempt/bifang-seed.png").read_bytes() == raw
    assert len(calls) == 1


def test_download_does_not_inherit_caller_auth_or_cookies(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": URL}]})
        return httpx.Response(200, content=bitmap())

    with httpx.Client(transport=httpx.MockTransport(handle),
                      headers={"Authorization": f"Bearer {KEY}", "Cookie": KEY},
                      auth=httpx.BasicAuth("private-login", "private-password")) as client:
        adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                 allow_paid_request=True, client=client)
    assert calls[0].headers["authorization"] == f"Bearer {KEY}"
    assert "authorization" not in calls[1].headers
    assert "cookie" not in calls[1].headers
    assert "proxy-authorization" not in calls[1].headers


def test_client_default_query_and_custom_credentials_are_not_forwarded(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": URL}]})
        return httpx.Response(200, content=bitmap())

    with httpx.Client(transport=httpx.MockTransport(handle),
                      params={"api_key": KEY}, headers={"X-API-Key": KEY}) as client:
        adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                 allow_paid_request=True, client=client)
    assert str(calls[0].url) == API
    assert str(calls[1].url) == URL
    assert "x-api-key" not in calls[1].headers


def test_request_hooks_are_rejected_before_a_paid_request(tmp_path):
    calls = []

    def inject_secret(request):
        request.headers["X-API-Key"] = KEY

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={
            "data": [{"b64_json": base64.b64encode(bitmap()).decode()}]})

    with httpx.Client(transport=httpx.MockTransport(handle),
                      event_hooks={"request": [inject_secret]}) as client:
        with pytest.raises(adapter().ImageGenerationError):
            adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                     allow_paid_request=True, client=client)
    assert calls == []
    assert not (tmp_path / "attempt").exists()


def test_report_redacts_all_response_strings_and_prompt(tmp_path):
    result, _ = execute(tmp_path, {"data": [{"url": URL, "revised_prompt": KEY}],
                                    "extra": {"token": KEY, "link": URL}})
    text = (tmp_path / "attempt/response-report.json").read_text()
    assert KEY not in text
    assert URL not in text
    assert "private-download-token" not in text
    assert JOB["prompt"] not in text
    assert result["http_status"] == 200
    assert len(result["sha256"]) == 64


@pytest.mark.parametrize("payload", [
    {"data": []}, {"data": None}, {"data": [{}]}, {"data": [{"b64_json": None}]},
    {"data": [{"b64_json": "not-valid-base64"}]}, {"data": ["wrong-item"]},
    {"data": [{"url": URL}, {"url": URL}]}, [],
])
def test_malformed_results_leave_diagnostics_without_any_image(tmp_path, payload):
    with pytest.raises(adapter().ImageGenerationError):
        execute(tmp_path, payload)
    report = json.loads((tmp_path / "attempt/response-report.json").read_text())
    assert report["status"] == "failed"
    assert report["http_status"] == 200
    assert report["image_posts"] == 1
    assert not list((tmp_path / "attempt").glob("*.png"))


def test_http_error_never_repeats_paid_post_or_echoes_provider_secrets(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(500, json={"error": {"message": KEY + URL}})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(adapter().ImageGenerationError) as caught:
            adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                     allow_paid_request=True, client=client)
    assert len(calls) == 1
    assert KEY not in str(caught.value)
    assert URL not in str(caught.value)
    report = json.loads((tmp_path / "attempt/response-report.json").read_text())
    assert report["http_status"] == 500
    assert report["status"] == "failed"


def test_timeout_never_repeats_paid_post(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout(KEY + URL, request=request)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(adapter().ImageGenerationError) as caught:
            adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                     allow_paid_request=True, client=client)
    assert len(calls) == 1
    assert KEY not in str(caught.value)
    assert URL not in str(caught.value)
    report = json.loads((tmp_path / "attempt/response-report.json").read_text())
    assert report["status"] == "failed"
    assert report["billing_status"] == "unknown"


@pytest.mark.parametrize("url", [
    "http://cdn.example.com/image.png", "file:///C:/secret.png",
    "https://127.0.0.1/image.png", "https://[::1]/image.png",
    "https://10.0.0.1/image.png", "https://user:password@cdn.example.com/image.png",
    "https://cdn.example.com:8787/image.png",
])
def test_unsafe_image_urls_are_not_requested(tmp_path, url):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"data": [{"url": url}]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(adapter().ImageGenerationError):
            adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                     allow_paid_request=True, client=client)
    assert [request.method for request in calls] == ["POST"]


def test_private_dns_destination_is_not_requested(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.2", 443))])
    with pytest.raises(adapter().ImageGenerationError):
        execute(tmp_path, {"data": [{"url": URL}]})
    assert not list((tmp_path / "attempt").glob("*.png"))


def test_redirect_cannot_bypass_private_destination_guard(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"data": [{"url": URL}]})
        return httpx.Response(302, headers={"location": "https://127.0.0.1/secret"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(adapter().ImageGenerationError):
            adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                     allow_paid_request=True, client=client)
    assert len(calls) == 2
    assert "authorization" not in calls[1].headers


def test_html_download_is_not_saved_as_an_image(tmp_path):
    with pytest.raises(adapter().ImageGenerationError):
        execute(tmp_path, {"data": [{"url": URL}]}, b"<html>upstream error</html>")
    assert not list((tmp_path / "attempt").glob("*.png"))


def test_corrupt_png_crc_becomes_safe_failed_diagnostics(tmp_path):
    raw = bytearray(bitmap())
    offset = raw.index(b"IDAT")
    length = int.from_bytes(raw[offset - 4:offset], "big")
    raw[offset + 4 + length] ^= 1
    with pytest.raises(adapter().ImageGenerationError, match="INVALID_IMAGE_BYTES"):
        execute(tmp_path, {"data": [{"url": URL}]}, bytes(raw))
    report = json.loads((tmp_path / "attempt/response-report.json").read_text())
    assert report["status"] == "failed"
    assert not list((tmp_path / "attempt").glob("*.png"))


def test_final_report_failure_preserves_image_with_safe_recovery_report(tmp_path, monkeypatch):
    original = Path.replace

    def fail_saved_report(path, destination):
        if path.name == "response-report.json.part" and (
                json.loads(path.read_text())["status"] == "saved"):
            raise OSError(KEY + URL)
        return original(path, destination)

    monkeypatch.setattr(Path, "replace", fail_saved_report)
    with pytest.raises(adapter().ImageGenerationError,
                       match="IMAGE_SAVED_REPORT_WRITE_FAILED") as caught:
        execute(tmp_path, {"data": [{"url": URL}]})
    assert (tmp_path / "attempt/bifang-seed.png").read_bytes() == bitmap()
    report_text = (tmp_path / "attempt/failure-report.json").read_text()
    report = json.loads(report_text)
    assert report["status"] == "saved-report-error"
    assert report["file"] == "bifang-seed.png"
    assert report["actual_size"] == [32, 48]
    assert report["image_posts"] == 1
    assert KEY not in str(caught.value) + report_text
    assert URL not in str(caught.value) + report_text


def test_image_publication_failure_is_recorded_without_retry(tmp_path, monkeypatch):
    original = Path.rename
    calls = []

    def fail_image(path, destination):
        if Path(destination).name == "bifang-seed.png":
            raise OSError(KEY + URL)
        return original(path, destination)

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={
            "data": [{"b64_json": base64.b64encode(bitmap()).decode()}]})

    monkeypatch.setattr(Path, "rename", fail_image)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(adapter().ImageGenerationError) as caught:
            adapter().generate_image(JOB, tmp_path / "attempt", KEY,
                                     allow_paid_request=True, client=client)
    assert len(calls) == 1
    assert not (tmp_path / "attempt/bifang-seed.png").exists()
    report_text = (tmp_path / "attempt/response-report.json").read_text()
    assert json.loads(report_text)["status"] == "failed"
    assert KEY not in str(caught.value) + report_text
    assert URL not in str(caught.value) + report_text


def test_download_has_a_byte_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter(), "MAX_IMAGE_BYTES", 16)
    with pytest.raises(adapter().ImageGenerationError):
        execute(tmp_path, {"data": [{"url": URL}]}, b"a" * 17)
    assert not list((tmp_path / "attempt").glob("*.png"))


def test_native_jpeg_bytes_keep_correct_extension_without_resizing(tmp_path):
    raw = bitmap("JPEG")
    result, _ = execute(tmp_path, {"data": [{"url": URL}]}, raw)
    assert result["file"] == "bifang-seed.jpg"
    assert result["actual_format"] == "JPEG"
    assert (tmp_path / "attempt/bifang-seed.jpg").read_bytes() == raw
    assert not (tmp_path / "attempt/bifang-seed.png").exists()


@pytest.mark.parametrize("changes", [
    {"n": 2}, {"out": "../escape.png"}, {"out": "C:/escape.png"},
    {"size": "2047x3072"}, {"model": "different-model"}, {"background": "transparent"},
])
def test_invalid_jobs_are_rejected_before_network_or_output(tmp_path, changes):
    calls = []
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: calls.append(request))) as client:
        with pytest.raises(adapter().ImageGenerationError):
            adapter().generate_image({**JOB, **changes}, tmp_path / "attempt", KEY,
                                     allow_paid_request=True, client=client)
    assert calls == []
    assert not (tmp_path / "attempt").exists()


def test_paid_request_requires_explicit_opt_in(tmp_path):
    with pytest.raises(adapter().ImageGenerationError):
        adapter().generate_image(JOB, tmp_path / "attempt", KEY)
    assert not (tmp_path / "attempt").exists()


def test_existing_attempt_cannot_be_overwritten_or_regenerated(tmp_path):
    target = tmp_path / "attempt"
    target.mkdir()
    old = target / "bifang-seed.png"
    old.write_bytes(b"existing user image")
    with pytest.raises(FileExistsError):
        adapter().generate_image(JOB, target, KEY, allow_paid_request=True)
    assert old.read_bytes() == b"existing user image"


def test_cli_defaults_to_redacted_dry_run_without_network(tmp_path, monkeypatch, capsys):
    input_path, target = tmp_path / "job.jsonl", tmp_path / "attempt"
    input_path.write_text(json.dumps(JOB), encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["jojocode_image", "--input", str(input_path),
                                     "--out-dir", str(target)])
    assert adapter().main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["model"] == "gpt-image-2"
    assert JOB["prompt"] not in json.dumps(report)
    assert not target.exists()


def test_cli_missing_key_fails_before_creating_attempt(tmp_path, monkeypatch, capsys):
    input_path, target = tmp_path / "job.jsonl", tmp_path / "attempt"
    input_path.write_text(json.dumps(JOB), encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["jojocode_image", "--input", str(input_path),
                                     "--out-dir", str(target), "--allow-paid-request"])
    assert adapter().main() == 1
    assert "API_KEY_REQUIRED" in capsys.readouterr().out
    assert not target.exists()


def test_cli_rejects_multi_job_input_before_any_paid_request(tmp_path, monkeypatch):
    input_path, target = tmp_path / "job.jsonl", tmp_path / "attempt"
    input_path.write_text(json.dumps(JOB) + "\n" + json.dumps(JOB), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["jojocode_image", "--input", str(input_path),
                                     "--out-dir", str(target), "--allow-paid-request"])
    assert adapter().main() == 1
    assert not target.exists()


def edit_execute(tmp_path, payload, status=200, calls=None):
    calls = [] if calls is None else calls
    reference = tmp_path / "reference.png"
    reference.write_bytes(bitmap())

    def handle(request):
        request.read()
        calls.append(request)
        return httpx.Response(status, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handle),
                      params={"api_key": KEY}, headers={"X-API-Key": KEY}) as client:
        report = adapter().edit_image(
            JOB, reference, tmp_path / "attempt", KEY,
            allow_paid_request=True, client=client)
    return report, calls, reference


def test_edit_uploads_exact_reference_and_preserves_approved_parameters(tmp_path):
    raw = bitmap()
    report, calls, reference = edit_execute(
        tmp_path, {"data": [{"b64_json": base64.b64encode(raw).decode()}]})
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "https://api2.jojocode.com/v1/images/edits"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert "x-api-key" not in request.headers
    message = BytesParser(policy=default).parsebytes(
        ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode()
        + request.content)
    fields = {part.get_param("name", header="content-disposition"): part
              for part in message.iter_parts()}
    assert fields["image[]"].get_payload(decode=True) == reference.read_bytes()
    assert fields["model"].get_content().strip() == "gpt-image-2"
    assert fields["prompt"].get_content().strip() == JOB["prompt"]
    assert fields["size"].get_content().strip() == "2048x3072"
    assert fields["n"].get_content().strip() == "1"
    assert fields["quality"].get_content().strip() == "high"
    assert fields["output_format"].get_content().strip() == "png"
    assert "input_fidelity" not in fields and "background" not in fields
    assert report["request"]["operation"] == "edit"
    assert report["request"]["reference_sha256"] == sha256(raw).hexdigest()
    assert report["request"]["reference_size"] == [32, 48]
    assert str(reference) not in json.dumps(report)


@pytest.mark.parametrize("contents", [b"not an image", b""])
def test_edit_invalid_reference_fails_before_network_or_output(tmp_path, contents):
    source = tmp_path / "reference.png"
    source.write_bytes(contents)
    calls = []
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: calls.append(request))) as client:
        with pytest.raises(adapter().ImageGenerationError):
            adapter().edit_image(JOB, source, tmp_path / "attempt", KEY,
                                 allow_paid_request=True, client=client)
    assert calls == []
    assert not (tmp_path / "attempt").exists()


def test_edit_missing_reference_is_safe_and_does_not_generate_without_it(tmp_path):
    with pytest.raises(adapter().ImageGenerationError, match="INVALID_REFERENCE_IMAGE"):
        adapter().edit_image(JOB, tmp_path / "private-missing.png",
                             tmp_path / "attempt", KEY, allow_paid_request=True)
    assert not (tmp_path / "attempt").exists()


def test_edit_http_failure_is_not_retried_or_replaced_by_generation(tmp_path):
    calls = []
    with pytest.raises(adapter().ImageGenerationError, match="API_HTTP_500"):
        edit_execute(tmp_path, {"error": {"message": KEY + URL}}, status=500, calls=calls)
    assert [str(request.url) for request in calls] == [
        "https://api2.jojocode.com/v1/images/edits"]
    report = json.loads((tmp_path / "attempt/response-report.json").read_text())
    assert report["image_posts"] == 1
    assert report["request"]["operation"] == "edit"
    assert KEY not in json.dumps(report) and URL not in json.dumps(report)


def test_edit_dry_run_inspects_reference_without_sending_or_echoing_it(
        tmp_path, monkeypatch, capsys):
    source, job = tmp_path / "reference.png", tmp_path / "job.json"
    source.write_bytes(bitmap())
    job.write_text(json.dumps(JOB))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["jojocode_image", "--input", str(job),
                                     "--image", str(source),
                                     "--out-dir", str(tmp_path / "attempt")])
    assert adapter().main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["operation"] == "edit"
    assert report["reference_size"] == [32, 48]
    assert str(source) not in json.dumps(report)
    assert not (tmp_path / "attempt").exists()


def test_live_cli_image_flag_sends_edit_and_never_generation(tmp_path, monkeypatch, capsys):
    source, job = tmp_path / "reference.png", tmp_path / "job.json"
    source.write_bytes(bitmap())
    job.write_text(json.dumps(JOB))
    calls = []

    def handle(request):
        request.read()
        calls.append(request)
        return httpx.Response(200, json={"data": [{
            "b64_json": base64.b64encode(bitmap()).decode()}]})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    monkeypatch.setattr(adapter().httpx, "Client", lambda **kwargs: client)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setattr(sys, "argv", ["jojocode_image", "--input", str(job),
                                     "--image", str(source), "--allow-paid-request",
                                     "--out-dir", str(tmp_path / "attempt")])
    assert adapter().main() == 0
    assert [str(request.url) for request in calls] == [
        "https://api2.jojocode.com/v1/images/edits"]
    assert KEY not in capsys.readouterr().out
    assert (tmp_path / "attempt/bifang-seed.png").read_bytes() == bitmap()
