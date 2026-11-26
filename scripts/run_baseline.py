"""Repeatable, local Ollama image baseline; raw model responses are retained."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any
from urllib.request import Request, urlopen


def ollama_tags(base_url: str) -> set[str]:
    request = Request(base_url.rstrip("/") + "/api/tags", method="GET")
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {item.get("name", "") for item in payload.get("models", [])}


def infer(base_url: str, model: str, image_path: Path, prompt: str, options: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
        "stream": False,
        "format": "json",
        "think": False,
        "options": options,
    }
    request = Request(base_url.rstrip("/") + "/api/generate", data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def run(root: Path, base_url: str = "http://127.0.0.1:11434", limit_images: int | None = None) -> dict[str, Any]:
    root = root.resolve()
    model = "qwen3.5:9b-q4_K_M"
    prompt_file = root / "evaluation/baseline_prompts_v1.0.json"
    prompt_spec = json.loads(prompt_file.read_text(encoding="utf-8"))
    if prompt_spec["model"] != model:
        raise ValueError("Prompt file model does not match the required Qwen tag")
    available = ollama_tags(base_url)
    if model not in available:
        raise RuntimeError(f"Required model tag unavailable; no substitution permitted: {model}")
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    samples = [sample for sample in batch["samples"] if sample["dataset_split"] == "development"]
    if limit_images is not None:
        samples = samples[:max(0, limit_images)]
    options = {"temperature": 0, "num_predict": 1200}
    prediction_root = root / "evaluation/predictions/baseline_v1_2"
    prediction_root.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result_index = []
    for sample in samples:
        image_rows = [json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        image = next(row for row in image_rows if row["image_id"] == sample["image_id"])
        image_path = root / image["relative_path"]
        for task in prompt_spec["tasks"]:
            output_path = prediction_root / sample["image_id"] / f"{task['task_id']}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                result_index.append({"image_id": sample["image_id"], "task_id": task["task_id"], "status": "already_present"})
                continue
            timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            t0 = time.perf_counter()
            try:
                response = infer(base_url, model, image_path, task["instruction"], options)
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                raw = response.get("response", "")
                try:
                    parsed = json.loads(raw)
                    status, parse_error = "ok", None
                except json.JSONDecodeError as exc:
                    parsed, status, parse_error = None, "parse_error", str(exc)
                record = {
                    "schema_version": "1.0.0", "model_identifier": model,
                    "quantization": "q4_K_M (tag suffix; runtime metadata not independently verified)",
                    "runtime": {"provider": "ollama", "base_url": base_url, "temperature": 0, "num_predict": 1200, "stream": False, "think": False},
                    "prompt_version": prompt_spec["prompt_version"], "prompt": task["instruction"],
                    "input_image_id": sample["image_id"], "input_sha256": image["sha256"],
                    "task_id": task["task_id"], "timestamp": timestamp, "inference_duration_ms": elapsed_ms,
                    "status": status, "raw_response": raw, "parsed_response": parsed, "parse_error": parse_error,
                    "ollama_done_reason": response.get("done_reason"), "error": None,
                }
            except Exception as exc:
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                record = {
                    "schema_version": "1.0.0", "model_identifier": model,
                    "quantization": "q4_K_M (tag suffix; runtime metadata not independently verified)",
                    "runtime": {"provider": "ollama", "base_url": base_url, "temperature": 0, "num_predict": 1200, "stream": False, "think": False},
                    "prompt_version": prompt_spec["prompt_version"], "prompt": task["instruction"],
                    "input_image_id": sample["image_id"], "input_sha256": image["sha256"],
                    "task_id": task["task_id"], "timestamp": timestamp, "inference_duration_ms": elapsed_ms,
                    "status": "error", "raw_response": None, "parsed_response": None, "parse_error": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result_index.append({"image_id": sample["image_id"], "task_id": task["task_id"], "status": record["status"], "duration_ms": record["inference_duration_ms"]})
            print(f"{sample['image_id']} {task['task_id']} {record['status']} {record['inference_duration_ms']}ms", flush=True)
    summary = {
        "schema_version": "1.0.0", "run_id": "baseline_v1_2", "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model_identifier": model,
        "prompt_version": prompt_spec["prompt_version"], "images_requested": len(samples),
        "tasks_per_image": len(prompt_spec["tasks"]), "results": result_index,
        "successful": sum(item["status"] == "ok" for item in result_index),
        "failed_or_malformed": sum(item["status"] in {"error", "parse_error"} for item in result_index),
        "note": "Predictions are model outputs, not reference annotations or ground truth.",
    }
    (prediction_root / "run_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--limit-images", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.ollama_url, args.limit_images), ensure_ascii=False, indent=2))
