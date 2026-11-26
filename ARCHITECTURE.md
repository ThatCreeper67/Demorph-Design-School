# demorph Design School — Architecture Document

> The sections below document the original dataset/CLI workflow. The local interactive application added later is described in **Local application architecture** near the end.

## System Overview

The demorph Design School pipeline performs AI-assisted design analysis on poster images. It combines local LLM inference (Qwen3.5 9B via Ollama) with a dynamic, cue-based annotation workflow that selects specialist analysis modules per poster.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           demorph Design School                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐               │
│  │   Ingest     │────▶│  Batch Prep  │────▶│  Annotation  │               │
│  │  (images)    │     │  (splits)    │     │  Pipeline    │               │
│  └──────────────┘     └──────────────┘     └──────┬───────┘               │
│                                                    │                        │
│                         ┌──────────────────────────┼──────────────────┐   │
│                         ▼                          ▼                  ▼   │
│                ┌─────────────────┐         ┌─────────────┐    ┌─────────┐ │
│                │  Qwen Inference │         │  Planner    │    │ Validator│ │
│                │  (Ollama API)   │         │  (cues→mods)│    │(ref check)│ │
│                └────────┬────────┘         └──────┬──────┘    └────┬────┘ │
│                         │                         │                  │     │
│                         ▼                         ▼                  ▼     │
│                ┌──────────────────────────────────────────────────────┐   │
│                │              v1.2 Annotation                         │   │
│                │  foundation + analysis_plan + specialist_sections    │   │
│                └────────────────────────┬─────────────────────────────┘   │
│                                         │                                 │
│                                         ▼                                 │
│                              ┌─────────────────────┐                      │
│                              │  Output: JSON + MD  │                      │
│                              │  annotations/drafts/│                      │
│                              │  dynamic_v1_2/      │                      │
│                              └─────────────────────┘                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Image Ingestion & Manifests (`scripts/ingest_images.py`, `scripts/prepare_batch001.py`)

- Scans `designs/original/` for images
- Computes SHA-256, dimensions, format
- Creates `manifests/image_manifest.jsonl` (96 entries)
- Creates deterministic 20/5/5 dev/val/test split in `evaluation/datasets/batch_001_manifest.json`
- Tracks provenance in `manifests/source_register.csv`

### 2. Qwen Inference (`scripts/generate_v12_annotations.py::infer_qwen`)

```python
def infer_qwen(image_path: Path, prompt: str) -> dict[str, Any]:
    """Calls Ollama /api/generate with base64-encoded image."""
    payload = {
        "model": "qwen3.5:9b-q4_K_M",
        "prompt": prompt,
        "images": [base64_data],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 1200},
    }
```

**Key finding**: Qwen3.5 outputs structured analysis in the `thinking` field, not `response`. The pipeline extracts from both.

### 3. Observation Parser (`parse_qwen_observations`)

Parses markdown-style output with patterns like:
```markdown
**1. Visual Elements**
*   **The Protagonist:** A silhouette...
*   **Background:** Swirling texture...
```

Extracts:
- `observation_id` (auto: obs_001, obs_002...)
- `category` (heading text)
- `description` (bullet content)
- `source`: "model_inference"
- `confidence`: 0.7, `uncertainty`: "medium"

### 4. Foundation Builder (`build_observation_component`)

Maps observation categories → component types using `category_to_type`:

| Category keywords | component_type |
|-------------------|----------------|
| hero, protagonist, main subject, visual element | primary |
| typography, type, text | supporting |
| colour, color | supporting |
| composition, compositional | supporting |
| negative space, negative | background_context |
| visual flow, flow | supporting |
| layering, layer | supporting |
| illustration, metaphor | supporting |
| brand, branding | supporting |
| information, density | supporting |

Each observation becomes a `component` with:
- `component_id` = `observation_id`
- `component_type` / `significance`
- `functional_roles`, `visual_characteristics`
- `hierarchy_contribution`, `overall_contribution`
- `possible_improvements`

### 5. Cue Mapper (Category → Signal)

Maps Qwen's verbose categories to catalog trigger signals:

