"""Behavior tests for poster-specific planning and cross-reference enforcement."""
from pathlib import Path
import pytest
from annotations.dynamic_workflow import load_catalog, make_annotation, promote_module, validate_annotation

ROOT = Path(__file__).resolve().parents[1]
CATALOG = load_catalog(ROOT)
EVIDENCE = [{"evidence_id": "ev1", "text": "Curator observed the feature", "source": "human_interpretation", "source_ref": None, "confidence": 0.8, "uncertainty": "medium"}]

def build(cues=(), proposals=()):
    return make_annotation({"image_id": "fixture", "sha256": "a" * 64, "relative_path": "fixture.jpg"}, catalog=CATALOG, evidence=EVIDENCE if cues else [], cues=[{"signal": c, "evidence_refs": ["ev1"], "confidence": .9} for c in cues], custom_proposals=list(proposals))

def test_universal_foundation_only():
    value = build()
    assert set(value["foundation"]) == {"observe", "identify", "hierarchy_composition", "judge", "improve"}
    assert value["specialist_sections"] == []
    validate_annotation(value, CATALOG)

def test_one_specialist_and_multiple_specialists():
    one = build(["typography_led"])
    assert [s["module_ref"] for s in one["specialist_sections"]] == ["typography_letterforms"]
    many = build(["typography_led", "dominant_subject", "strong_colour_contrast"])
    assert {s["module_ref"] for s in many["specialist_sections"]} == {"typography_letterforms", "hero_visual", "colour_relationships"}
    validate_annotation(one, CATALOG); validate_annotation(many, CATALOG)

def test_poster_specific_new_section():
    proposal = {"proposal_id": "custom_1", "heading": "Unique device", "concept": "Poster-specific visual device", "rationale": "This poster uses it", "focus_questions": ["How does it work?"], "evidence_refs": ["ev1"], "status": "proposed", "selection_decision": "selected"}
    value = build(["typography_led"], [proposal])
    assert any(s["scope"] == "poster_specific" for s in value["specialist_sections"])
    validate_annotation(value, CATALOG)

def test_irrelevant_module_suppressed():
    value = build(["no_legible_or_visible_type"])
    decision = next(d for d in value["analysis_plan"]["module_decisions"] if d["module_ref"] == "typography_letterforms")
    assert decision["decision"] == "omitted" and "Suppressed" in decision["rationale"]

def test_bad_component_and_evidence_references_rejected():
    value = build(["typography_led"])
    value["foundation"]["judge"]["component_assessments"].append({"component_ref": "missing", "strengths": [], "weaknesses": [], "impact": []})
    with pytest.raises(ValueError, match="component/group/relationship"): validate_annotation(value, CATALOG)
    value = build(["typography_led"]); value["specialist_sections"][0]["evidence_refs"] = ["missing"]
    with pytest.raises(ValueError, match="evidence"): validate_annotation(value, CATALOG)

def test_unapproved_promotion_rejected_and_approved_candidate_is_separate(monkeypatch):
    proposal = {"proposal_id": "p1", "heading": "Candidate", "focus_questions": ["Q?"]}
    with pytest.raises(ValueError, match="human-approved"):
        promote_module(ROOT, proposal, review={"status": "draft"})
    writes = []
    monkeypatch.setattr(Path, "mkdir", lambda self, **kwargs: None)
    monkeypatch.setattr(Path, "write_text", lambda self, value, **kwargs: writes.append((self, value)))
    path = promote_module(ROOT, proposal, review={"status": "approved", "reviewer_id_or_role": "design reviewer"})
    assert path.parent == ROOT / "annotations/modules/candidates"
    assert __import__("json").loads(writes[0][1])["promotion_status"] == "approved_candidate_pending_catalogue_maintainer"

def test_v1_backward_compatibility_and_bad_reference():
    value = {"schema_version": "1.0.0", "image": {}, "brief_context": None, "elements": [], "roles": [], "hierarchy": [], "principles": [], "evaluation": [], "critique": {}, "human_review": {}}
    validate_annotation(value, CATALOG)
    value["elements"] = [{"element_id": "e1"}]; value["roles"] = [{"element_id": "bad"}]
    with pytest.raises(ValueError, match="invalid element"): validate_annotation(value, CATALOG)

def test_existing_pilot_data_and_review_packets_exist_unchanged():
    drafts = sorted((ROOT / "annotations/drafts/batch_001").glob("*.json"))
    packets = sorted((ROOT / "annotations/drafts/batch_001/prediction_review").glob("*.md"))
    assert len(drafts) == 5 and len(packets) == 5
    assert all(__import__("json").loads(p.read_text(encoding="utf-8"))["schema_version"] == "1.0.0" for p in drafts)
