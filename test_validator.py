"""Validator quality tests."""
from pathlib import Path
import json
from annotations.dynamic_workflow import load_catalog, validate_annotation

root = Path('.')
catalog = load_catalog(root)
img = {'image_id': 'test', 'sha256': 'a'*64, 'relative_path': 'test.jpg'}

print('=== VALIDATOR QUALITY TESTS ===')
print()

# 1. Missing required fields (v1.1 envelope)
print('1. Missing annotation_id:')
ann = {
    'schema_version': '1.1.0',
    'image': img,
    'foundation': {'observe': {}, 'identify': {}, 'hierarchy_composition': {}, 'judge': {}, 'improve': []},
    'analysis_plan': {'module_catalog_version': '1.0.0', 'planner_version': '1.0.0', 'profile_source': 'human_interpretation', 'evidence': [], 'cues': [], 'max_specialist_sections': 3, 'module_decisions': [], 'custom_proposals': []},
    'specialist_sections': [],
    'source_prediction_ids': [],
    'human_review': {'reviewer_id_or_role': None, 'status': 'draft', 'reviewed_version': None, 'reviewed_sections': [], 'reviewed_at': None, 'disagreement_status': 'not_reviewed', 'correction_history': []},
    'legacy_source_annotation': None
}
try:
    validate_annotation(ann, catalog)
    print('   FAIL: should reject')
except ValueError as e:
    print(f'   PASS: {e}')

# 2. Invalid component reference
print('2. Invalid component reference:')
ann = {
    'schema_version': '1.1.0',
    'annotation_id': 'test',
    'image': img,
    'foundation': {
        'observe': {'visible_elements_locations': [{'text': 'test', 'source': 'direct_observation', 'evidence_refs': ['e1'], 'confidence': 0.9, 'uncertainty': 'low'}], 'text_transcribed_with_confidence': [], 'uncertain_observations': []},
        'identify': {'components': [], 'component_groups': [], 'relationships': []},
        'hierarchy_composition': {'intended_hierarchy': [], 'apparent_hierarchy': [], 'attention_flow': [], 'spatial_relationships': []},
        'judge': {'component_assessments': [{'component_ref': 'missing', 'strengths': [], 'weaknesses': [], 'impact': []}], 'overall_strengths': [], 'overall_weaknesses': [], 'impact_readability': [], 'impact_hierarchy': [], 'impact_communication': [], 'uncertainty_or_alternatives': []},
        'improve': []
    },
    'analysis_plan': {'module_catalog_version': '1.0.0', 'planner_version': '1.0.0', 'profile_source': 'human_interpretation', 'evidence': [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}], 'cues': [], 'max_specialist_sections': 3, 'module_decisions': [], 'custom_proposals': []},
    'specialist_sections': [{'section_id': 'section_test', 'module_ref': 'missing_module', 'proposal_ref': None, 'heading': 'Test', 'scope': 'catalogued_module', 'selection_rationale': 'test', 'evidence_refs': ['e1'], 'component_refs': [], 'group_refs': [], 'subsections': [{'subsection_id': 'test_analysis', 'heading': 'Test', 'focus_questions': ['How does it work?'], 'claims': []}]}],
    'source_prediction_ids': [],
    'human_review': {'reviewer_id_or_role': None, 'status': 'draft', 'reviewed_version': None, 'reviewed_sections': [], 'reviewed_at': None, 'disagreement_status': 'not_reviewed', 'correction_history': []},
    'legacy_source_annotation': None
}
try:
    validate_annotation(ann, catalog)
    print('   FAIL: should reject')
except ValueError as e:
    print(f'   PASS: {e}')

# 3. Invalid evidence reference
print('3. Invalid evidence reference:')
ann = {
    'schema_version': '1.1.0',
    'annotation_id': 'test',
    'image': img,
    'foundation': {'observe': {'visible_elements_locations': [], 'text_transcribed_with_confidence': [], 'uncertain_observations': []}, 'identify': {'components': [], 'component_groups': [], 'relationships': []}, 'hierarchy_composition': {'intended_hierarchy': [], 'apparent_hierarchy': [], 'attention_flow': [], 'spatial_relationships': []}, 'judge': {'component_assessments': [], 'overall_strengths': [], 'overall_weaknesses': [], 'impact_readability': [], 'impact_hierarchy': [], 'impact_communication': [], 'uncertainty_or_alternatives': []}, 'improve': []},
    'analysis_plan': {'module_catalog_version': '1.0.0', 'planner_version': '1.0.0', 'profile_source': 'human_interpretation', 'evidence': [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}], 'cues': [], 'max_specialist_sections': 3, 'module_decisions': [], 'custom_proposals': []},
    'specialist_sections': [{'section_id': 'section_test', 'module_ref': 'typography_letterforms', 'proposal_ref': None, 'heading': 'Test', 'scope': 'catalogued_module', 'selection_rationale': 'test', 'evidence_refs': ['nonexistent'], 'component_refs': [], 'group_refs': [], 'subsections': [{'subsection_id': 'test_analysis', 'heading': 'Test', 'focus_questions': ['How does it work?'], 'claims': []}]}],
    'source_prediction_ids': [],
    'human_review': {'reviewer_id_or_role': None, 'status': 'draft', 'reviewed_version': None, 'reviewed_sections': [], 'reviewed_at': None, 'disagreement_status': 'not_reviewed', 'correction_history': []},
    'legacy_source_annotation': None
}
try:
    validate_annotation(ann, catalog)
    print('   FAIL: should reject')
