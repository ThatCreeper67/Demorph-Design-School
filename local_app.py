"""Loopback-only local web app for the demorph Phase 5 design agent."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID, uuid4

from run_phase5_pilot import MODEL, analyze_image_bytes, request_json

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "webui"
DATA_ROOT = ROOT / "local_app_data"
UPLOAD_ROOT = DATA_ROOT / "uploads"
DB_PATH = DATA_ROOT / "history.sqlite3"
OLLAMA_URL = os.environ.get("DEMORPH_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MAX_UPLOAD_MB = max(1, min(100, int(os.environ.get("DEMORPH_MAX_UPLOAD_MB", "25"))))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_PIXELS = 80_000_000
ALLOWED = {"JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png"), "WEBP": (".webp", "image/webp")}
STAGES = {
    "queued": "Queued",
    "checking_model": "Checking the required Ollama model",
    "preparing_visual_input": "Preparing the original image input",
    "applying_curriculum": "Retrieving relevant design curriculum",
    "analyzing_with_qwen": "Qwen is analyzing the design (this can take a few minutes)",
    "validating_analysis": "Checking evidence and result references",
    "saving_result": "Saving this analysis to local history",
    "complete": "Analysis complete",
    "partial": "Analysis finished with limitations",
    "failed": "Analysis failed",
    "cancel_requested": "Cancellation requested; waiting for the active model call",
    "cancelled": "Analysis cancelled; result discarded",
}

_DB_LOCK = threading.RLock()
_JOB_LOCK = threading.RLock()
_JOBS: dict[str, dict] = {}
_ACTIVE_JOB: str | None = None
_LOGGER = logging.getLogger("demorph.local_app")


class AnalysisCancelled(Exception):
    """Cooperative cancellation before or after the non-interruptible model call."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_storage() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    (DATA_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    with _DB_LOCK, closing(sqlite3.connect(DB_PATH)) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS analyses (
            analysis_id TEXT PRIMARY KEY, source_filename TEXT NOT NULL, stored_filename TEXT NOT NULL,
            mime_type TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
            size_bytes INTEGER NOT NULL, image_sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
            status TEXT NOT NULL, stage TEXT NOT NULL, error_code TEXT, error_message TEXT,
            result_json TEXT)""")
        db.commit()


def setup_logging() -> None:
    handler = RotatingFileHandler(DATA_ROOT / "logs" / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _LOGGER.setLevel(logging.INFO)
    if not _LOGGER.handlers:
        _LOGGER.addHandler(handler)


def db_execute(sql: str, params: tuple = (), *, fetch: bool = False):
    with _DB_LOCK, closing(sqlite3.connect(DB_PATH, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        cur = db.execute(sql, params)
        rows = cur.fetchall() if fetch else None
        db.commit()
        return rows


def inspect_image(data: bytes) -> tuple[str, str, int, int]:
    """Identify and decode supported raster input without transforming its bytes."""
    if not data:
        raise ValueError("The selected file is empty.")
    if data.startswith(b"\xff\xd8\xff"):
        fmt = "JPEG"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt = "PNG"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        fmt = "WEBP"
    else:
        raise ValueError("This file is not a supported PNG, JPG, or WEBP image.")
    mime = ALLOWED[fmt][1]
    try:
        from io import BytesIO
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        with Image.open(BytesIO(data)) as image:
            if image.format != fmt:
                raise ValueError("Image file content does not match its format signature.")
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PIXELS:
                raise ValueError(f"Image dimensions exceed the local limit ({MAX_PIXELS:,} pixels).")
            image.verify()
    except ImportError:
        width, height = image_dimensions_header(data, fmt)
    except Exception as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("The image file is damaged or cannot be decoded.") from exc
    if not width or not height or width > 30_000 or height > 30_000 or width * height > MAX_PIXELS:
        raise ValueError(f"Image dimensions exceed the local limit ({MAX_PIXELS:,} pixels).")
    return fmt, mime, width, height


def image_dimensions_header(data: bytes, fmt: str) -> tuple[int, int]:
    """Small fallback dimension reader for systems without Pillow."""
    if fmt == "PNG" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if fmt == "WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            return int.from_bytes(data[26:28], "little") & 0x3fff, int.from_bytes(data[28:30], "little") & 0x3fff
        if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2f:
            b1,b2,b3,b4=data[21:25]
            return 1 + b1 + ((b2 & 0x3f) << 8), 1 + (b2 >> 6) + (b3 << 2) + ((b4 & 0x0f) << 10)
    if fmt == "JPEG":
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            offset += 2
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset:offset + 2], "big")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF) and offset + 7 <= len(data):
                return int.from_bytes(data[offset + 5:offset + 7], "big"), int.from_bytes(data[offset + 3:offset + 5], "big")
            if length < 2:
                break
            offset += length
    raise ValueError("Could not read the image dimensions. Install Pillow only if you need this fallback on your system.")


def safe_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, HTTPError):
        return "ollama_error", "Ollama returned an error while analyzing this image. Check its local logs and retry."
    if isinstance(exc, TimeoutError):
        return "timeout", "The analysis timed out. Check the local Ollama service and try again."
    if isinstance(exc, URLError):
        return "ollama_unavailable", "The local Ollama service could not be reached. Start Ollama and try again."
    if isinstance(exc, RuntimeError) and "model" in str(exc).lower():
        return "model_unavailable", f"The required model {MODEL} is not available. This app will not download or substitute a model."
    if isinstance(exc, ValueError):
        return "invalid_analysis", "The model response was incomplete or could not pass validation. No result was marked complete."
    return "analysis_error", "The analysis could not be completed. Check the local application log for details."


def update_job(analysis_id: str, *, status: str | None = None, stage: str | None = None,
               error_code: str | None = None, error_message: str | None = None, result: dict | None = None) -> None:
    values = {}
    if status is not None: values["status"] = status
    if stage is not None: values["stage"] = stage
    if error_code is not None: values["error_code"] = error_code
    if error_message is not None: values["error_message"] = error_message
    if result is not None: values["result_json"] = json.dumps(result, ensure_ascii=False)
    if values:
        clause = ", ".join(f"{key}=?" for key in values)
        db_execute(f"UPDATE analyses SET {clause} WHERE analysis_id=?", (*values.values(), analysis_id))
    with _JOB_LOCK:
        job = _JOBS.get(analysis_id)
        if job:
            if status is not None: job["status"] = status
            if stage is not None: job["stage"] = stage
            if error_code is not None: job["error_code"] = error_code
            if error_message is not None: job["error_message"] = error_message


def run_analysis(analysis_id: str, image: dict, image_bytes: bytes, brief: str | None) -> None:
    global _ACTIVE_JOB
    try:
        update_job(analysis_id, status="running", stage="checking_model")
        def on_stage(stage: str) -> None:
            with _JOB_LOCK:
                job = _JOBS.get(analysis_id, {})
                if job.get("cancel_requested"):
                    update_job(analysis_id, status="cancel_requested", stage="cancel_requested")
                    raise AnalysisCancelled()
            update_job(analysis_id, status="running", stage=stage)

        annotation, _response, _elapsed = analyze_image_bytes(
            ROOT, image, image_bytes, brief=brief, base_url=OLLAMA_URL,
            timeout=int(os.environ.get("DEMORPH_ANALYSIS_TIMEOUT", "600")), on_stage=on_stage,
        )
        with _JOB_LOCK:
            cancelled = _JOBS.get(analysis_id, {}).get("cancel_requested", False)
        if cancelled:
            update_job(analysis_id, status="cancelled", stage="cancelled")
            return
        update_job(analysis_id, status="running", stage="saving_result")
        partial = any("Curriculum retrieval unavailable" in item or "Suppressed optional specialist" in item
                      for item in annotation.get("uncertainties", []))
        final_status = "partial" if partial else "complete"
        with _JOB_LOCK:
            if _JOBS.get(analysis_id, {}).get("cancel_requested", False):
                update_job(analysis_id, status="cancelled", stage="cancelled")
            else:
                update_job(analysis_id, status=final_status, stage=final_status, result=annotation)
    except AnalysisCancelled:
        update_job(analysis_id, status="cancelled", stage="cancelled")
    except Exception as exc:
        _LOGGER.exception("Analysis %s failed (%s)", analysis_id, type(exc).__name__)
        code, message = safe_error(exc)
        update_job(analysis_id, status="failed", stage="failed", error_code=code, error_message=message)
    finally:
        with _JOB_LOCK:
            if _ACTIVE_JOB == analysis_id:
                _ACTIVE_JOB = None


def multipart_fields(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:
    envelope = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii") + body)
    message = BytesParser(policy=policy.default).parsebytes(envelope)
    if not message.is_multipart():
        raise ValueError("Expected a multipart image upload.")
    fields = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        fields[name] = (filename, part.get_payload(decode=True) or b"")
    return fields


def valid_uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        return None


def history_row(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in ("analysis_id", "source_filename", "mime_type", "width", "height", "size_bytes", "image_sha256", "created_at", "status", "stage", "error_code", "error_message")}


class LocalHandler(BaseHTTPRequestHandler):
    server_version = "DemorphLocal/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        # Do not log request bodies, filenames, or result content.
        _LOGGER.info("HTTP %s", fmt % args)

    def _security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")

    def send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and host in {"localhost", "127.0.0.1", "::1"}

    def _body(self, max_bytes: int) -> bytes:
        try: length = int(self.headers.get("Content-Length", "-1"))
        except ValueError: length = -1
        if length < 0 or length > max_bytes:
            raise ValueError(f"Request exceeds the configured upload limit of {MAX_UPLOAD_MB} MB.")
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError("The upload ended before all bytes arrived.")
        return data

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        if path == "/api/health":
            self._health(); return
        if path == "/api/history":
            rows = db_execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT 50", fetch=True)
            self.send_json(200, {"items": [history_row(row) for row in rows]}); return
        if path.startswith("/api/jobs/"):
            self._job(path.rsplit("/", 1)[-1]); return
        if path.startswith("/api/results/"):
            self._result(path.rsplit("/", 1)[-1]); return
        if path.startswith("/api/uploads/"):
            self._upload(path.rsplit("/", 1)[-1]); return
        if path.startswith("/api/export/"):
            self._export(path.rsplit("/", 1)[-1]); return
        if path == "/" or path.startswith("/assets/"):
            self._static(path); return
        self.send_json(404, {"error": "not_found", "message": "Page not found."})

    def do_POST(self):
        if not self._origin_ok():
            self.send_json(403, {"error": "origin_rejected", "message": "This local app accepts requests from localhost only."}); return
        parsed = urlsplit(self.path)
        if parsed.path == "/api/analyze":
            self._analyze(); return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
            self._cancel(parsed.path.split("/")[-2]); return
        self.send_json(404, {"error": "not_found", "message": "Endpoint not found."})

    def _static(self, path: str):
        relative = "index.html" if path == "/" else path.removeprefix("/assets/")
        target = (WEB_ROOT / relative).resolve()
        if WEB_ROOT.resolve() not in target.parents or not target.is_file():
            self.send_json(404, {"error": "not_found", "message": "Asset not found."}); return
        data = target.read_bytes()
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith(("text/", "application/javascript")) else ""))
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _health(self):
        model_ok, detail = False, None
        try:
            tags = request_json(OLLAMA_URL + "/api/tags", timeout=2)
            model_ok = MODEL in {item.get("name") for item in tags.get("models", [])}
            if not model_ok: detail = f"Required model tag not found: {MODEL}"
        except Exception as exc:
            detail = type(exc).__name__
        self.send_json(200, {"app": "ok", "ollama": "ready" if model_ok else "unavailable", "model": MODEL,
                             "model_available": model_ok, "upload_limit_mb": MAX_UPLOAD_MB,
                             "message": detail or "Local analysis is ready."})

    def _analyze(self):
        global _ACTIVE_JOB
        try:
            content_type = self.headers.get("Content-Type", "")
            if not content_type.lower().startswith("multipart/form-data"):
                raise ValueError("Select an image file to upload.")
            body = self._body(MAX_UPLOAD_BYTES + 1_000_000)
            fields = multipart_fields(content_type, body)
            filename, image_bytes = fields.get("image", (None, b""))
            if not filename or not image_bytes:
                raise ValueError("The image upload is missing or empty.")
            if len(image_bytes) > MAX_UPLOAD_BYTES:
                raise ValueError(f"Choose an image smaller than {MAX_UPLOAD_MB} MB.")
            brief = fields.get("brief", (None, b""))[1].decode("utf-8", errors="replace").strip() or None
            if brief and len(brief) > 3000:
                raise ValueError("The optional brief must be 3,000 characters or fewer.")
            fmt, mime, width, height = inspect_image(image_bytes)
            original_name = re.split(r"[/\\]", filename)[-1].strip()[:180] or "uploaded-image"
            ext = ALLOWED[fmt][0]
            analysis_id = str(uuid4())
            with _JOB_LOCK:
                if _ACTIVE_JOB is not None:
                    raise RuntimeError("An analysis is already running. Wait for it to finish before starting another.")
                _ACTIVE_JOB = analysis_id
            stored_name = f"{analysis_id}{ext}"
            upload_path = UPLOAD_ROOT / stored_name
            with upload_path.open("xb") as uploaded:
                uploaded.write(image_bytes)
            image_sha = sha256(image_bytes).hexdigest()
            created = utc_now()
            db_execute("""INSERT INTO analyses (analysis_id,source_filename,stored_filename,mime_type,width,height,size_bytes,image_sha256,created_at,status,stage)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                       (analysis_id, original_name, stored_name, mime, width, height, len(image_bytes), image_sha, created, "queued", "queued"))
            image_info = {"image_id": "upload_" + analysis_id.replace("-", ""), "sha256": image_sha,
                          "relative_path": "local_app_data/uploads/" + stored_name}
            with _JOB_LOCK:
                _JOBS[analysis_id] = {"analysis_id": analysis_id, "status": "queued", "stage": "queued",
                                      "image": image_info, "image_bytes": image_bytes, "brief": brief,
                                      "cancel_requested": False}
            thread = threading.Thread(target=run_analysis, args=(analysis_id, image_info, image_bytes, brief), daemon=True)
            thread.start()
            self.send_json(202, {"analysis_id": analysis_id, "status": "queued", "stage": "queued",
                                 "message": STAGES["queued"]})
        except RuntimeError as exc:
            status = 409 if "already running" in str(exc) else 503
            self.send_json(status, {"error": "busy" if status == 409 else "startup_error", "message": str(exc)})
        except ValueError as exc:
            self.send_json(400, {"error": "invalid_upload", "message": str(exc)})
        except Exception as exc:
            _LOGGER.exception("Upload handling failed (%s)", type(exc).__name__)
            with _JOB_LOCK:
                if _ACTIVE_JOB and _ACTIVE_JOB not in _JOBS:
                    _ACTIVE_JOB = None
            self.send_json(500, {"error": "upload_error", "message": "The image could not be accepted. Check the local app log."})

    def _job(self, analysis_id: str):
        analysis_id = valid_uuid(analysis_id)
        if not analysis_id:
            self.send_json(404, {"error": "not_found", "message": "Analysis not found."}); return
        with _JOB_LOCK:
            job = _JOBS.get(analysis_id)
            if job:
                payload = {key: job.get(key) for key in ("analysis_id", "status", "stage", "error_code", "error_message")}
                payload["message"] = STAGES.get(job.get("stage"), "Working")
                self.send_json(200, payload); return
        self._result(analysis_id)

    def _result(self, analysis_id: str):
        analysis_id = valid_uuid(analysis_id)
        if not analysis_id:
            self.send_json(404, {"error": "not_found", "message": "Analysis not found."}); return
        rows = db_execute("SELECT * FROM analyses WHERE analysis_id=?", (analysis_id,), fetch=True)
        if not rows:
            self.send_json(404, {"error": "not_found", "message": "Analysis not found."}); return
        row = rows[0]
        payload = history_row(row)
        payload["image_url"] = f"/api/uploads/{analysis_id}"
        payload["result"] = json.loads(row["result_json"]) if row["result_json"] else None
        self.send_json(200, payload)

    def _upload(self, analysis_id: str):
        analysis_id = valid_uuid(analysis_id)
        if not analysis_id:
            self.send_json(404, {"error": "not_found", "message": "Image not found."}); return
        rows = db_execute("SELECT stored_filename,mime_type FROM analyses WHERE analysis_id=?", (analysis_id,), fetch=True)
        if not rows:
            self.send_json(404, {"error": "not_found", "message": "Image not found."}); return
        path = UPLOAD_ROOT / rows[0]["stored_filename"]
        if not path.is_file():
            self.send_json(404, {"error": "not_found", "message": "Stored image is unavailable."}); return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", rows[0]["mime_type"])
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", "inline")
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _export(self, suffix: str):
        fmt = "json" if suffix.endswith(".json") else "md" if suffix.endswith(".md") else None
        analysis_id = valid_uuid(suffix.rsplit(".", 1)[0] if "." in suffix else "")
        if not fmt or not analysis_id:
            self.send_json(404, {"error": "not_found", "message": "Export not found."}); return
        rows = db_execute("SELECT * FROM analyses WHERE analysis_id=? AND status IN ('complete','partial')", (analysis_id,), fetch=True)
        if not rows or not rows[0]["result_json"]:
            self.send_json(404, {"error": "not_found", "message": "A completed result is required for export."}); return
        row = rows[0]
        result = json.loads(row["result_json"])
        if fmt == "json":
            data, mime = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8"
            name = f"demorph-{analysis_id}.json"
        else:
            data, mime = markdown_report(row, result).encode("utf-8"), "text/markdown; charset=utf-8"
            name = f"demorph-{analysis_id}.md"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(data)

    def _cancel(self, analysis_id: str):
        analysis_id = valid_uuid(analysis_id)
        with _JOB_LOCK:
            job = _JOBS.get(analysis_id or "")
            if not job:
                self.send_json(404, {"error": "not_found", "message": "Active analysis not found."}); return
            if job.get("status") in {"complete", "failed", "cancelled"}:
                self.send_json(409, {"error": "not_cancellable", "message": "This analysis has already finished."}); return
            job["cancel_requested"] = True
        update_job(analysis_id, status="cancel_requested", stage="cancel_requested")
        self.send_json(202, {"analysis_id": analysis_id, "status": "cancel_requested", "stage": "cancel_requested",
                             "message": STAGES["cancel_requested"]})

