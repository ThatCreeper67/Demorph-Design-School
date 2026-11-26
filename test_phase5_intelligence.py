"""Regression checks for Phase 5 evidence chains and output safety."""
from annotations.phase5_intelligence import make_annotation, validate_reasoning

IMAGE = {"image_id":"fixture", "sha256":"a"*64, "relative_path":"designs/original/fixture.jpg"}
RAW = {
    "evidence":[{"evidence_id":"ev1","description":"Large yellow headline against blue field","location":"upper left","confidence":0.9}],
    "observations":[{"observation_id":"obs1","text":"The headline is a prominent text element","role":"headline","evidence_refs":["ev1"],"confidence":0.8}],
    "relationships":[], "hierarchy":{"apparent_order":[],"reading_flow":[],"intended_priority":"unknown without brief"},
    "evaluations":[],"recommendations":[],"specialists":[],"uncertainties":["Intended message cannot be confirmed"]
}

def test_v1_2_envelope_preserves_provenance_and_review_state():
    value=make_annotation(IMAGE,RAW,curriculum_refs=["visual-hierarchy-v1"],model="qwen3.5:9b-q4_K_M",elapsed_ms=1234)
    assert value["schema_version"]=="1.2.0"
    assert value["observations"][0]["evidence_refs"]==["ev1"]
    assert value["analysis_metadata"]["human_review"]=="unreviewed"

def test_relationship_must_connect_existing_observations_and_evidence():
    value={**RAW,"relationships":[{"relationship_id":"rel1","subject_refs":["obs1"],"object_refs":["missing"],"observation_refs":["obs1"],"evidence_refs":["ev1"],"effect":"competition","confidence":0.7}]}
    from annotations.phase5_intelligence import VERSION
    envelope={"schema_version":VERSION,"evidence":value["evidence"],"observations":value["observations"],"relationships":value["relationships"],"evaluations":[],"recommendations":[],"specialists":[],"curriculum_refs":[]}
    try:
        validate_reasoning(envelope)
    except ValueError as exc:
        assert "endpoint" in str(exc)
    else:
        raise AssertionError("invalid relationship endpoint was accepted")

def test_empty_or_untraceable_analysis_is_rejected():
    envelope={"schema_version":"1.2.0","evidence":[],"observations":[],"relationships":[],"evaluations":[],"recommendations":[],"specialists":[],"curriculum_refs":[]}
    try:
        validate_reasoning(envelope)
    except ValueError as exc:
        assert "needs image evidence" in str(exc)
    else:
        raise AssertionError("empty reasoning was accepted")

def test_missing_brief_drops_unsupported_brand_audience_claims_and_unknown_curriculum():
    import copy
    raw=copy.deepcopy(RAW)
    raw["relationships"]=[{"relationship_id":"rel1","subject_refs":["obs1"],"relation":"colour echo","object_refs":["obs1"],"effect":"brand palette","interpretation":"brand identity cue","principle":None,"curriculum_refs":[None,"made-up"],"observation_refs":["obs1"],"evidence_refs":["ev1"],"confidence":0.6}]
    raw["evaluations"]=[{"evaluation_id":"eval1","dimension":"communication","judgment":"mixed","finding":"clarity for non-Japanese audience","impact":"reduced clarity","observation_refs":["obs1"],"relationship_refs":["rel1"],"evidence_refs":["ev1"],"curriculum_refs":[],"confidence":0.5,"uncertainty":"medium"}]
    raw["recommendations"]=[{"recommendation_id":"rec1","priority":"optional","change":"add translation for global audience","reason":"audience access","expected_impact":"clarity","evaluation_refs":["eval1"],"evidence_refs":["ev1"],"confidence":0.5}]
    value=make_annotation(IMAGE,raw,curriculum_refs=["visual-hierarchy-v1"],model="qwen3.5:9b-q4_K_M",elapsed_ms=10)
    assert raw["relationships"][0]["curriculum_refs"]==[None,"made-up"]
    assert value["relationships"]==[] and value["evaluations"]==[] and value["recommendations"]==[]
    assert any("brand" in x for x in value["uncertainties"])
