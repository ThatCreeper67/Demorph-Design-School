"""Build a deterministic, rights-aware Batch 001 candidate and data split."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image

PICKED = [
    (3, ["typography_led", "minimalist"], "Spare type-led poster with a small photographic subject."),
    (8, ["cinematic", "typography_led"], "Large stacked message paired with a cinematic image."),
    (10, ["character_focused", "photographic"], "Portrait subject with strong type and red accent."),
    (11, ["experimental", "colour_driven"], "Blue map-like graphic and compact typography."),
    (14, ["illustrative", "colour_driven"], "Bright koi illustration and high-contrast title."),
    (16, ["illustrative_manga", "monochrome"], "Monochrome illustration with expressive lettering."),
    (21, ["experimental", "typography_led"], "Oversized star motif with crossing display text."),
    (23, ["dense_information", "illustrative"], "Floral illustration paired with multiple small text blocks."),
    (25, ["illustrative", "colour_driven"], "Folk-art-like illustration with saturated colors."),
    (26, ["cinematic", "typography_led"], "Portrait and large title treatment in a restrained palette."),
    (29, ["character_focused", "colour_driven"], "Vivid magenta composition with a prominent figure and type."),
    (32, ["illustrative_manga", "typography_led"], "Vertical monochrome illustrated poster with compact title."),
    (37, ["dense_information", "typography_led"], "Type-led layout with a large central word and smaller details."),
    (38, ["experimental", "typography_led"], "Expressive hand-drawn lettering as the main visual."),
    (40, ["typography_led", "minimalist"], "Large condensed type over a limited-color image."),
    (41, ["character_focused", "illustrative"], "Colorful fantasy figure with directional composition."),
    (43, ["illustrative", "colour_driven"], "Illustrated city scene with layered title treatment."),
    (49, ["experimental", "abstract"], "Abstract image and restrained event typography."),
    (50, ["illustrative_manga", "character_focused"], "Expressive comic illustration with Japanese lettering."),
    (53, ["dense_information", "colour_driven"], "Compact graphic and type system over a dark palette."),
    (54, ["minimalist", "illustrative"], "Open blue composition with a centered illustrated subject."),
    (56, ["dense_information", "typography_led"], "Small type blocks and strong black-and-white contrast."),
    (57, ["typography_led", "experimental"], "Editorial-scale type with intentionally fragmented words."),
    (60, ["character_focused", "colour_driven"], "Neon-lit portrait and compact display title."),
    (65, ["illustrative", "dense_information"], "Detailed cultural illustration surrounded by small copy."),
    (70, ["minimalist", "cinematic"], "Small silhouetted subject in a broad orange field."),
    (76, ["experimental", "colour_driven"], "Geometric, saturated lettering on a pale ground."),
    (77, ["photographic", "character_focused"], "Large photographic portrait and understated supporting text."),
    (83, ["typography_led", "colour_driven"], "Short message presented with a bold, saturated graphic."),
    (94, ["dense_information", "illustrative_manga"], "Information-dense comic page with multiple labeled regions."),
]


def perceptual_hash(path: Path) -> int:
    n, k = 32, 8
    cos = [[math.cos(math.pi * (2 * x + 1) * u / (2 * n)) for x in range(n)] for u in range(k)]
    with Image.open(path) as image:
        pixels = list(image.convert("L").resize((n, n)).getdata())
    coefficients = []
    for v in range(k):
        for u in range(k):
            coefficients.append(sum(pixels[y*n+x] * cos[u][x] * cos[v][y] for y in range(n) for x in range(n)))
    median = sorted(coefficients[1:])[len(coefficients[1:]) // 2]
    return sum(1 << i for i, value in enumerate(coefficients) if value > median)


def split_sizes(count: int) -> dict[str, int]:
    if count >= 30:
        return {"development": 20, "validation": 5, "test": 5}
    development = round(count * (2 / 3))
    validation = round(count / 6)
    return {"development": development, "validation": validation, "test": count - development - validation}


def prepare(root: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / "manifests" / "image_manifest.jsonl"
    rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) < 1:
        raise ValueError("No indexed images available")
    chosen = []
    for ordinal, tags, rationale in PICKED:
        if ordinal <= len(rows):
            row = rows[ordinal - 1]
            chosen.append({"image_id": row["image_id"], "visual_tags": tags, "selection_rationale": rationale})
    if len(rows) < 30:
        selected_ids = {item["image_id"] for item in chosen}
        for row in rows:
            if row["image_id"] not in selected_ids:
                chosen.append({"image_id": row["image_id"], "visual_tags": ["visual_review_needed"],
                               "selection_rationale": "Partial dataset fallback; requires human visual categorization."})
    chosen = chosen[:30]
    ids = {item["image_id"] for item in chosen}
    selected_rows = {row["image_id"]: row for row in rows if row["image_id"] in ids}
    hashes = {image_id: perceptual_hash(root / selected_rows[image_id]["relative_path"]) for image_id in ids}
    near_pairs = []
    ordered = sorted(ids)
    for pos, left in enumerate(ordered):
        for right in ordered[pos+1:]:
            distance = (hashes[left] ^ hashes[right]).bit_count()
            if distance <= 8:
                near_pairs.append({"image_ids": [left, right], "phash_hamming_distance": distance})
    if near_pairs:
        raise ValueError(f"Batch selection contains perceptual near-duplicates (threshold <=8): {near_pairs}")
    if len(chosen) >= 30 and len(chosen) != 30:
        raise ValueError("Batch 001 selection count must be 30 when 30 candidates are available")

    sizes = split_sizes(len(chosen))
    ranked = sorted(chosen, key=lambda item: hashlib.sha256(("design-school-batch001-v1:" + item["image_id"]).encode()).hexdigest())
    cursor, split_by_id = 0, {}
    for split, size in sizes.items():
        for item in ranked[cursor:cursor+size]:
            split_by_id[item["image_id"]] = split
        cursor += size
    for item in chosen:
        item["dataset_split"] = split_by_id[item["image_id"]]
        item["permission_status"] = "unconfirmed"
        item["provenance_classification"] = "unknown"
        item["training_eligible"] = False
    if len(chosen) >= 30 and sizes != {"development": 20, "validation": 5, "test": 5}:
        raise AssertionError("Unexpected full-batch split sizes")
    if set(split_by_id) != ids:
        raise AssertionError("Split assignment is incomplete")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batch = {
        "schema_version": "1.0.0", "batch_id": "batch_001", "created_at": now,
        "selection_method": "human-curated visual diversity review; deterministic source ordering and split seed",
        "rights_note": "All selected images have unconfirmed rights and are excluded from training exports.",
        "perceptual_hash": {"method": "64-bit DCT perceptual hash", "near_duplicate_threshold_hamming": 8, "near_duplicate_pairs_in_batch": near_pairs},
        "split_sizes": sizes, "samples": chosen,
    }
    evaluation_dir = root / "evaluation" / "datasets"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    (evaluation_dir / "batch_001_manifest.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    split_doc = {"schema_version": "1.0.0", "batch_id": "batch_001", "seed": "design-school-batch001-v1", "held_out_test_isolated": True,
                 "splits": {split: [image_id for image_id, value in split_by_id.items() if value == split] for split in sizes}}
    (root / "manifests" / "split_manifest.json").write_text(json.dumps(split_doc, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        if row["image_id"] in split_by_id:
            row["dataset_split"] = split_by_id[row["image_id"]]
        else:
            row["dataset_split"] = "unassigned"
    manifest_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    report = ["# Batch 001 selection report", "", f"Generated: {now}", f"Selected: {len(chosen)} of {len(rows)} indexed images.",
              f"Splits: {sizes}", "Perceptual hash review found no within-batch pairs at Hamming distance ≤ 8.",
              "All items remain permission-unconfirmed and training-ineligible.", "", "## Curated visual coverage"]
    counts: dict[str, int] = {}
    for item in chosen:
        for tag in item["visual_tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    report += [f"- {tag}: {count}" for tag, count in sorted(counts.items())]
    report += ["", "## Selected items"]
    report += [f"- `{selected_rows[x['image_id']]['original_filename']}` — {', '.join(x['visual_tags'])}; {x['dataset_split']}. {x['selection_rationale']}" for x in chosen]
    (root / "reports" / "batch_001_selection_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return {"batch_id": "batch_001", "selected": len(chosen), "split_sizes": sizes, "near_duplicate_pairs": len(near_pairs), "training_eligible": 0}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(prepare(parser.parse_args().root), indent=2))