```python
category_to_signal = {
    "main visual components and subjects": "dominant_subject",
    "typography and text elements": "typography_led",
    "colour relationships and palette": "dominant_colour_system",
    "composition structure and hierarchy": "single_clear_focal_point",
    "negative space usage": "extensive_negative_space",
    "visual flow and directional cues": "directional_lines",
    "layering and depth cues": "overlapping_elements",
    "illustration or photographic style": "illustration_led",
    "branding or identity markers": "visible_brandmark",
    "information density": "dense_text",
    "distinctive design techniques": "prominent_texture",
}
```

### 6. Dynamic Planner (`annotations/dynamic_workflow.py::plan_modules`)

```python
def plan_modules(catalog, evidence, cues, max_sections=3):
    # 1. Collect signals from cues
    signals = {cue["signal"] for cue in cues}

    # 2. Score each module
    for module in catalog["modules"]:
        triggered = signals & set(module["trigger_signals"])
        suppressed = signals & set(module["suppress_signals"])
        score = sum(cue["confidence"] for cue in cues if cue["signal"] in triggered)
        select = bool(triggered) and not suppressed

    # 3. Select top modules up to max_sections
    # 4. Return plan with module_decisions (selected/omitted + rationale)
```

**Module Catalog** (12 modules in `analytical_module_catalog_v1.0.json`):
1. `typography_letterforms` — Typography and Letterform Analysis
2. `hero_visual` — Hero Visual Analysis
3. `colour_relationships` — Colour Relationships
4. `directional_visual_flow` — Directional Guidance and Visual Flow
5. `layering_depth` — Layering and Depth
6. `negative_space` — Negative Space Utilization
7. `illustration_metaphor` — Illustration and Visual Metaphors
8. `branding_identity` — Branding and Identity
9. `information_density` — Information Density
10. `grid_alignment` — Grid and Alignment
11. `texture_surface` — Texture and Surface Treatment
12. `component_attention_competition` — Component Interaction and Attention Competition

### 7. Annotation Builder (`make_annotation`)

Creates v1.1 schema annotation with:
- `schema_version`: "1.1.0"
- `image`: {image_id, sha256, relative_path}
- `foundation`: {observe, identify, hierarchy_composition, judge, improve}
- `analysis_plan`: planner output
- `specialist_sections`: one per selected module with focus_questions
- `human_review`: draft status

### 8. Validator (`validate_annotation`)

Comprehensive cross-reference checks:
- Schema envelope (v1.0 or v1.1)
- Unique IDs: evidence_id, component_id, group_id, relationship_id, module_ref, proposal_id
- Cross-refs: evidence_refs ⊆ evidence_ids, component_refs ⊆ component_ids, etc.
- Specialist sections reference exactly one selected module/proposal
- Foundation references valid throughout
- Approved annotations require reviewer_id_or_role

---

## Data Structures

### v1.2 Annotation (extends v1.1)

```json
{
  "schema_version": "1.1.0",
  "annotation_id": "annotation_img_xxx",
  "image": {"image_id": "...", "sha256": "...", "relative_path": "..."},
  "brief_context": null,
  "foundation": {
    "observe": {
      "visible_elements_locations": [...],
      "text_transcribed_with_confidence": [],
      "uncertain_observations": [...]
    },
    "identify": {
      "components": [...],
      "component_groups": [],
      "relationships": []
    },
    "hierarchy_composition": {
      "intended_hierarchy": [...],
      "apparent_hierarchy": [...],
      "attention_flow": [...],
      "spatial_relationships": [...]
    },
    "judge": {...},
    "improve": [...]
  },
  "analysis_plan": {
    "module_catalog_version": "1.0.0",
    "planner_version": "1.0.0",
    "profile_source": "human_interpretation",
    "evidence": [...],
    "cues": [...],
    "max_specialist_sections": 3,
    "module_decisions": [...],
    "custom_proposals": []
  },
  "specialist_sections": [...],
  "source_prediction_ids": [],
  "human_review": {"status": "draft", ...},
  "legacy_source_annotation": null
}
```

### Component (from observation)

```json
{
  "component_id": "obs_001",
  "component_type": "primary",
  "significance": "primary",
  "significance_rationale": {...},
  "bbox": null,
  "functional_roles": ["Main visual components and subjects:"],
  "visual_characteristics": ["- There's a man..."],
  "spatial_relationship_ids": [],
  "hierarchy_contribution": [...],
  "overall_contribution": [...],
  "strengths": [],
  "weaknesses": [],
  "possible_improvements": [...]
}
```