except ValueError as e:
    print(f'   PASS: {e}')

# 4. Invalid module decision
print('4. Invalid module decision (selected without section):')
ann = {
    'schema_version': '1.1.0',
    'annotation_id': 'test',
    'image': img,
    'foundation': {'observe': {}, 'identify': {}, 'hierarchy_composition': {}, 'judge': {}, 'improve': []},
    'analysis_plan': {'module_catalog_version': '1.0.0', 'planner_version': '1.0.0', 'profile_source': 'human_interpretation', 'evidence': [{'evidence_id': 'e1', 'text': 'test', 'source': 'human_interpretation', 'source_ref': None, 'confidence': 0.8, 'uncertainty': 'medium'}], 'cues': [], 'max_specialist_sections': 3, 'module_decisions': [{'module_ref': 'nonexistent_module', 'heading': 'Test', 'decision': 'selected', 'rationale': 'test', 'evidence_refs': ['e1'], 'relevance_score': 0.5}], 'custom_proposals': []},
    'specialist_sections': [{'section_id': 'section_test', 'module_ref': 'nonexistent_module', 'proposal_ref': None, 'heading': 'Test', 'scope': 'catalogued_module', 'selection_rationale': 'test', 'evidence_refs': ['e1'], 'component_refs': [], 'group_refs': [], 'subsections': [{'subsection_id': 'test_analysis', 'heading': 'Test', 'focus_questions': ['How does it work?'], 'claims': []}]}],
    'source_prediction_ids': [],
    'human_review': {'reviewer_id_or_role': None, 'status': 'draft', 'reviewed_version': None, 'reviewed_sections': [], 'reviewed_at': None, 'disagreement_status': 'not_reviewed', 'correction_history': []},
    'legacy_source_annotation': None
}
try:
    validate_annotation(ann, catalog)
    print('   FAIL: should reject')
except ValueError as e:
    print(f'   PASS: {e}')

# 5. Unsupported schema version
print('5. Unsupported schema version:')
ann = {
    'schema_version': '2.0.0',
    'annotation_id': 'test',
    'image': img,
    'foundation': {'observe': {}, 'identify': {}, 'hierarchy_composition': {}, 'judge': {}, 'improve': []},
    'analysis_plan': {'module_catalog_version': '1.0.0', 'planner_version': '1.0.0', 'profile_source': 'human_interpretation', 'evidence': [], 'cues': [], 'max_specialist_sections': 3, 'module_decisions': [], 'custom_proposals': []},
    'specialist_sections': [],
    'source_prediction_ids': [],
    'human_review': {'reviewer_id_or_role': None, 'status': 'draft', 'reviewed_version': None, 'reviewed_sections': [], 'reviewed_at': None, 'disagreement_status': 'not_reviewed', 'correction_history': []},
    'legacy_source_annotation': None
}
try:
    validate_annotation(ann, catalog)
    print('   FAIL: should reject')
except ValueError as e:
    print(f'   PASS: {e}')

# 6. Approved without reviewer
print('6. Approved without reviewer_id_or_role:')
ann = {
    'schema_version': '1.1.0',
    'annotation_id': 'test',
    'image': img,
    'foundation': {'observe': {}, 'identify': {}, 'hierarchy_composition': {}, 'judge': {}, 'improve': []},
    'analysis_plan': {'module_catalog_version': '1.0.0', 'planner_version': '1.0.0', 'profile_source': 'human_interpretation', 'evidence': [], 'cues': [], 'max_specialist_sections': 3, 'module_decisions': [], 'custom_proposals': []},
    'specialist_sections': [],
    'source_prediction_ids': [],
    'human_review': {'reviewer_id_or_role': None, 'status': 'approved', 'reviewed_version': None, 'reviewed_sections': [], 'reviewed_at': None, 'disagreement_status': 'not_reviewed', 'correction_history': []},
    'legacy_source_annotation': None
}
try:
    validate_annotation(ann, catalog)
    print('   FAIL: should reject')
except ValueError as e:
    print(f'   PASS: {e}')