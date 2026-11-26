# Reviewed feedback data

Use the correction schema in `schemas/correction_v1.0.json` for reviewed changes tied to archived model predictions. Use `schemas/preference_v1.0.json` for a human-selected preferred/rejected answer pair. Every item must identify its source image, prediction or prompt, annotation version, evidence, reviewer status, and reason.

No corrections or preference labels are present yet. Do not create records from model output alone; a human must review and approve the correction first.
