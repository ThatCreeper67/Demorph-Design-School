# demorph Design School — Showcase Results

## Pipeline Execution Summary

**Date**: 2026-11-25\
**Model**: qwen3.5:9b-q4_K_M (Ollama)\
**Images processed**: 5 development images from batch_001\
**Output**: 5 v1.2 dynamic annotations in `annotations/drafts/dynamic_v1_2/batch_001/`

---

## Per-Image Results

### 1. img_f5806551035bb4a71497
**Source**: `designs/original/183ccc9ce2f55caf67b6d5b37e116586.jpg` (Arthur Morgan poster)

| Metric | Value |
|--------|-------|
| Qwen thinking length | 4,997 chars |
| Observations parsed | 11 |
| Foundation components | 11 |
| Specialist sections selected | 3 |
| Validation | ✅ PASSED |

**Observations**:
1. Main visual components and subjects (obs_001)
2. Typography and text elements (obs_002)
3. Colour relationships and palette (obs_003)
4. Composition structure and hierarchy (obs_004)
5. Negative space usage (obs_005)
6. Visual flow and directional cues (obs_006)
7. Layering and depth cues (obs_007)
8. Illustration or photographic style (obs_008)
9. Branding or identity markers (obs_009)
10. Information density (obs_010)
11. Distinctive design techniques (obs_011)

**Selected modules**:
- Typography and Letterform Analysis (triggered by: dense_text, typography_led)
- Colour Relationships (triggered by: dominant_colour_system)
- Branding and Identity (triggered by: visible_brandmark)

---

### 2. img_03280f90ebe513ab5be8
**Source**: `designs/original/19676aa6d2732508e95fd7770dbac5ba.jpg` (Edge of Singularity poster)

| Metric | Value |
|--------|-------|
| Qwen thinking length | 4,861 chars |
| Observations parsed | 3 |
| Foundation components | 3 |
| Specialist sections selected | 0 |
| Validation | ✅ PASSED |

**Observations**:
1. Main visual components and subjects
2. Colour relationships and palette
3. Composition structure and hierarchy

**Selected modules**: None (no cues matched catalog signals strongly enough)

---

### 3. img_967e9dcfff322008214d
**Source**: `designs/original/1e993d80ab988327e15db2ac0d96b933.jpg`

| Metric | Value |
|--------|-------|
| Qwen thinking length | 4,951 chars |
| Observations parsed | 2 |
| Foundation components | 2 |
| Specialist sections selected | 0 |
| Validation | ✅ PASSED |

**Observations**:
1. Main visual components and subjects
2. Typography and text elements

**Selected modules**: None

---

### 4. img_f1ff25c8769e4c3c7079
**Source**: `designs/original/26e600afd9935467d02f3cf94a51df93.jpg`

| Metric | Value |
|--------|-------|
| Qwen thinking length | 4,051 chars |
| Qwen response length | 649 chars |
| Observations parsed | 11 |
| Foundation components | 11 |
| Specialist sections selected | 3 |
| Validation | ✅ PASSED |

**Selected modules**:
- Typography and Letterform Analysis (triggered by: dense_text, typography_led)
- Colour Relationships (triggered by: dominant_colour_system)
- Branding and Identity (triggered by: visible_brandmark)

---

### 5. img_abe316099d69db022590
**Source**: `designs/original/41dc250e1919dfdf7ecbddb04b0b86ad.jpg`

| Metric | Value |
|--------|-------|
| Qwen thinking length | 4,936 chars |
| Observations parsed | 12 |
| Foundation components | 12 |
| Specialist sections selected | 3 |
| Validation | ✅ PASSED |

**Selected modules**:
- Illustration and Visual Metaphors (triggered by: illustration_led)
- Branding and Identity (triggered by: visible_brandmark)
- Information Density (triggered by: dense_text)

---

## Aggregate Statistics

| Metric | Total | Average |
|--------|-------|---------|
| Observations | 39 | 7.8 |
| Components | 39 | 7.8 |
| Specialist sections | 9 | 1.8 |
| Images with ≥1 specialist section | 3/5 | 60% |
| Validation pass rate | 5/5 | 100% |

---

## Module Selection Frequency

| Module | Selected Count | Images |
|--------|----------------|--------|
| typography_letterforms | 2 | img_f580..., img_f1ff... |
| colour_relationships | 2 | img_f580..., img_f1ff... |
| branding_identity | 3 | img_f580..., img_f1ff..., img_abe3... |
| illustration_metaphor | 1 | img_abe3... |
| information_density | 1 | img_abe3... |
| (others) | 0 | — |

---

## Validation Details

All 5 annotations passed `validate_annotation()` with:
- Schema version: 1.1.0 ✓
- Required envelope keys present ✓
- Unique evidence_ids, component_ids, module_refs ✓
- Cross-references valid (evidence_refs ⊆ evidence_ids, component_refs ⊆ component_ids) ✓
- Specialist sections reference exactly one selected module ✓
- Foundation references valid throughout ✓
- Human review status = draft (no reviewer required) ✓

---

## Output Files

```
annotations/drafts/dynamic_v1_2/batch_001/
├── img_f5806551035bb4a71497.json   (70,364 bytes)
├── img_f5806551035bb4a71497.md     (2,112 bytes)
├── img_03280f90ebe513ab5be8.json   (28,968 bytes)
├── img_03280f90ebe513ab5be8.md     (796 bytes)
├── img_967e9dcfff322008214d.json   (23,836 bytes)
├── img_967e9dcfff322008214d.md     (796 bytes)
├── img_f1ff25c8769e4c3c7079.json   (69,560 bytes)
├── img_f1ff25c8769e4c3c7079.md     (2,112 bytes)
├── img_abe316099d69db022590.json   (74,769 bytes)
└── img_abe316099d69db022590.md     (2,072 bytes)
```

JSON files contain full v1.2 annotation structure.
Markdown files contain human review worksheets.

---

## Known Limitations

1. **Two images had 0 specialist sections** (img_0328..., img_967e...): Qwen observations didn't produce categories that mapped to catalog trigger signals. The universal foundation is still populated.

2. **Category mapping is heuristic**: The `category_to_signal` dictionary maps Qwen's free-form headings to catalog signals. Some Qwen categories may not match.

3. **Qwen thinking field**: The model outputs analysis in `thinking`, not `response`. The pipeline handles both but this is model-specific behavior.

4. **No bounding boxes**: Qwen doesn't provide spatial coordinates; `bbox` is always null.

5. **Single image test**: Results based on 5 development images; not validated on validation/test splits.

---

## Comparison with v1.1

| Aspect | v1.1 (human cues) | v1.2 (Qwen cues) |
|--------|-------------------|------------------|
| Cue source | Human-interpreted visual tags | Qwen model observations |
| Specialist selection | Based on manifest tags | Based on parsed observations |
| Foundation content | Empty (blank worksheet) | Populated with Qwen analysis |
| Observations | 0 | 2-12 per image |
| Components | 0 | 2-12 per image |
| Review readiness | Blank template | Pre-populated claims to verify |