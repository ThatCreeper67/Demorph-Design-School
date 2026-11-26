"""Read-only image inventory for Design School source files."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

SUPPORTED = {".jpg", ".jpeg", ".png"}
PROVENANCE = {"owned_original", "licensed_or_permitted", "reference_only", "unknown"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["image_id"]] = row
    return rows


def read_source_register(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return {row["image_id"]: row for row in csv.DictReader(stream)}


def ingest(root: Path) -> dict[str, Any]:
    root = root.resolve()
    source_dir = root / "designs" / "original"
    manifest_dir = root / "manifests"
    report_dir = root / "reports"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "image_manifest.jsonl"
    register_path = manifest_dir / "source_register.csv"
    prior_manifest = read_jsonl(manifest_path)
    prior_register = read_source_register(register_path)
    files = sorted((p for p in source_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED), key=lambda p: p.name.casefold())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, register, errors = [], [], []

    for path in files:
        try:
            digest = sha256_file(path)
            image_id = "img_" + digest[:20]
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
                image_format = (image.format or path.suffix.lstrip(".")).upper()
            if width <= 0 or height <= 0:
                raise ValueError("Image dimensions must be positive")
            old = prior_manifest.get(image_id, {})
            old_reg = prior_register.get(image_id, {})
            rel = path.relative_to(root).as_posix()
            row = {
                "schema_version": "1.0.0",
                "image_id": image_id,
                "original_filename": path.name,
                "relative_path": rel,
                "sha256": digest,
                "file_size_bytes": path.stat().st_size,
                "width": width,
                "height": height,
                "aspect_ratio": round(width / height, 8),
                "format": image_format,
                "imported_at": old.get("imported_at", now),
                "provenance_classification": old_reg.get("provenance_classification", "unknown"),
                "permission_status": old_reg.get("permission_status", "unconfirmed"),
                "training_eligible": False,
                "annotation_status": old.get("annotation_status", "not_started"),
                "dataset_split": old.get("dataset_split", "unassigned"),
                "duplicate_of": None,
            }
            rows.append(row)
            register.append({
                "image_id": image_id,
                "original_filename": path.name,
                "relative_path": rel,
                "provenance_classification": row["provenance_classification"] if row["provenance_classification"] in PROVENANCE else "unknown",
                "permission_status": row["permission_status"] if row["permission_status"] in {"confirmed", "denied", "unconfirmed"} else "unconfirmed",
                "owner_confirmation": old_reg.get("owner_confirmation", "unconfirmed"),
                "permission_confirmation": old_reg.get("permission_confirmation", "unconfirmed"),
                "reviewer": old_reg.get("reviewer", ""),
                "reviewed_at": old_reg.get("reviewed_at", ""),
                "notes": old_reg.get("notes", ""),
            })
        except (OSError, ValueError, UnidentifiedImageError) as exc:
            errors.append({"filename": path.name, "error": f"{type(exc).__name__}: {exc}"})

    by_hash: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_hash.setdefault(row["sha256"], []).append(row)
    for group in by_hash.values():
        if len(group) > 1:
            canonical = min(group, key=lambda x: x["relative_path"])
            for row in group:
                if row is not canonical:
                    row["duplicate_of"] = canonical["image_id"]

    manifest_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    fields = ["image_id", "original_filename", "relative_path", "provenance_classification", "permission_status", "owner_confirmation", "permission_confirmation", "reviewer", "reviewed_at", "notes"]
    with register_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(register)

    summary = {
        "generated_at": now,
        "source_directory": str(source_dir),
        "supported_files_found": len(files),
        "images_indexed": len(rows),
        "errors": errors,
        "exact_duplicate_groups": [
            {"sha256": group[0]["sha256"], "image_ids": [r["image_id"] for r in group], "filenames": [r["original_filename"] for r in group]}
            for group in by_hash.values() if len(group) > 1
        ],
        "provenance_counts": {key: sum(r["provenance_classification"] == key for r in rows) for key in sorted(PROVENANCE)},
        "permission_counts": {key: sum(r["permission_status"] == key for r in register) for key in ("confirmed", "denied", "unconfirmed")},
        "training_eligible_count": sum(bool(r["training_eligible"]) for r in rows),
        "originals_modified": False,
    }
    report = [
        "# Image ingestion report — Stage 2", "", f"Generated: {now}",
        f"Source: `{source_dir}`", f"Supported files found: {len(files)}",
        f"Successfully indexed: {len(rows)}", f"Unreadable/invalid files: {len(errors)}",
        f"Exact duplicate groups: {len(summary['exact_duplicate_groups'])}",
        f"Permission confirmed: {summary['permission_counts']['confirmed']}",
        f"Permission unconfirmed: {summary['permission_counts']['unconfirmed']}",
        f"Training eligible: {summary['training_eligible_count']}",
        "", "Original images were opened read-only; this script does not copy, rename, recompress, or modify them.",
        "All new images default to provenance `unknown`, permission `unconfirmed`, and training ineligible.",
    ]
    if errors:
        report += ["", "## Errors", *[f"- `{e['filename']}`: {e['error']}" for e in errors]]
    if summary["exact_duplicate_groups"]:
        report += ["", "## Exact duplicates", *[f"- SHA-256 `{g['sha256']}`: {', '.join(g['filenames'])}" for g in summary["exact_duplicate_groups"]]]
    (report_dir / "ingestion_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (report_dir / "ingestion_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(ingest(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
