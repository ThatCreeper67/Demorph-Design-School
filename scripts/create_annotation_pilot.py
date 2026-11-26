"""Create review worksheets: v1.0 blank drafts + dynamic v1.1 worksheets (additive)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on path for annotations module
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Import dynamic workflow functions for v1.1 generation
try:
    from annotations.dynamic_workflow import load_catalog, make_annotation, validate_annotation
except ImportError:
    # Allow script to run for v1.0 even if dynamic module has issues
    load_catalog = make_annotation = validate_annotation = None


def create_v10(root: Path) -> list[Path]:
    """Create five blank v1.0 review shells; this script never invents annotation labels."""
    root = root.resolve()
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    samples = [sample for sample in batch["samples"] if sample["dataset_split"] == "development"][:5]
    if len(samples) != 5:
        raise ValueError("Five development images are required for the annotation pilot")
    out = root / "annotations/drafts/batch_001"
    out.mkdir(parents=True, exist_ok=True)
    created = []
    for sample in samples:
        manifest_rows = [json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        image = next(row for row in manifest_rows if row["image_id"] == sample["image_id"])
        record = {
            "schema_version": "1.0.0",
            "image": {"image_id": image["image_id"], "sha256": image["sha256"], "relative_path": image["relative_path"]},
            "brief_context": None,
            "elements": [], "roles": [], "hierarchy": [], "principles": [], "evaluation": [],
            "critique": {"strengths": [], "weaknesses": [], "improvements": []},
            "human_review": {"reviewer_id_or_role": None, "status": "draft", "annotation_version": "1.0.0",
                             "reviewed_at": None, "disagreement_status": "not_reviewed", "correction_history": []},
        }
        target = out / f"{image['image_id']}.json"
        if target.exists():
            # Preserve any human work on repeat execution.
            created.append(target)
            continue
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md = [f"# Human review — {image['image_id']}", "", f"Image: `{image['relative_path']}`", f"SHA-256: `{image['sha256']}`", "",
              "This is a blank review worksheet. Add only claims supported by the image or a supplied brief. Label direct observation, model inference, human interpretation, and uncertainty separately.", "",
              "## Observe", "- Visible elements and locations:", "- Text transcribed with confidence:", "- Uncertain observations:", "",
              "## Classify", "- Element IDs and component types:", "- Functional roles with evidence:", "",
              "## Relate", "- Intended hierarchy (brief-based):", "- Apparent attention prediction (image-based):", "- Composition and spatial relationships:", "",
              "## Judge", "- Strengths with evidence:", "- Weaknesses with evidence:", "- Uncertainty or alternate interpretation:", "",
              "## Improve", "- Proposed change:", "- Expected impact:", "- Trade-offs:", "",
              "## Human review", "- Reviewer identifier or role:", "- Status: draft / in_review / approved / rejected", "- Disagreement and correction history:"]
        target.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
        created.append(target)
    return created


def create_v11(root: Path) -> list[Path]:
    """Create additive dynamic v1.1 worksheets for the five development pilot images."""
    if load_catalog is None or make_annotation is None or validate_annotation is None:
        raise RuntimeError("Dynamic workflow module not available; cannot create v1.1 worksheets")

    root = root.resolve()
    catalog = load_catalog(root)
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    samples = [sample for sample in batch["samples"] if sample["dataset_split"] == "development"][:5]
    if len(samples) != 5:
        raise ValueError("Five development images are required for the annotation pilot")

    # Load full image manifest for sha256 and relative_path
    manifest_rows = [json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    images = {row["image_id"]: row for row in manifest_rows}

    # Known signals from catalogue for cue matching
    known_signals = {signal for module in catalog["modules"] for signal in module["trigger_signals"] + module["suppress_signals"]}

    # Output to dynamic subdirectory (additive, not replacing v1.0)
    out = root / "annotations/drafts/dynamic/batch_001"
    out.mkdir(parents=True, exist_ok=True)

    created = []
    for sample in samples:
        image = images[sample["image_id"]]
        target = out / f"{image['image_id']}.json"
        if target.exists():
            # Preserve any existing draft
            created.append(target)
            continue

        # Build evidence from manifest selection rationale
        eid = f"manifest_{image['image_id']}"
        evidence = [{
            "evidence_id": eid,
            "text": sample.get("selection_rationale", "Curated batch description."),
            "source": "human_interpretation",
            "source_ref": None,
            "confidence": 0.6,
            "uncertainty": "medium"
        }]

        # Build cues from visual_tags that match catalogue signals
        cues = [
            {"signal": tag, "evidence_refs": [eid], "confidence": 0.6}
            for tag in sample.get("visual_tags", [])
            if tag in known_signals
        ]

        # Create v1.1 annotation using dynamic planner
        annotation = make_annotation(
            {k: image[k] for k in ("image_id", "sha256", "relative_path")},
            catalog=catalog,
            evidence=evidence if cues else [],
            cues=cues
        )

        # Validate the generated annotation
        validate_annotation(annotation, catalog)

        # Write JSON
        target.write_text(json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # Write Markdown review sheet
        md = [f"# Dynamic v1.1 human review — {image['image_id']}", "", f"Image: `{image['relative_path']}`", f"SHA-256: `{image['sha256']}`", "",
              "This worksheet was generated by the dynamic planner using manifest cues as planning hints.", "All claims must be verified against the poster before approval.", "",
              "## Universal foundation (always reviewed)", "1. **Observe** — Visible elements, text, uncertainties", "2. **Identify** — Components, groups, relationships", "3. **Hierarchy & Composition** — Intended vs apparent hierarchy, attention flow, spatial relationships", "4. **Judge** — Component assessments, overall strengths/weaknesses, impact on readability/hierarchy/communication", "5. **Improve** — Proposed changes with expected impact and trade-offs", ""]

        for section in annotation["specialist_sections"]:
            md += [f"## {section['heading']} ({section['scope']})", f"Selection rationale: {section['selection_rationale']}", "",
                   "**Focus questions:**"] + [f"- {q}" for q in section["subsections"][0]["focus_questions"]] + [""]

        omitted = [d for d in annotation["analysis_plan"]["module_decisions"] if d["decision"] == "omitted"]
        if omitted:
            md += ["## Suppressed or omitted sections"] + [f"- {d['heading']}: {d['rationale']}" for d in omitted] + [""]

        md += ["## Human review", "Status: draft. No claims have been approved.", "Reviewer: ___________________", "Date: ___________________"]
        target.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")

        created.append(target)
    return created


def create(root: Path) -> list[Path]:
    """Create both v1.0 and v1.1 worksheets (additive)."""
    v10_created = create_v10(root)
    v11_created = create_v11(root)
    return v10_created + v11_created


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version", choices=["v1.0", "v1.1", "both"], default="both", help="Which version to create")
    args = parser.parse_args()

    if args.version == "v1.0":
        paths = create_v10(Path(args.root))
    elif args.version == "v1.1":
        paths = create_v11(Path(args.root))
    else:
        paths = create(Path(args.root))

    for path in paths:
        print(path)
