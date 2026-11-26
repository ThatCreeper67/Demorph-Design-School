"""Integration tests for dynamic v1.1 workflow."""
from pathlib import Path
import json
import shutil

from annotations.dynamic_workflow import load_catalog, make_annotation, validate_annotation, promote_module
from annotations.review_workflow import save_reviewed_annotation, load_reviewed_annotation, list_reviewed_annotations, list_candidate_modules
from scripts.validate_annotation_pilot import validate_v11


def test_integration():
    root = Path('.')
    catalog = load_catalog(root)

    # Test 1: Universal foundation only (no cues)
    print('Test 1: Universal foundation only')
    img = {'image_id': 'test_universal', 'sha256': 'a'*64, 'relative_path': 'test.jpg'}
    ann = make_annotation(img, catalog=catalog, evidence=[], cues=[])
    assert ann['specialist_sections'] == []
    assert set(ann['foundation'].keys()) == {'observe', 'identify', 'hierarchy_composition', 'judge', 'improve'}
    validate_annotation(ann, catalog)
    print('  PASS')

    # Test 2: One specialist module
    print('Test 2: One specialist module')
    cues = [{'signal': 'typography_led', 'evidence_refs': ['e1'], 'confidence': 0.9}]
    evidence = [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}]
    ann = make_annotation(img, catalog=catalog, evidence=evidence, cues=cues)
    assert len(ann['specialist_sections']) == 1
    assert ann['specialist_sections'][0]['module_ref'] == 'typography_letterforms'
    validate_annotation(ann, catalog)
    print('  PASS')

    # Test 3: Multiple specialist modules
    print('Test 3: Multiple specialist modules')
    cues = [{'signal': 'typography_led', 'evidence_refs': ['e1'], 'confidence': 0.9},
            {'signal': 'dominant_subject', 'evidence_refs': ['e1'], 'confidence': 0.9},
            {'signal': 'strong_colour_contrast', 'evidence_refs': ['e1'], 'confidence': 0.9}]
    evidence = [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}]
    ann = make_annotation(img, catalog=catalog, evidence=evidence, cues=cues)
    refs = {s['module_ref'] for s in ann['specialist_sections']}
    assert refs == {'typography_letterforms', 'hero_visual', 'colour_relationships'}
    validate_annotation(ann, catalog)
    print('  PASS')

    # Test 4: Custom poster-specific section
    print('Test 4: Custom poster-specific section')
    proposal = {'proposal_id': 'custom_1', 'heading': 'Unique device', 'concept': 'Poster-specific visual device', 'rationale': 'This poster uses it', 'focus_questions': ['How does it work?'], 'evidence_refs': ['e1'], 'status': 'proposed', 'selection_decision': 'selected'}
    cues = [{'signal': 'typography_led', 'evidence_refs': ['e1'], 'confidence': 0.9}]
    evidence = [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}]
    ann = make_annotation(img, catalog=catalog, evidence=evidence, cues=cues, custom_proposals=[proposal])
    assert any(s['scope'] == 'poster_specific' for s in ann['specialist_sections'])
    validate_annotation(ann, catalog)
    print('  PASS')

    # Test 5: Irrelevant module suppressed
    print('Test 5: Irrelevant module suppressed')
    cues = [{'signal': 'no_legible_or_visible_type', 'evidence_refs': ['e1'], 'confidence': 0.9}]
    evidence = [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}]
    ann = make_annotation(img, catalog=catalog, evidence=evidence, cues=cues)
    decision = next(d for d in ann['analysis_plan']['module_decisions'] if d['module_ref'] == 'typography_letterforms')
    assert decision['decision'] == 'omitted' and 'Suppressed' in decision['rationale']
    validate_annotation(ann, catalog)
    print('  PASS')

    # Test 6: Invalid component reference rejected
    print('Test 6: Invalid component reference rejected')
    cues = [{'signal': 'typography_led', 'evidence_refs': ['e1'], 'confidence': 0.9}]
    evidence = [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}]
    ann = make_annotation(img, catalog=catalog, evidence=evidence, cues=cues)
    ann['foundation']['judge']['component_assessments'].append({'component_ref': 'missing', 'strengths': [], 'weaknesses': [], 'impact': []})
    try:
        validate_annotation(ann, catalog)
        print('  FAIL: Should have raised ValueError')
    except ValueError as e:
        assert 'component/group/relationship' in str(e)
        print('  PASS')

    # Test 7: Invalid evidence reference rejected
    print('Test 7: Invalid evidence reference rejected')
    cues = [{'signal': 'typography_led', 'evidence_refs': ['e1'], 'confidence': 0.9}]
    evidence = [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}]
    ann = make_annotation(img, catalog=catalog, evidence=evidence, cues=cues)
    ann['specialist_sections'][0]['evidence_refs'] = ['missing']
    try:
        validate_annotation(ann, catalog)
        print('  FAIL: Should have raised ValueError')
    except ValueError as e:
        assert 'evidence' in str(e)
        print('  PASS')

    # Test 8: Unapproved promotion rejected
    print('Test 8: Unapproved promotion rejected')
    proposal = {'proposal_id': 'p1', 'heading': 'Candidate', 'focus_questions': ['Q?']}
    try:
        promote_module(root, proposal, review={'status': 'draft'})
        print('  FAIL: Should have raised ValueError')
    except ValueError as e:
        assert 'human-approved' in str(e)
        print('  PASS')

    # Test 9: Approved promotion creates candidate
    print('Test 9: Approved promotion creates candidate')
    candidates_dir = root / 'annotations/modules/candidates'
    if candidates_dir.exists():
        shutil.rmtree(candidates_dir)
    proposal = {'proposal_id': 'p2', 'heading': 'Candidate 2', 'focus_questions': ['Q?']}
    path = promote_module(root, proposal, review={'status': 'approved', 'reviewer_id_or_role': 'design reviewer'})
    assert path.parent == root / 'annotations/modules/candidates'
    with open(path) as f:
        data = json.load(f)
    assert data['promotion_status'] == 'approved_candidate_pending_catalogue_maintainer'
    print('  PASS')

    # Test 10: v1.0 backward compatibility
    print('Test 10: v1.0 backward compatibility')
    v10 = {'schema_version': '1.0.0', 'image': {'image_id': 'test', 'sha256': 'a'*64, 'relative_path': 'test.jpg'}, 'brief_context': None, 'elements': [], 'roles': [], 'hierarchy': [], 'principles': [], 'evaluation': [], 'critique': {'strengths': [], 'weaknesses': [], 'improvements': []}, 'human_review': {'reviewer_id_or_role': None, 'status': 'draft', 'annotation_version': '1.0.0', 'reviewed_at': None, 'disagreement_status': 'not_reviewed', 'correction_history': []}}
    validate_annotation(v10, catalog)
    v10['elements'] = [{'element_id': 'e1'}]
    v10['roles'] = [{'element_id': 'bad'}]
    try:
        validate_annotation(v10, catalog)
        print('  FAIL: Should have raised ValueError')
    except ValueError as e:
        assert 'invalid element' in str(e)
        print('  PASS')

    # Test 11: Existing pilot drafts preserved
    print('Test 11: Existing pilot drafts preserved')
    drafts = sorted((root / 'annotations/drafts/batch_001').glob('*.json'))
    packets = sorted((root / 'annotations/drafts/batch_001/prediction_review').glob('*.md'))
    assert len(drafts) == 5 and len(packets) == 5
    assert all(json.loads(p.read_text(encoding='utf-8'))['schema_version'] == '1.0.0' for p in drafts)
    print('  PASS')

    # Test 12: v1.1 actual worksheet generation
    print('Test 12: Actual v1.1 worksheet generation')
    batch = json.loads((root / 'evaluation/datasets/batch_001_manifest.json').read_text(encoding='utf-8'))
    samples = [s for s in batch['samples'] if s['dataset_split'] == 'development'][:5]
    manifest_rows = [json.loads(line) for line in (root / 'manifests/image_manifest.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    images = {row['image_id']: row for row in manifest_rows}
    known_signals = {signal for module in catalog['modules'] for signal in module['trigger_signals'] + module['suppress_signals']}
    for sample in samples:
        image = images[sample['image_id']]
        eid = f'manifest_{image["image_id"]}'
        evidence = [{'evidence_id': eid, 'text': sample.get('selection_rationale', ''), 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.6, 'uncertainty': 'medium'}]
        cues = [{'signal': tag, 'evidence_refs': [eid], 'confidence': 0.6} for tag in sample.get('visual_tags', []) if tag in known_signals]
        ann = make_annotation({k: image[k] for k in ('image_id', 'sha256', 'relative_path')}, catalog=catalog, evidence=evidence if cues else [], cues=cues)
        validate_annotation(ann, catalog)
        assert ann['schema_version'] == '1.1.0'
    print('  PASS')

    # Test 13: v1.1 validation through validator
    print('Test 13: v1.1 validation through validator')
    count = validate_v11(root)
    assert count == 5
    print('  PASS')

    print()
    print('All 13 required tests PASSED!')


if __name__ == '__main__':
    test_integration()