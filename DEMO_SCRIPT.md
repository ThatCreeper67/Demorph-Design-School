# demorph Design School — Demo Script

## Terminal Demonstration (5-7 minutes)

### Setup (before demo)

```bash
# 1. Ensure Ollama is running with Qwen model
ollama list
# Should show: qwen3.5:9b-q4_K_M

# 2. Navigate to project
cd demorph_design_school

# 3. Verify test images exist
ls designs/original/183ccc9ce2f55caf67b6d5b37e116586.jpg
ls designs/original/19676aa6d2732508e95fd7770dbac5ba.jpg
```

---

### Step 1: Show Project Structure (30 sec)

```bash
tree -L 3 -I '__pycache__|*.png|*.jpg' .
```

**Talking points**:
- 96 source images in `designs/original/`
- Deterministic 20/5/5 split in `evaluation/datasets/`
- 12 specialist modules in `annotations/modules/`
- v1.0, v1.1, and v1.2 draft directories

---

### Step 2: Run the Pipeline (2 min)

```bash
python3 scripts/generate_v12_annotations.py
```

**Expected output**:
```
Processing img_f5806551035bb4a71497...
  API response: response=0 chars, thinking=4997 chars
  Parsed 11 observations
  ✅ img_f5806551035bb4a71497 written (11 observations, 3 specialist sections)
Processing img_03280f90ebe513ab5be8...
  API response: response=0 chars, thinking=4861 chars
  Parsed 3 observations
  ✅ img_03280f90ebe513ab5be8 written (3 observations, 0 specialist sections)
Processing img_967e9dcfff322008214d...
  API response: response=0 chars, thinking=4951 chars
  Parsed 2 observations
  ✅ img_967e9dcfff322008214d written (2 observations, 0 specialist sections)
Processing img_f1ff25c8769e4c3c7079...
  API response: response=649 chars, thinking=4051 chars
  Parsed 11 observations
  ✅ img_f1ff25c8769e4c3c7079 written (11 observations, 3 specialist sections)
Processing img_abe316099d69db022590...
  API response: response=0 chars, thinking=4936 chars
  Parsed 12 observations
  ✅ img_abe316099d69db022590 written (12 observations, 3 specialist sections)
```

**Talking points**:
- Real inference on 5 images (~30s each)
- Qwen outputs in `thinking` field (model-specific)
- Dynamic specialist selection: 3/5 images get 3 modules each
- All pass validation

---

### Step 3: Inspect Generated Output (1 min)

```bash
# Show output files
ls -la annotations/drafts/dynamic_v1_2/batch_001/

# View one JSON (Arthur Morgan poster)
cat annotations/drafts/dynamic_v1_2/batch_001/img_f5806551035bb4a71497.json | head -100
```

**Talking points**:
- Full v1.2 schema with foundation + analysis_plan + specialist_sections
- 11 observations → 11 components → 3 specialist sections
- Cross-references validated

---

### Step 4: View Human Review Worksheet (1 min)

```bash
cat annotations/drafts/dynamic_v1_2/batch_001/img_f5806551035bb4a71497.md
```

**Talking points**:
- Pre-populated with Qwen's observations
- Universal foundation checklist (Observe, Identify, Hierarchy, Judge, Improve)
- Specialist sections with focus questions from catalog
- Ready for human reviewer to approve/disagree

---

### Step 5: Run Tests (30 sec)

```bash
# Unit tests
python3 -m pytest tests/ -v

# Integration tests
python3 test_integration.py
```

**Expected**: All 6 unit tests + 13 integration tests pass.

---

### Step 6: Show Architecture (30 sec)

```bash
cat ARCHITECTURE.md | head -80
```

---

## Key Demo Narrative Points

### 1. "No Mocking — Real Inference"
- Each image sent to local Ollama
- Qwen3.5 9B processes actual pixels
- ~30 seconds per image on CPU

### 2. "Dynamic, Not Fixed"
- Specialist modules selected PER POSTER
- Same catalog, different modules for each image
- Arthur Morgan poster → Typography + Colour + Branding
- Edge of Singularity → No specialist match (universal foundation only)
- Other poster → Illustration + Branding + Info Density

### 3. "Validated by Construction"
- Every cross-reference checked
- Invalid references caught at generation time
- Schema version enforced

### 4. "Human-in-the-Loop Ready"
- Model output separated from human review
- Worksheets guide reviewer through claims
- Status tracking: draft → approved

### 5. "Rights-Aware"
- Source register tracks provenance
- No training until human confirms rights
- Original images never modified

---

## Troubleshooting During Demo

| Issue | Fix |
|-------|-----|
| Ollama not running | `ollama serve` in separate terminal |
| Model not found | `ollama pull qwen3.5:9b-q4_K_M` |
| Timeout | Increase `num_predict` or reduce prompt |
| No observations | Check Qwen thinking field parsing |
| Validation fails | Check evidence_ids match across sections |

---

## Quick Re-run Commands

```bash
# Re-run single image (modify script to limit=1)
python3 -c "
import json, base64, urllib.request
from pathlib import Path
from scripts.generate_v12_annotations import infer_qwen, parse_qwen_observations

img = Path('designs/original/183ccc9ce2f55caf67b6d5b37e116586.jpg')
result = infer_qwen(img, 'Analyze this poster...')
print('thinking:', len(result.get('thinking', '')))
print('response:', len(result.get('response', '')))
obs = parse_qwen_observations(result.get('thinking', ''))
print('observations:', len(obs))
"
```

---

## Demo Variations

### 5-minute version
- Skip Step 1 (structure)
- Run pipeline + show one output + tests

### 10-minute deep dive
- Show catalog JSON
- Show planner logic in `dynamic_workflow.py`
- Show validator cross-reference checks
- Show review workflow for promotion

### Audience-specific focus

| Audience | Emphasize |
|----------|-----------|
| ML Engineers | Inference pipeline, structured output parsing |
| Designers | Specialist modules, focus questions, review worksheets |
| Researchers | Rights tracking, schema validation, evaluation splits |
| Product | Human-in-the-loop, dynamic adaptation, audit trail |