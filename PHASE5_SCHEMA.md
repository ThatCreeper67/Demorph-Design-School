# Phase 5 annotation schema

The Phase 5 pilot uses the additive `1.2.0` reasoning envelope in `annotations/design_intelligence_v1.2.schema.json`. It does not rewrite historical v1.0 or v1.1 annotations; existing validators continue to accept those versions under their original contracts.

## Reasoning chain

`evidence` stores image-visible cues with stable IDs. `observations` describe what is seen and cite one or more evidence IDs. `relationships` connect observation IDs and explain the interaction and its likely effect. `hierarchy` records apparent prominence and plausible reading flow separately from intended priority. `evaluations` cite evidence and relationships, name the design dimension, and separate judgment from likely impact. `recommendations` cite an evaluation and evidence, state a change, and explain its expected effect. `specialists` provide optional area-specific findings with evidence and relationship references. Curriculum IDs are recorded only when the principle is applied in a finding.

Confidence is the model's estimate, not measured accuracy. The local validator checks ID links, evidence presence, recommendation priority, and duplicate IDs; it cannot independently confirm that a visual claim matches the image. When no brief exists, the envelope builder suppresses explicit unsupported brand, audience, translation, and intent claims, plus any findings that depend on a suppressed relationship. Unknown curriculum IDs are omitted. Suppression reasons are logged under `uncertainties`; the original response remains in the separate raw prediction record. These lexical safeguards are narrow and do not prove that remaining claims are accurate. Pilot records are always marked unreviewed. Human review is required before use as reference data.

The JSON Schema constrains field shape and value ranges. Cross-record references are additionally checked by `annotations/phase5_intelligence.py::validate_reasoning` because JSON Schema alone does not conveniently enforce these ID joins.