---

## File Locations

| Category | Path |
|----------|------|
| Source images | `designs/original/` (96 files) |
| Manifests | `manifests/image_manifest.jsonl`, `source_register.csv`, `split_manifest.json` |
| Batch manifest | `evaluation/datasets/batch_001_manifest.json` |
| Module catalog | `annotations/modules/analytical_module_catalog_v1.0.json` |
| Candidate modules | `annotations/modules/candidates/` |
| v1.0 drafts | `annotations/drafts/batch_001/` |
| v1.1 drafts | `annotations/drafts/dynamic/batch_001/` |
| **v1.2 drafts (showcase)** | `annotations/drafts/dynamic_v1_2/batch_001/` |
| Reviewed annotations | `annotations/reviewed/` |
| Review history | `annotations/review_history/` |
| Core workflow | `annotations/dynamic_workflow.py` |
| Review workflow | `annotations/review_workflow.py` |
| Main pipeline | `scripts/generate_v12_annotations.py` |

---

## Configuration Points

| Parameter | Location | Default |
|-----------|----------|---------|
| Max specialist sections | `catalog["policy"]["default_max_per_poster"]` | 3 |
| Qwen model | `infer_qwen()` payload | "qwen3.5:9b-q4_K_M" |
| Qwen temperature | `infer_qwen()` options | 0 |
| Qwen max tokens | `infer_qwen()` options | 1200 |
| Ollama endpoint | `infer_qwen()` URL | "http://127.0.0.1:11434/api/generate" |

---

## Error Handling

| Stage | Failure Mode | Handling |
|-------|--------------|----------|
| Inference | Ollama unreachable | Exception caught, empty response |
| Inference | Model timeout | 300s timeout, empty response |
| Parsing | No observations found | Empty list, foundation has empty arrays |
| Planning | No cues match | Empty specialist_sections, universal foundation only |
| Validation | Cross-ref failure | ValueError raised, logged as WARNING |
| Output | Write failure | Exception propagates |

---

## Extensibility

1. **New modules**: Add to `analytical_module_catalog_v1.0.json` with trigger/suppress signals
2. **New models**: Modify `infer_qwen()` to call different endpoint
3. **New output formats**: Extend Markdown writer in `generate_v12_annotations.py`
4. **Custom proposals**: Add to `analysis_plan.custom_proposals` for poster-specific modules
5. **Promotion pipeline**: `annotations/review_workflow.py::promote_module()` for catalog growth

---

## Local application architecture

The browser workspace uses only project-local static assets (`webui/`) and a standard-library Python HTTP server (`local_app.py`) bound to loopback. The browser sends a multipart image and optional brief to `POST /api/analyze`; it does not call Ollama or implement model logic.

The server validates PNG/JPEG/WEBP signatures and dimensions, preserves the original upload and SHA-256 in `local_app_data/uploads/`, then calls `run_phase5_pilot.analyze_image_bytes`. That function verifies the exact configured Ollama tag, retrieves curriculum knowledge (recording an uncertainty if retrieval fails), sends the original image bytes to Qwen, parses JSON, and builds a versioned Phase 5 annotation using `annotations/phase5_intelligence.py`. The v1.2 result keeps evidence, observations, relationships, hierarchy, evaluations, recommendations, specialists, uncertainties, and applied curriculum IDs in separate fields. References are validated before it is saved.

The API reports named backend stages instead of estimated percentages. It allows one model job at a time. Cancellation marks the job and discards output after an active generation returns; it cannot interrupt Ollama safely. SQLite stores job results and source metadata; originals remain in the uploads directory. History entries can be reopened and exported as JSON or Markdown. A model or curriculum limitation is represented as a partial result where the core analysis remains valid; malformed or invalid core output fails closed.

The upload guard limits encoded input to 20 MiB and decoded dimensions to 80 million pixels. Pillow is used opportunistically for full decode checks when present; the app does not install it. Diagnostic logs are local and rotated. No browser upload leaves the host; the server binds to `127.0.0.1` by default.

The Phase 5 model schema is independent from the older v1.0/v1.1 batch annotation workflow described above. The GUI exposes only fields present in each result and does not synthesize missing specialist or curriculum findings.
