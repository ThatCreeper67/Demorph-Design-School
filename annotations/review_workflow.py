"""Persistent human review workflow for Design School annotations."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEWED_DIR = "annotations/reviewed"
MODULES_DIR = "annotations/modules"
CANDIDATES_DIR = "annotations/modules/candidates"


def ensure_directories(root: Path) -> tuple[Path, Path]:
    """Ensure reviewed and candidates directories exist."""
    reviewed_dir = root / REVIEWED_DIR
    candidates_dir = root / CANDIDATES_DIR
    reviewed_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir.mkdir(parents=True, exist_ok=True)
    return reviewed_dir, candidates_dir


def save_reviewed_annotation(root: Path, annotation: dict[str, Any], reviewer_id_or_role: str) -> Path:
    """Save a reviewed annotation to the reviewed directory."""
    reviewed_dir, _ = ensure_directories(root)

    image_id = annotation["image"]["image_id"]
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Update review metadata
    annotation["human_review"]["reviewer_id_or_role"] = reviewer_id_or_role
    annotation["human_review"]["reviewed_at"] = timestamp
    annotation["human_review"]["status"] = "approved"
    annotation["human_review"]["reviewed_version"] = annotation.get("schema_version", "1.1.0")
    annotation["human_review"]["reviewed_sections"] = ["foundation"] + [
        s["section_id"] for s in annotation.get("specialist_sections", [])
    ]

    target = reviewed_dir / f"{image_id}.json"
    if target.exists():
        raise FileExistsError(f"Reviewed annotation already exists: {target}. Use update_reviewed_annotation for changes.")

    target.write_text(json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def update_reviewed_annotation(root: Path, image_id: str, reviewer_id_or_role: str,
                                updates: dict[str, Any]) -> Path:
    """Update an existing reviewed annotation with new values, recording corrections."""
    reviewed_dir, _ = ensure_directories(root)
    target = reviewed_dir / f"{image_id}.json"

    if not target.exists():
        raise FileNotFoundError(f"No reviewed annotation found for {image_id}")

    annotation = json.loads(target.read_text(encoding="utf-8"))

    # Verify reviewer matches (or allow new reviewer with note)
    existing_reviewer = annotation["human_review"]["reviewer_id_or_role"]
    if existing_reviewer != reviewer_id_or_role:
        # Allow but record the change
        updates["human_review.reviewer_id_or_role"] = reviewer_id_or_role

    # Record corrections
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for field_path, new_value in updates.items():
        # Navigate to the field
        keys = field_path.split(".")
        obj = annotation
        for key in keys[:-1]:
            obj = obj[key]
        old_value = obj[keys[-1]]
        if old_value != new_value:
            annotation["human_review"]["correction_history"].append({
                "timestamp": timestamp,
                "field": field_path,
                "old_value": old_value,
                "new_value": new_value,
                "reason": f"Updated by {reviewer_id_or_role}"
            })
            obj[keys[-1]] = new_value

    # Update review metadata
    annotation["human_review"]["reviewed_at"] = timestamp
    annotation["human_review"]["status"] = "approved"

    target.write_text(json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def load_reviewed_annotation(root: Path, image_id: str) -> dict[str, Any] | None:
    """Load a reviewed annotation if it exists and is approved."""
    reviewed_dir, _ = ensure_directories(root)
    target = reviewed_dir / f"{image_id}.json"
    if not target.exists():
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    if data.get("human_review", {}).get("status") == "approved":
        return data
    return None


def list_reviewed_annotations(root: Path) -> list[Path]:
    """List all reviewed annotation files."""
    reviewed_dir, _ = ensure_directories(root)
    return sorted(reviewed_dir.glob("*.json"))


def promote_module(root: Path, proposal: dict[str, Any], *, review: dict[str, Any]) -> Path:
    """Store a reviewed reusable candidate separately; never edit the approved catalogue.

    This is a wrapper around the dynamic_workflow.promote_module that ensures
    directories exist and handles the review workflow integration.
    """
    # Validate review
    if review.get("status") != "approved" or not review.get("reviewer_id_or_role"):
        raise ValueError("human-approved review with reviewer_id_or_role is required for module promotion")

    # Validate proposal
    if not proposal.get("proposal_id") or not proposal.get("heading") or not proposal.get("focus_questions"):
        raise ValueError("proposal requires an id, heading, and focus questions")

    _, candidates_dir = ensure_directories(root)
    target = candidates_dir / (re.sub(r"[^A-Za-z0-9_.-]", "_", proposal["proposal_id"]) + ".json")

    # Enrich with review metadata
    payload = {
        "candidate": proposal,
        "human_review": {
            "reviewer_id_or_role": review["reviewer_id_or_role"],
            "status": "approved",
            "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reviewed_version": "1.1.0",
            "reviewed_sections": ["candidate"],
            "disagreement_status": "none",
            "correction_history": []
        },
        "promotion_status": "approved_candidate_pending_catalogue_maintainer",
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
    }

    if target.exists():
        raise FileExistsError(f"candidate already exists: {target}")

    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def list_candidate_modules(root: Path) -> list[Path]:
    """List all candidate module files."""
    _, candidates_dir = ensure_directories(root)
    return sorted(candidates_dir.glob("*.json"))


def load_candidate_module(root: Path, candidate_id: str) -> dict[str, Any] | None:
    """Load a candidate module if it exists."""
    _, candidates_dir = ensure_directories(root)
    # Try exact match first
    for path in candidates_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("candidate", {}).get("proposal_id") == candidate_id:
            return data
    return None


def approve_candidate_for_catalogue(root: Path, candidate_id: str, maintainer_id: str) -> Path:
    """Mark a candidate as approved by catalogue maintainer (final promotion step)."""
    _, candidates_dir = ensure_directories(root)
    for path in candidates_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("candidate", {}).get("proposal_id") == candidate_id:
            if data.get("promotion_status") != "approved_candidate_pending_catalogue_maintainer":
                raise ValueError(f"Candidate not in pending state: {data.get('promotion_status')}")
            data["promotion_status"] = "catalogue_maintainer_approved"
            data["catalogue_maintainer"] = maintainer_id
            data["catalogue_approved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return path
    raise FileNotFoundError(f"Candidate not found: {candidate_id}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Review workflow CLI")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    subparsers = parser.add_subparsers(dest="command")

    # save-reviewed
    p_save = subparsers.add_parser("save-reviewed", help="Save a reviewed annotation")
    p_save.add_argument("--image-id", required=True)
    p_save.add_argument("--reviewer", required=True)
    p_save.add_argument("--annotation-file", type=Path, required=True, help="Path to v1.1 annotation JSON to save as reviewed")

    # promote-module
    p_promo = subparsers.add_parser("promote-module", help="Promote a custom proposal to candidate module")
    p_promo.add_argument("--proposal-file", type=Path, required=True, help="JSON file with proposal")
    p_promo.add_argument("--reviewer", required=True)

    # list-reviewed
    subparsers.add_parser("list-reviewed", help="List reviewed annotations")

    # list-candidates
    subparsers.add_parser("list-candidates", help="List candidate modules")

    args = parser.parse_args()
    root = args.root.resolve()

    if args.command == "save-reviewed":
        annotation = json.loads(args.annotation_file.read_text(encoding="utf-8"))
        path = save_reviewed_annotation(root, annotation, args.reviewer)
        print(f"Saved reviewed annotation: {path}")
    elif args.command == "promote-module":
        proposal = json.loads(args.proposal_file.read_text(encoding="utf-8"))
        path = promote_module(root, proposal, review={"status": "approved", "reviewer_id_or_role": args.reviewer})
        print(f"Promoted candidate module: {path}")
    elif args.command == "list-reviewed":
        for path in list_reviewed_annotations(root):
            print(path)
    elif args.command == "list-candidates":
        for path in list_candidate_modules(root):
            print(path)
    else:
        parser.print_help()