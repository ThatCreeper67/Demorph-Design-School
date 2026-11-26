"""Repeat one frozen image/task request and retain both responses for comparison."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import infer  # noqa: E402


def main(root: Path) -> None:
    root = root.resolve()
    run_dir = root / "evaluation/predictions/baseline_v1_2"
    baseline = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    first = next(row for row in baseline["results"] if row["status"] == "ok")
    image_id, task_id = first["image_id"], first["task_id"]
    stored = json.loads((run_dir / image_id / f"{task_id}.json").read_text(encoding="utf-8"))
    prompt_spec = json.loads((root / "evaluation/baseline_prompts_v1.0.json").read_text(encoding="utf-8"))
    task = next(item for item in prompt_spec["tasks"] if item["task_id"] == task_id)
    image_rows = [json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    image = next(row for row in image_rows if row["image_id"] == image_id)
    runtime = stored["runtime"]
    raw2 = infer(runtime["base_url"], stored["model_identifier"], root / image["relative_path"], task["instruction"],
                 {"temperature": runtime["temperature"], "num_predict": runtime["num_predict"]})
    response2 = raw2.get("response", "")
    try:
        parsed2 = json.loads(response2)
        valid2 = True
    except json.JSONDecodeError:
        parsed2, valid2 = None, False
    same = valid2 and json.dumps(parsed2, sort_keys=True, ensure_ascii=False) == json.dumps(stored["parsed_response"], sort_keys=True, ensure_ascii=False)
    record = {
        "schema_version": "1.0.0", "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "image_id": image_id, "task_id": task_id, "prompt_version": stored["prompt_version"],
        "model_identifier": stored["model_identifier"], "same_parsed_output": same,
        "original_raw_response": stored["raw_response"], "repeat_raw_response": response2,
        "repeat_parsed_response": parsed2, "repeat_done_reason": raw2.get("done_reason"),
    }
    (run_dir / "repeatability_check.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"same_parsed_output": same, "second_response_valid_json": valid2, "image_id": image_id, "task_id": task_id}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    main(parser.parse_args().root)
