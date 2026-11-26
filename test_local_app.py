"""Local app API, validation, export, cancellation, and failure-path checks."""
from __future__ import annotations

import json
import struct
import tempfile
import time
import urllib.error
import urllib.request
import zlib
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread

import pytest

import local_app
import run_phase5_pilot
from annotations.phase5_intelligence import make_annotation


def chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)


def tiny_png() -> bytes:
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\x00\x00\xff\x00")) + chunk(b"IEND", b""))


def multipart(image: bytes, filename: str = "fixture.png", brief: str = "") -> tuple[str, bytes]:
    boundary = "----demorph-test-boundary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode() + image
    body += (f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"brief\"\r\n\r\n{brief}"
             f"\r\n--{boundary}--\r\n").encode()
    return f"multipart/form-data; boundary={boundary}", body


@pytest.fixture
def app_server(monkeypatch):
    scratch = tempfile.TemporaryDirectory(prefix=".local-app-test-", dir=local_app.ROOT)
    test_root = Path(scratch.name)
    monkeypatch.setattr(local_app, "DATA_ROOT", test_root / "app-data")
    monkeypatch.setattr(local_app, "UPLOAD_ROOT", test_root / "app-data" / "uploads")
    monkeypatch.setattr(local_app, "DB_PATH", test_root / "app-data" / "history.sqlite3")
    monkeypatch.setattr(local_app, "_JOBS", {})
    monkeypatch.setattr(local_app, "_ACTIVE_JOB", None)
    for handler in list(local_app._LOGGER.handlers):
        local_app._LOGGER.removeHandler(handler); handler.close()
    local_app.ensure_storage(); local_app.setup_logging()
    server = ThreadingHTTPServer(("127.0.0.1", 0), local_app.LocalHandler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown(); server.server_close(); thread.join(timeout=2)
    deadline = time.time() + 2
    while local_app._ACTIVE_JOB is not None and time.time() < deadline: time.sleep(.01)
    for handler in list(local_app._LOGGER.handlers):
        local_app._LOGGER.removeHandler(handler); handler.close()
    scratch.cleanup()


def post_image(base: str, data: bytes | None = None, *, filename="fixture.png", brief=""):
    content_type, body = multipart(data if data is not None else tiny_png(), filename, brief)
    request = urllib.request.Request(base + "/api/analyze", body, {"Content-Type": content_type}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def wait_job(base: str, analysis_id: str, timeout=5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        with urllib.request.urlopen(base + f"/api/jobs/{analysis_id}", timeout=3) as response:
            last = json.loads(response.read())
        if last["status"] in {"complete", "partial", "failed", "cancelled"}:
            return last
        time.sleep(.02)
    raise AssertionError(f"job did not finish: {last}")


def fixture_annotation(image, brief=None):
    raw = {"evidence":[{"evidence_id":"ev1","description":"Red headline on pale background","location":"top","confidence":.9}],
           "observations":[{"observation_id":"obs1","text":"A red headline anchors the upper area","role":"headline","evidence_refs":["ev1"],"confidence":.8}],
           "relationships":[],"hierarchy":{"apparent_order":[{"observation_ref":"obs1","rank":1,"prominence_evidence":"large scale and contrast","confidence":.8}],"reading_flow":[],"intended_priority":"unknown"},
           "evaluations":[],"recommendations":[],"specialists":[],"uncertainties":[]}
    return make_annotation(image, raw, curriculum_refs=[], model=run_phase5_pilot.MODEL, elapsed_ms=8, brief=brief)


def test_image_validation_and_multipart_parser():
    data = tiny_png()
    assert local_app.inspect_image(data) == ("PNG", "image/png", 2, 1)
    with pytest.raises(ValueError, match="supported"):
        local_app.inspect_image(b"not an image")
    fields = local_app.multipart_fields(*multipart(data, "my poster.png", "Festival brief"))
    assert fields["image"] == ("my poster.png", data)
    assert fields["brief"][1] == b"Festival brief"


def test_http_upload_history_image_preview_and_exports(app_server, monkeypatch):
    def fake_analyze(root, image, data, *, brief=None, base_url=None, timeout=None, on_stage=None):
        if on_stage: on_stage("preparing_visual_input")
        return fixture_annotation(image, brief), {"done_reason":"stop"}, 8
    monkeypatch.setattr(local_app, "analyze_image_bytes", fake_analyze)
    status, response = post_image(app_server, tiny_png(), brief="Keep the title most prominent")
    assert status == 202
    result = wait_job(app_server, response["analysis_id"])
    assert result["status"] == "complete"
    with urllib.request.urlopen(app_server + f"/api/results/{response['analysis_id']}") as response:
        stored = json.loads(response.read())
    assert stored["result"]["brief_context"] == "Keep the title most prominent"
    with urllib.request.urlopen(app_server + stored["image_url"]) as response:
        assert response.read() == tiny_png()
    with urllib.request.urlopen(app_server + "/api/history") as response:
        assert len(json.loads(response.read())["items"]) == 1
    with urllib.request.urlopen(app_server + f"/api/export/{stored['analysis_id']}.json") as response:
        assert json.loads(response.read())["schema_version"] == "1.2.0"
    with urllib.request.urlopen(app_server + f"/api/export/{stored['analysis_id']}.md") as response:
        assert b"Visual observations" in response.read()
    # The single-active-job gate clears after completion, so a second analysis starts.
    status2, second = post_image(app_server, tiny_png(), filename="second.png")
    assert status2 == 202
    assert wait_job(app_server, second["analysis_id"])["status"] == "complete"


def test_invalid_upload_and_ollama_health_are_reported(app_server, monkeypatch):
    monkeypatch.setattr(local_app, "OLLAMA_URL", "http://127.0.0.1:1")
    with urllib.request.urlopen(app_server + "/api/health") as response:
        assert json.loads(response.read())["model_available"] is False
    status, payload = post_image(app_server, b"bad data", filename="bad.png")
    assert status == 400 and payload["error"] == "invalid_upload"
    with urllib.request.urlopen(app_server + "/api/history") as response:
        assert json.loads(response.read())["items"] == []


def test_optional_component_failure_is_saved_as_partial(app_server, monkeypatch):
    def partial_analyze(root, image, data, *, brief=None, base_url=None, timeout=None, on_stage=None):
        annotation=fixture_annotation(image,brief)
        annotation["uncertainties"].append("Suppressed optional specialist typography: its evidence links were invalid.")
        return annotation, {}, 10
    monkeypatch.setattr(local_app, "analyze_image_bytes", partial_analyze)
    status, item=post_image(app_server)
    assert status==202
    assert wait_job(app_server,item["analysis_id"])["status"]=="partial"
    with urllib.request.urlopen(app_server+f"/api/export/{item['analysis_id']}.md") as response:
        assert b"Suppressed optional specialist" in response.read()


def test_safe_cancellation_discards_result(app_server, monkeypatch):
    started, release = Event(), Event()
    def slow_analyze(root, image, data, *, brief=None, base_url=None, timeout=None, on_stage=None):
        if on_stage: on_stage("analyzing_with_qwen")
        started.set(); release.wait(3)
        if on_stage: on_stage("validating_analysis")
        return fixture_annotation(image, brief), {}, 1000
    monkeypatch.setattr(local_app, "analyze_image_bytes", slow_analyze)
    status, item = post_image(app_server)
    assert status == 202 and started.wait(2)
    request = urllib.request.Request(app_server + f"/api/jobs/{item['analysis_id']}/cancel", data=b"", method="POST")
    with urllib.request.urlopen(request) as response:
        assert response.status == 202
    release.set()
    assert wait_job(app_server, item["analysis_id"])["status"] == "cancelled"


def test_truncated_and_empty_model_responses_fail_closed(monkeypatch):
    calls = iter([{"models":[{"name":run_phase5_pilot.MODEL}]}, {"done_reason":"length","response":"{}"}])
    monkeypatch.setattr(run_phase5_pilot, "request_json", lambda *args, **kwargs: next(calls))
    image = {"image_id":"fixture","sha256":"a"*64,"relative_path":"upload.png"}
    with pytest.raises(ValueError, match="output limit"):
        run_phase5_pilot.analyze_image_bytes(Path(__file__).resolve().parent, image, tiny_png())
    calls = iter([{"models":[{"name":run_phase5_pilot.MODEL}]}, {"done_reason":"stop","response":" "}])
    monkeypatch.setattr(run_phase5_pilot, "request_json", lambda *args, **kwargs: next(calls))
    with pytest.raises(ValueError, match="empty analysis"):
        run_phase5_pilot.analyze_image_bytes(Path(__file__).resolve().parent, image, tiny_png())