def markdown_report(row: sqlite3.Row, result: dict) -> str:
    lines = ["# demorph Design Analysis", "", f"- **Image:** {row['source_filename']}",
             f"- **Analyzed:** {row['created_at']}", f"- **Dimensions:** {row['width']} × {row['height']}",
             f"- **Image SHA-256:** `{row['image_sha256']}`", f"- **Model:** {result['analysis_metadata']['model']}", ""]
    if result.get("brief_context"):
        lines += ["## Design brief", "", result["brief_context"], ""]
    sections = (("Visual observations", "observations", "text"), ("Element relationships", "relationships", "effect"),
                ("Design evaluations", "evaluations", "finding"), ("Recommendations", "recommendations", "change"),
                ("Specialist findings", "specialists", "finding"))
    for title, key, field in sections:
        items = result.get(key, [])
        if items:
            lines += [f"## {title}", ""]
            for item in items:
                lines.append(f"- {item.get(field, '')}")
                if item.get("impact"): lines.append(f"  - Likely impact: {item['impact']}")
                if item.get("interpretation"): lines.append(f"  - Why it matters: {item['interpretation']}")
                if item.get("expected_impact"): lines.append(f"  - Expected impact: {item['expected_impact']}")
            lines.append("")
    order = result.get("hierarchy", {}).get("apparent_order", [])
    if order:
        lines += ["## Apparent visual hierarchy", ""] + [f"{item['rank']}. {item['prominence_evidence']}" for item in order] + [""]
    uncertainties = result.get("uncertainties", [])
    if uncertainties:
        lines += ["## Uncertainty and limits", ""] + [f"- {item}" for item in uncertainties] + [""]
    lines += ["---", "Generated locally by demorph Design School. Model findings are unreviewed and should be checked against the image and brief.", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Must remain loopback-only")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true", help="Check local Ollama and required model; do not start the server")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("The local application must bind to loopback; external network binding is disabled.")
    ensure_storage(); setup_logging()
    if args.check:
        try:
            tags = request_json(OLLAMA_URL + "/api/tags", timeout=3)
            if MODEL not in {item.get("name") for item in tags.get("models", [])}:
                print(f"Ollama is reachable, but required model is missing: {MODEL}")
                raise SystemExit(1)
            print(f"Ready: Ollama and {MODEL} are available. No model download was attempted.")
            return
        except Exception as exc:
            print(f"Local model check failed: {type(exc).__name__}. Start Ollama and verify {MODEL} is installed.")
            raise SystemExit(1)
    server = ThreadingHTTPServer((args.host, args.port), LocalHandler)
    server.daemon_threads = True
    print(f"demorph Design School is ready at http://{args.host}:{args.port}")
    print("Keep this terminal open. Press Ctrl+C here to stop the local app.")
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nStopping local app…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
