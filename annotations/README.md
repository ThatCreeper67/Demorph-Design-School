# Annotation workflow

The versioned JSON Schema is `schemas/design_annotation_v1.0.json`. Each claim carries a source label and uncertainty; evidence is linked by stable IDs. `human_review.status` must be `approved` before a record can become a reference label. Model predictions remain separate and are never promoted automatically.

Five blank pilot records and readable Markdown review sheets are created under `drafts/batch_001/`. They are templates for human review, not annotations or ground truth. Do not scale bulk annotation until the five pilot records have been reviewed and approved.
