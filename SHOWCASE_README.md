# demorph Design School — Showcase README

## Overview

This repository demonstrates an end-to-end pipeline for AI-assisted design analysis of poster images using Qwen3.5 9B (via Ollama) and a dynamic, cue-based annotation workflow.

### What this shows

1. **Real model inference** — Qwen3.5 9B analyzes actual poster images and produces structured observations
2. **Dynamic module selection** — Specialist analysis modules are selected per-poster based on visual cues
3. **Validated annotations** — All outputs conform to schema version 1.2 with cross-reference integrity
4. **Human-review ready** — Generated worksheets separate model observations from human-reviewable claims

---

## Quick Start

### Prerequisites

- Python 3.11+
- Ollama with `qwen3.5:9b-q4_K_M` model installed

```bash
# Install Ollama and the model
ollama pull qwen3.5:9b-q4_K_M
```

### Run the pipeline

```bash
cd demorph_design_school
python3 scripts/generate_v12_annotations.py
```

This will:
1. Load the 5 development images from `manifests/image_manifest.jsonl`
2. Run Qwen inference on each image
3. Parse observations and build structured foundation
4. Select specialist modules via cue-based planner
5. Generate v1.2 annotation JSON + Markdown review sheets
6. Validate all outputs

Output location: `annotations/drafts/dynamic_v1_2/batch_001/`

---

## Project Structure

```
demorph_design_school/
├── annotations/
│   ├── drafts/
│   │   ├── dynamic_v1_2/batch_001/     # ← v1.2 showcase outputs (5 images)
│   │   ├── dynamic/batch_001/           # v1.1 worksheets (human-interpretation cues)
│   │   └── batch_001/                   # v1.0 blank worksheets
│   ├── modules/
│   │   ├── analytical_module_catalog_v1.0.json  # 12 specialist modules
│   │   └── candidates/                       # promoted custom modules
│   ├── dynamic_workflow.py           # Core annotation + planner
│   ├── review_workflow.py            # Human review + promotion
│   └── schemas/                      # JSON schemas
├── designs/
│   └── original/                     # 96 source images
├── evaluation/
│   └── datasets/batch_001_manifest.json  # 20/5/5 dev/val/test split
├── manifests/
│   ├── image_manifest.jsonl          # All 96 images with metadata
│   ├── source_register.csv           # Rights tracking
│   └── split_manifest.json           # Split summary
├── scripts/
│   ├── generate_v12_annotations.py   # ← Main showcase pipeline
│   ├── run_baseline.py               # Baseline Qwen run (frozen)
│   ├── validate_annotation_pilot.py  # Validator
│   └── ...                           # Ingestion, batch prep, etc.
├── tests/                            # Unit/integration tests
├── test_integration.py               # 13 integration test cases
└── test_validator.py                 # Validator quality tests
```

---

## Data Flow

```
Image + Prompt → Ollama (Qwen3.5 9B)
                    ↓
        Thinking field → Markdown observations
                    ↓
    parse_qwen_observations() → 11 structured observations
                    ↓
    build_observation_component() → 11 foundation components
                    ↓
    category_to_signal mapping → Cues for planner
                    ↓
    plan_modules(catalog, evidence, cues) → Selected modules
                    ↓
    make_annotation() + foundation override → v1.2 annotation
                    ↓
    validate_annotation() → PASS
                    ↓
    Write JSON + Markdown → annotations/drafts/dynamic_v1_2/
```

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/generate_v12_annotations.py` | Main pipeline (inference → parse → plan → validate → write) |
| `annotations/dynamic_workflow.py` | Core planner, annotation builder, validator |
| `annotations/modules/analytical_module_catalog_v1.0.json` | 12 reusable specialist modules |
| `manifests/image_manifest.jsonl` | 96 images with splits + metadata |
| `evaluation/datasets/batch_001_manifest.json` | 20 dev / 5 val / 5 test split |

---

## Running Tests

```bash
# Unit tests
python3 -m pytest tests/ -v

# Integration tests (13 cases)
python3 test_integration.py

# Validator quality tests
python3 test_validator.py
```

All tests should pass.

---

## Example Output

For image `img_f5806551035bb4a71497` (Arthur Morgan poster):

- **11 observations** parsed from Qwen (main subject, typography, colour, composition, negative space, visual flow, layering, illustration style, branding, information density, design techniques)
- **11 foundation components** with types, roles, hierarchy contributions
- **3 specialist sections selected**: Typography, Colour Relationships, Branding
- **Validation**: PASSED

See `annotations/drafts/dynamic_v1_2/batch_001/img_f5806551035bb4a71497.json` for full structure.

---

## Human Review Workflow

Generated Markdown files in `annotations/drafts/dynamic_v1_2/batch_001/*.md` contain:

1. Qwen perception summary
2. Universal foundation checklist (Observe, Identify, Hierarchy, Judge, Improve)
3. Specialist section focus questions
4. Reviewer sign-off fields

Reviewers place approved annotations in `annotations/reviewed/` with `human_review.status = "approved"`.

---

## License & Rights

- Source images: `manifests/source_register.csv` tracks provenance
- No original images are modified
- No images are training-eligible until human review confirms rights
- Model outputs are stored separately from human-reviewed references

---

## Next Steps (Post-Showcase)

1. Human review of 5 v1.2 pilot drafts
2. Candidate module promotion from custom proposals
3. Scoring rubric application (Stage 7)
4. Feedback label collection (Stage 8)
5. Training export preparation