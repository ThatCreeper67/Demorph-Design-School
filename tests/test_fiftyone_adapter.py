import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from evaluation.fiftyone_adapter import FiftyOneUnavailable, _fiftyone, import_batch


def test_fiftyone_import_is_optional_and_clear_when_unavailable():
    with pytest.raises(FiftyOneUnavailable, match="not installed"):
        _fiftyone()


def test_adapter_import_contract_keeps_predictions_and_references_separate():
    class Sample(dict):
        def __init__(self, filepath):
            super().__init__()
            self.filepath = filepath

    class Dataset:
        def __init__(self, name):
            self.name = name
            self.samples = []
            self.info = {}

        def add_samples(self, samples):
            self.samples.extend(samples)

        def save(self):
            pass

    class FakeFiftyOne:
        @staticmethod
        def list_datasets():
            return []
        @staticmethod
        def Detections(detections):
            return detections
        @staticmethod
        def Detection(**kwargs):
            return kwargs

    FakeFiftyOne.Sample = Sample
    FakeFiftyOne.Dataset = Dataset

    root = Path(__file__).resolve().parents[1]
    # Temporarily move reviewed dir to ensure clean state for contract test
    reviewed_dir = root / "annotations/reviewed"
    backup_dir = root / "annotations/reviewed_test_backup"
    if reviewed_dir.exists():
        shutil.move(str(reviewed_dir), str(backup_dir))
    try:
        dataset = import_batch(root, split="development", dataset_name="test-contract", module=FakeFiftyOne)
        assert len(dataset.samples) == 20
        assert all("model_predictions_json" in sample for sample in dataset.samples)
        assert all("reference_annotation_json" in sample for sample in dataset.samples)
        assert all(sample["reference_annotation_json"] == "" for sample in dataset.samples)
    finally:
        if backup_dir.exists():
            shutil.move(str(backup_dir), str(reviewed_dir))
