# Evaluation

Batch selection and split data live in `datasets/`; frozen Qwen prompts live in `baseline_prompts_v1.0.json`; raw and parsed model outputs live in `predictions/`; custom metric definitions live in `rubrics/` and `design_rubric.py`.

`fiftyone_adapter.py` imports FiftyOne only when called. It creates a new dataset, keeps human-reviewed reference JSON separate from model output JSON, maps available boxes to detection fields, and offers an optional `evaluate_detections()` wrapper. It does not make FiftyOne a required dependency.

FiftyOne's documented sample model uses `Sample(filepath=...)` and `Dataset.add_sample(s)`; its detection evaluator compares prediction and ground-truth fields. See the [dataset guide](https://docs.voxel51.com/user_guide/using_datasets.html) and [detection evaluation guide](https://docs.voxel51.com/user_guide/evaluation/detections.html). Bounding-box scores describe localization only; they do not measure design intelligence.
