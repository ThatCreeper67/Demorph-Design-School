"""Dynamic v1.1 worksheet planning, validation, and reviewed module promotion."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_catalog(root: Path) -> dict[str, Any]:
    return json.loads((root / "annotations/modules/analytical_module_catalog_v1.0.json").read_text(encoding="utf-8"))


def plan_modules(catalog: dict[str, Any], evidence: list[dict[str, Any]], cues: list[dict[str, Any]], *, max_sections: int | None = None) -> dict[str, Any]:
    """Select relevant existing modules from explicit poster cues; retain omissions and reasons."""
    signals = {cue["signal"] for cue in cues}
    evidence_ids = {item["evidence_id"] for item in evidence}
    for cue in cues:
        if not set(cue.get("evidence_refs", [])) <= evidence_ids:
            raise ValueError(f"cue {cue.get('signal')} references missing evidence")
    limit = catalog["policy"]["default_max_per_poster"] if max_sections is None else max_sections
    if not isinstance(limit, int) or not 0 <= limit <= 8:
        raise ValueError("max_sections must be between 0 and 8")
    candidates = []
    decisions = []
    for module in catalog["modules"]:
        triggered = signals.intersection(module["trigger_signals"])
        suppressed = signals.intersection(module["suppress_signals"])
        score = sum(next(c["confidence"] for c in cues if c["signal"] == s) for s in triggered)
        select = bool(triggered) and not suppressed
        reason = ("Triggered by " + ", ".join(sorted(triggered))) if select else (
            "Suppressed by " + ", ".join(sorted(suppressed)) if suppressed else "No matching poster-specific cue")
        candidates.append((module, select, reason, score))
    selected = [c for c in candidates if c[1]]
    selected.sort(key=lambda c: (-c[3], c[0]["module_id"]))
    keep = {c[0]["module_id"] for c in selected[:limit]}
    for module, select, reason, score in candidates:
        if select and module["module_id"] not in keep:
            reason += "; omitted because the specialist-section limit was reached"
        related_evidence = sorted({eid for cue in cues if cue["signal"] in signals.intersection(module["trigger_signals"] + module["suppress_signals"]) for eid in cue["evidence_refs"]})
        decisions.append({"module_ref": module["module_id"], "heading": module["heading"], "decision": "selected" if module["module_id"] in keep else "omitted", "rationale": reason, "evidence_refs": related_evidence, "relevance_score": score})
    return {"module_catalog_version": catalog["catalogue_version"], "planner_version": "1.0.0", "profile_source": "human_interpretation", "evidence": evidence, "cues": cues, "max_specialist_sections": limit, "module_decisions": decisions, "custom_proposals": []}


def make_annotation(image: dict[str, str], *, catalog: dict[str, Any], evidence: list[dict[str, Any]] | None = None, cues: list[dict[str, Any]] | None = None, max_sections: int | None = None, custom_proposals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    evidence, cues = evidence or [], cues or []
    plan = plan_modules(catalog, evidence, cues, max_sections=max_sections)
    plan["custom_proposals"] = custom_proposals or []
    sections = []
    selected = {d["module_ref"]: d for d in plan["module_decisions"] if d["decision"] == "selected"}
    for module in catalog["modules"]:
        decision = selected.get(module["module_id"])
        if not decision:
            continue
        sections.append({"section_id": "section_" + module["module_id"], "module_ref": module["module_id"], "proposal_ref": None, "heading": module["heading"], "scope": "catalogued_module", "selection_rationale": decision["rationale"], "evidence_refs": decision["evidence_refs"], "component_refs": [], "group_refs": [], "subsections": [{"subsection_id": module["module_id"] + "_analysis", "heading": module["heading"], "focus_questions": module["focus_questions"], "claims": []}]})
    for proposal in plan["custom_proposals"]:
        if proposal["selection_decision"] == "selected":
            sections.append({"section_id": "section_" + proposal["proposal_id"], "module_ref": None, "proposal_ref": proposal["proposal_id"], "heading": proposal["heading"], "scope": "poster_specific", "selection_rationale": proposal["rationale"], "evidence_refs": proposal["evidence_refs"], "component_refs": [], "group_refs": [], "subsections": [{"subsection_id": proposal["proposal_id"] + "_analysis", "heading": proposal["heading"], "focus_questions": proposal["focus_questions"], "claims": []}]})
    annotation = {"schema_version": "1.1.0", "annotation_id": "annotation_" + image["image_id"], "image": image, "brief_context": None,
        "foundation": {"observe": {"visible_elements_locations": [], "text_transcribed_with_confidence": [], "uncertain_observations": []}, "identify": {"components": [], "component_groups": [], "relationships": []}, "hierarchy_composition": {"intended_hierarchy": [], "apparent_hierarchy": [], "attention_flow": [], "spatial_relationships": []}, "judge": {"component_assessments": [], "overall_strengths": [], "overall_weaknesses": [], "impact_readability": [], "impact_hierarchy": [], "impact_communication": [], "uncertainty_or_alternatives": []}, "improve": []},
        "analysis_plan": plan, "specialist_sections": sections, "source_prediction_ids": [], "human_review": {"reviewer_id_or_role": None, "status": "draft", "reviewed_version": None, "reviewed_sections": [], "reviewed_at": None, "disagreement_status": "not_reviewed", "correction_history": []}, "legacy_source_annotation": None}
    return annotation


def validate_annotation(data: dict[str, Any], catalog: dict[str, Any]) -> None:
    """Check versioned envelope plus all cross references used by the dynamic workflow."""
    if data.get("schema_version") == "1.0.0":
        required_v1 = {"image", "brief_context", "elements", "roles", "hierarchy", "principles", "evaluation", "critique", "human_review"}
        if not required_v1 <= data.keys() or data["schema_version"] != "1.0.0":
            raise ValueError("Invalid v1.0 annotation envelope")
        for element in data["elements"]:
            if not element.get("element_id"):
                raise ValueError("v1.0 element missing stable element_id")
        element_ids = {e["element_id"] for e in data["elements"]}
        for entry in data["roles"] + data["hierarchy"]:
            if entry.get("element_id") not in element_ids:
                raise ValueError("v1.0 role/hierarchy has invalid element reference")
        return
    if data.get("schema_version") != "1.1.0":
        raise ValueError("Unsupported annotation schema_version")
    required = {"annotation_id", "image", "foundation", "analysis_plan", "specialist_sections", "human_review", "legacy_source_annotation", "source_prediction_ids", "brief_context"}
    if not required <= data.keys():
        raise ValueError(f"v1.1 annotation missing keys: {sorted(required-data.keys())}")
    plan = data["analysis_plan"]
    ids = {x["evidence_id"] for x in plan["evidence"]}
    if len(ids) != len(plan["evidence"]):
        raise ValueError("duplicate evidence_id")
    components = {x["component_id"] for x in data["foundation"]["identify"]["components"]}
    groups = {x["group_id"] for x in data["foundation"]["identify"]["component_groups"]}
    relationships = {x["relationship_id"] for x in data["foundation"]["identify"]["relationships"]}
    known_modules = {m["module_id"] for m in catalog["modules"]}
    decisions = {d["module_ref"]: d for d in plan["module_decisions"]}
    if len(decisions) != len(plan["module_decisions"]):
        raise ValueError("duplicate module decision")
    proposals = {p["proposal_id"]: p for p in plan["custom_proposals"]}
    if len(proposals) != len(plan["custom_proposals"]):
        raise ValueError("duplicate custom proposal")
    for p in proposals.values():
        if p["status"] != "proposed":
            raise ValueError("custom module proposals must remain proposed")
        missing = set(p["evidence_refs"]) - ids
        if missing: raise ValueError(f"custom proposal has invalid evidence references: {sorted(missing)}")
    selected_ids = set()
    for section in data["specialist_sections"]:
        refs = [x for x in (section["module_ref"], section["proposal_ref"]) if x is not None]
        if len(refs) != 1: raise ValueError("specialist section must reference exactly one module or proposal")
        ref = refs[0]
        if section["module_ref"] is not None:
            if ref not in known_modules or ref not in decisions or decisions[ref]["decision"] != "selected": raise ValueError(f"section references unselected/unknown module: {ref}")
            if section["scope"] != "catalogued_module": raise ValueError("catalogued module section has incorrect scope")
        else:
            if ref not in proposals or proposals[ref]["selection_decision"] != "selected": raise ValueError(f"section references unselected/unknown proposal: {ref}")
            if section["scope"] != "poster_specific": raise ValueError("custom proposal section has incorrect scope")
        selected_ids.add(ref)
        missing = set(section["evidence_refs"]) - ids
        if missing: raise ValueError(f"section has invalid evidence references: {sorted(missing)}")
        missing = set(section["component_refs"]) - components
        if missing: raise ValueError(f"section has invalid component references: {sorted(missing)}")
        missing = set(section["group_refs"]) - groups
        if missing: raise ValueError(f"section has invalid group references: {sorted(missing)}")
        for subsection in section["subsections"]:
            for claim in subsection["claims"]:
                missing = set(claim["evidence_refs"]) - ids
                if missing: raise ValueError(f"claim has invalid evidence references: {sorted(missing)}")
    for ref, decision in decisions.items():
        if ref is not None and ref not in known_modules: raise ValueError(f"unknown catalogue module: {ref}")
        if set(decision["evidence_refs"]) - ids: raise ValueError(f"module decision has invalid evidence references: {decision['module_ref']}")
        if decision["decision"] == "selected" and ref not in selected_ids: raise ValueError(f"selected module lacks a section: {ref}")
    if len(selected_ids) > plan["max_specialist_sections"]: raise ValueError("specialist section limit exceeded")
    for evidence in plan["evidence"]:
        if evidence.get("source_ref") and evidence["source_ref"] not in components and evidence["source_ref"] not in relationships:
            raise ValueError(f"evidence has invalid source_ref: {evidence['source_ref']}")
    for component in data["foundation"]["identify"]["components"]:
        missing = set(component["spatial_relationship_ids"]) - relationships
        if missing: raise ValueError(f"component has invalid relationship references: {sorted(missing)}")
    # Check component/group/relationship references throughout foundation.
    def walk(value: Any, key: str = ""):
        if isinstance(value, dict):
            for k, v in value.items(): yield from walk(v, k)
        elif isinstance(value, list):
            for v in value: yield from walk(v, key)
        elif isinstance(value, str) and key in {"component_ref", "component_refs", "subject_refs", "object_refs"}:
            yield key, value
    for key, ref in walk(data["foundation"]):
        allowed = components | groups
        if key in {"subject_refs", "object_refs"}: allowed |= relationships
        if ref not in allowed: raise ValueError(f"invalid component/group/relationship reference: {ref}")
    def check_evidence_refs(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_refs":
                    refs = child if isinstance(child, list) else [child]
                    if set(refs) - ids: raise ValueError(f"invalid evidence reference: {sorted(set(refs)-ids)}")
                else: check_evidence_refs(child)
        elif isinstance(value, list):
            for child in value: check_evidence_refs(child)
    check_evidence_refs(data["foundation"])
    if data["human_review"]["status"] == "approved" and not data["human_review"].get("reviewer_id_or_role"):
        raise ValueError("approved annotation requires a reviewer")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create dynamic v1.1 worksheets for the batch 001 development pilot")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    batch = json.loads((root / "evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    images = {row["image_id"]: row for row in (json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    catalog = load_catalog(root)
    known = {signal for module in catalog["modules"] for signal in module["trigger_signals"] + module["suppress_signals"]}
    out = root / "annotations/drafts/batch_001/v1.1"
    out.mkdir(parents=True, exist_ok=True)
    for sample in [s for s in batch["samples"] if s["dataset_split"] == "development"][:5]:
        image = images[sample["image_id"]]
        target = out / f"{image['image_id']}.json"
        if target.exists():
            print(f"Preserved existing draft: {target}")
            continue
        eid = f"manifest_{image['image_id']}"
        evidence = [{"evidence_id": eid, "text": sample.get("selection_rationale", "Curated batch description."), "source": "human_interpretation", "source_ref": None, "confidence": 0.6, "uncertainty": "medium"}]
        cues = [{"signal": tag, "evidence_refs": [eid], "confidence": 0.6} for tag in sample.get("visual_tags", []) if tag in known]
        annotation = make_annotation({k: image[k] for k in ("image_id", "sha256", "relative_path")}, catalog=catalog, evidence=evidence if cues else [], cues=cues)
        validate_annotation(annotation, catalog)
        target.write_text(json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md = [f"# Dynamic human review — {image['image_id']}", "", f"Image: `{image['relative_path']}`", "", "Always review the universal foundation: Observe, Identify, Hierarchy and composition, Judge, Improve. Curator metadata cues below are planning hints only and must be checked against the poster.", ""]
        for section in annotation["specialist_sections"]:
            md += [f"## {section['heading']}", f"Selection rationale: {section['selection_rationale']}", ""] + [f"- {q}" for q in section["subsections"][0]["focus_questions"]] + [""]
        md += ["## Suppressed or omitted sections"] + [f"- {d['heading']}: {d['rationale']}" for d in annotation["analysis_plan"]["module_decisions"] if d["decision"] == "omitted"] + ["", "## Human review", "Status: draft. No claims have been approved."]
        target.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
        print(target)


def promote_module(root: Path, proposal: dict[str, Any], *, review: dict[str, Any]) -> Path:
    """Store a reviewed reusable candidate separately; never edit the approved catalogue."""
    if review.get("status") != "approved" or not review.get("reviewer_id_or_role"):
        raise ValueError("human-approved review with reviewer_id_or_role is required for module promotion")
    if not proposal.get("proposal_id") or not proposal.get("heading") or not proposal.get("focus_questions"):
        raise ValueError("proposal requires an id, heading, and focus questions")
    out = root / "annotations/modules/candidates"
    out.mkdir(parents=True, exist_ok=True)
    target = out / (re.sub(r"[^A-Za-z0-9_.-]", "_", proposal["proposal_id"]) + ".json")
    payload = {"candidate": proposal, "human_review": review, "promotion_status": "approved_candidate_pending_catalogue_maintainer"}
    if target.exists():
        raise FileExistsError(f"candidate already exists: {target}")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
