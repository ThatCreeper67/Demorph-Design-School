#!/usr/bin/env python3
"""Verify all generated annotations are valid."""
import json
from pathlib import Path
from annotations.dynamic_workflow import validate_annotation, load_catalog

catalog = load_catalog(Path('.'))
out_dir = Path('annotations/drafts/dynamic_v1_2/batch_001')

print("=== Annotation Verification ===")
print()

all_valid = True
for json_file in sorted(out_dir.glob('*.json')):
    with open(json_file) as f:
        ann = json.load(f)
    try:
        validate_annotation(ann, catalog)
        print(f"✅ {json_file.name}: VALID")
        sections = ann.get('specialist_sections', [])
        claims_total = sum(
            len(sec.get('subsections', [{}])[0].get('claims', []))
            for sec in sections
            if sec.get('subsections')
        )
        print(f"   specialist_sections: {len(sections)}, claims_total: {claims_total}")
    except Exception as e:
        print(f"❌ {json_file.name}: INVALID - {e}")
        all_valid = False

print()
print(f"Total annotations: {len(list(out_dir.glob('*.json')))}")
print(f'All valid: {all_valid}')
exit(0 if all_valid else 1)