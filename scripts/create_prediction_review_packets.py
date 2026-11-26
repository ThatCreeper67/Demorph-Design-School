"""Make reviewer-facing packets without copying predictions into annotations."""
from __future__ import annotations

import json
from pathlib import Path


def create(root: Path) -> list[Path]:
    root = root.resolve()
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    image_rows = [json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    images = {row["image_id"]: row for row in image_rows}
    out = root / "annotations/drafts/batch_001/prediction_review"
    out.mkdir(parents=True, exist_ok=True)
    result = []
    for sample in [s for s in batch["samples"] if s["dataset_split"] == "development"][:5]:
        image_id = sample["image_id"]
        image = images[image_id]
        pred_dir = root / "evaluation/predictions/baseline_v1_2" / image_id
        lines = [
            f"# Prediction review packet — {image_id}", "",
            "**These are unverified model outputs, not annotations or ground truth.** Use them only as suggestions to inspect and correct. Write reviewed claims in the separate annotation worksheet.", "",
            f"- Image: `{image['original_filename']}`", f"- Dataset split: `{sample['dataset_split']}`",
            f"- Source image ID: `{image_id}`", "- Reference worksheet: `../" + image_id + ".md`", "",
        ]
        for prediction_path in sorted(pred_dir.glob("*.json")):
            if prediction_path.name == "run_manifest.json":
                continue
            record = json.loads(prediction_path.read_text(encoding="utf-8"))
            lines += [f"## {record['task_id']} — {record['status']}", "",
                      f"Archived record: `evaluation/predictions/baseline_v1_2/{image_id}/{prediction_path.name}`", ""]
            raw = record.get("raw_response")
            if raw:
                lines += ["Unverified raw response:", "", "```json", raw, "```", ""]
            else:
                lines += [f"No parseable response. Recorded error: `{record.get('parse_error') or record.get('error')}`", ""]
        target = out / f"{image_id}.md"
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result.append(target)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    for path in create(parser.parse_args().root):
        print(path)
