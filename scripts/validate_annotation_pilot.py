"""Dependency-free checks for pilot draft records (v1.0 and v1.1)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def require_object(value: Any, required: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = required - value.keys()
    if missing:
        raise ValueError(f"{label} missing keys: {sorted(missing)}")


def validate_v10(root: Path) -> int:
    """Validate v1.0 pilot drafts."""
    root = root.resolve()
    schema = json.loads((root / "annotations/schemas/design_annotation_v1.0.json").read_text(encoding="utf-8"))
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or schema.get("version") != "1.0.0":
        raise ValueError("Unexpected v1.0 annotation schema identity")
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    dev_ids = {sample["image_id"] for sample in batch["samples"] if sample["dataset_split"] == "development"}
    files = sorted((root / "annotations/drafts/batch_001").glob("*.json"))
    if len(files) != 5:
        raise ValueError(f"Expected exactly five v1.0 pilot drafts; found {len(files)}")
    seen = set()
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != "1.0.0":
            raise ValueError(f"Expected v1.0 schema_version, got {data.get('schema_version')}: {path}")
        require_object(data, {"schema_version", "image", "brief_context", "elements", "roles", "hierarchy", "principles", "evaluation", "critique", "human_review"}, str(path))
        require_object(data["image"], {"image_id", "sha256", "relative_path"}, "image")
        require_object(data["critique"], {"strengths", "weaknesses", "improvements"}, "critique")
        require_object(data["human_review"], {"reviewer_id_or_role", "status", "annotation_version", "reviewed_at", "disagreement_status", "correction_history"}, "human_review")
        image_id = data["image"]["image_id"]
        if image_id not in dev_ids or image_id in seen:
            raise ValueError(f"Pilot must use unique development images only: {image_id}")
        seen.add(image_id)
        if not (root / data["image"]["relative_path"]).is_file():
            raise ValueError(f"Source image missing for {image_id}")
        if data["human_review"]["status"] != "draft" or data["human_review"]["reviewed_at"] is not None:
            raise ValueError(f"Pilot draft falsely indicates review: {image_id}")
        if any(data[key] for key in ("elements", "roles", "hierarchy", "principles", "evaluation")):
            raise ValueError(f"Pilot draft contains unreviewed labels: {image_id}")
    return len(files)


def validate_v11(root: Path) -> int:
    """Validate v1.1 pilot drafts using dynamic workflow cross-reference validation."""
    root = root.resolve()

    # Import dynamic workflow validator
    import sys
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from annotations.dynamic_workflow import load_catalog, validate_annotation

    catalog = load_catalog(root)
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    dev_ids = {sample["image_id"] for sample in batch["samples"] if sample["dataset_split"] == "development"}

    # Check dynamic subdirectory
    dyn_dir = root / "annotations/drafts/dynamic/batch_001"
    files = sorted(dyn_dir.glob("*.json"))
    if len(files) != 5:
        raise ValueError(f"Expected exactly five v1.1 pilot drafts; found {len(files)}")

    seen = set()
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != "1.1.0":
            raise ValueError(f"Expected v1.1 schema_version, got {data.get('schema_version')}: {path}")
        # Full cross-reference validation via dynamic workflow
        validate_annotation(data, catalog)

        image_id = data["image"]["image_id"]
        if image_id not in dev_ids or image_id in seen:
            raise ValueError(f"Pilot must use unique development images only: {image_id}")
        seen.add(image_id)
        if not (root / data["image"]["relative_path"]).is_file():
            raise ValueError(f"Source image missing for {image_id}")
        if data["human_review"]["status"] != "draft":
            raise ValueError(f"v1.1 pilot draft falsely indicates review: {image_id}")
        # v1.1 drafts should have empty foundation (no labels yet)
        foundation = data.get("foundation", {})
        for key in ("observe", "identify", "hierarchy_composition", "judge", "improve"):
            if key in foundation:
                section = foundation[key]
                if isinstance(section, list):
                    if section:  # non-empty list
                        raise ValueError(f"v1.1 pilot draft contains unreviewed labels in foundation.{key}: {image_id}")
                elif isinstance(section, dict):
                    # Check if any sub-array is non-empty
                    if any(v for v in section.values() if isinstance(v, list) and v):
                        raise ValueError(f"v1.1 pilot draft contains unreviewed labels in foundation.{key}: {image_id}")
                elif section:
                    raise ValueError(f"v1.1 pilot draft contains unreviewed labels in foundation.{key}: {image_id}")

    return len(files)


def validate(root: Path) -> tuple[int, int]:
    """Validate both v1.0 and v1.1 pilot drafts."""
    v10_count = validate_v10(root)
    v11_count = validate_v11(root)
    return v10_count, v11_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version", choices=["v1.0", "v1.1", "both"], default="both", help="Which version to validate")
    args = parser.parse_args()

    if args.version == "v1.0":
        count = validate_v10(Path(args.root))
        print(f"PASS: {count} v1.0 pilot draft records reference real development images and contain no labels.")
    elif args.version == "v1.1":
        count = validate_v11(Path(args.root))
        print(f"PASS: {count} v1.1 pilot draft records validated via cross-reference checks.")
    else:
        v10, v11 = validate(Path(args.root))
        print(f"PASS: {v10} v1.0 + {v11} v1.1 pilot draft records validated.")
