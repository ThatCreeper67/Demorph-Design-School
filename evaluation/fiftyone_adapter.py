"""Optional FiftyOne bridge; the rest of Design School has no FiftyOne dependency."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FiftyOneUnavailable(RuntimeError):
    pass


def _fiftyone(module: Any = None) -> Any:
    if module is not None:
        return module
    try:
        import fiftyone as fo
    except ImportError as exc:
        raise FiftyOneUnavailable("FiftyOne is not installed. Install it only after explicit approval.") from exc
    return fo


def import_batch(root: str | Path, *, split: str = "development", dataset_name: str = "demorph-design-school-batch-001", module: Any = None) -> Any:
    """Create a new, non-destructive dataset and import manifest, reviewed labels, and predictions."""
    root = Path(root).resolve()
    fo = _fiftyone(module)
    if dataset_name in fo.list_datasets():
        raise ValueError(f"Dataset already exists; choose a new name to preserve it: {dataset_name}")
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    manifest = [json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    images = {row["image_id"]: row for row in manifest}
    reviewed = {}
    for path in (root / "annotations/reviewed").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("human_review", {}).get("status") == "approved":
            reviewed[record["image"]["image_id"]] = record
    prediction_root = root / "evaluation/predictions/baseline_v1_2"
    selected = [row for row in batch["samples"] if row["dataset_split"] == split]
    if split == "test" and not batch.get("held_out_test_isolated", True):
        raise ValueError("Held-out test isolation flag is false")
    dataset = fo.Dataset(name=dataset_name)
    samples = []
    for item in selected:
        image = images[item["image_id"]]
        filepath = root / image["relative_path"]
        sample = fo.Sample(filepath=str(filepath))
        sample["image_id"] = image["image_id"]
        sample["sha256"] = image["sha256"]
        sample["dataset_split"] = split
        sample["permission_status"] = image["permission_status"]
        sample["provenance_classification"] = image["provenance_classification"]
        annotation = reviewed.get(image["image_id"])
        prediction_records = []
        task_dir = prediction_root / image["image_id"]
        if task_dir.is_dir():
            for prediction_path in sorted(task_dir.glob("*.json")):
                if prediction_path.name == "run_manifest.json":
                    continue
                record = json.loads(prediction_path.read_text(encoding="utf-8"))
                if record.get("status") == "ok":
                    prediction_records.append(record)
        sample["reference_annotation_json"] = json.dumps(annotation, ensure_ascii=False) if annotation else ""
        sample["model_predictions_json"] = json.dumps(prediction_records, ensure_ascii=False) if prediction_records else ""
        if annotation:
            detections = _to_detections(annotation.get("elements", []), fo, "element_type", "bbox")
            sample["ground_truth_detections"] = fo.Detections(detections=detections)
        prediction_elements = []
        for record in prediction_records:
            if record.get("task_id") == "visual_elements":
                prediction_elements = record.get("parsed_response", {}).get("elements", [])
                break
        predicted_detections = _to_detections(prediction_elements, fo, "element_type", "bbox_normalized_or_null")
        sample["predicted_detections"] = fo.Detections(detections=predicted_detections)
        samples.append(sample)
    dataset.add_samples(samples)
    dataset.info["design_school_batch_id"] = "batch_001"
    dataset.info["design_school_split"] = split
    dataset.info["design_school_note"] = "Human references and model outputs are separate fields; predictions are not ground truth."
    dataset.save()
    return dataset


def _to_detections(elements: list[dict[str, Any]], fo: Any, label_key: str, bbox_key: str) -> list[Any]:
    detections = []
    for element in elements:
        box = element.get(bbox_key)
        if not isinstance(box, list) or len(box) != 4:
            continue
        x1, y1, x2, y2 = box
        if not all(isinstance(value, (int, float)) for value in box) or not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            continue
        detections.append(fo.Detection(label=str(element.get(label_key) or element.get("component_type") or "unknown"),
                                       bounding_box=[x1, y1, x2-x1, y2-y1]))
    return detections


def evaluate_boxes(dataset: Any, *, prediction_field: str = "predicted_detections", reference_field: str = "ground_truth_detections", eval_key: str = "design_bbox") -> Any:
    """Run standard spatial metrics only when reviewed boxes are present."""
    if not dataset.has_sample_field(prediction_field) or not dataset.has_sample_field(reference_field):
        raise ValueError("Both prediction and human-reference detection fields must be imported before box evaluation")
    return dataset.evaluate_detections(prediction_field, gt_field=reference_field, eval_key=eval_key, iou=0.5)


def launch(dataset: Any) -> Any:
    """Open the FiftyOne App for visual inspection."""
    fo = _fiftyone()
    return fo.launch_app(dataset)
