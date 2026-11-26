# demorph Design School — Curriculum v1.0

## Mission

Teach the visual-perception system to understand graphic design as an intentional communication system. The target is not merely object recognition or image captioning. The student should identify components, infer their communicative roles, reconstruct hierarchy and relationships, evaluate execution against an explicit brief, and propose evidence-based improvements.

## The lesson format

Every lesson follows the same five-step protocol:

1. **Observe:** report visible facts only (text, objects, shapes, regions, colour, placement, contrast, texture).
2. **Classify:** assign component types and likely design roles.
3. **Relate:** describe grouping, alignment, overlap, contrast, sequence, and spatial relationships.
4. **Judge:** evaluate effectiveness against the brief and rubric; cite the visual evidence.
5. **Improve:** propose a concrete change and explain the intended effect and trade-off.

The model must label uncertain interpretations as hypotheses. It must be allowed to answer `unknown`, `ambiguous`, or `not_applicable`.

---

## Level 1 — Visual literacy

**Question:** What is visibly in the image?

Learning objectives:
- Identify text blocks, people, products, objects, illustrations, logos, shapes, icons, patterns, backgrounds, and photographic regions.
- Separate foreground, middle ground, and background where meaningful.
- Describe approximate location, scale, colour, contrast, texture, lighting, and orientation.
- Recognise that an image may contain multiple visual layers and overlapping elements.
- Distinguish readable text from decorative or illegible text; do not invent wording.

Exercises:
- Image inventory: list visible elements without assigning a design role.
- Region localization: provide normalized boxes or polygons where the task requires geometry.
- OCR comparison: compare recognized text with verified transcription.
- Observation-versus-inference exercise: flag claims that go beyond pixels.

Assessment:
- Element detection/classification precision and recall.
- OCR character/word error rate on text-bearing examples.
- Human audit of unsupported visual claims.

**Exit gate:** the model can describe the image without hallucinating specific brands, locations, identities, or text.

## Level 2 — Design component literacy

**Question:** What job does each element perform?

Component vocabulary:
- Headline / title
- Deck / subtitle
- Body copy
- Caption
- Call to action
- Date, time, venue, price, contact, and other information blocks
- Hero image / subject
- Supporting image
- Logo / brand mark
- Product feature / badge / label
- Navigation or interface control
- Decorative element / texture / ornament
- Border, divider, frame, grid, and background treatment

Important rule: an element's visible form does not determine its role. A large text object may be a title, a quotation, a product name, or a decorative word. Use the brief and surrounding context; otherwise mark the role uncertain.

Exercises:
- Assign each annotated element one primary component role and optional secondary roles.
- Explain the evidence for each role.
- Separate semantic object identity (e.g. a person) from design role (e.g. hero subject).

Assessment:
- Macro-F1 for component-role classification.
- Reviewer agreement on ambiguous roles.
- Evidence coverage: proportion of role assignments supported by visible or brief-derived evidence.

**Exit gate:** the model separates object recognition from design-role understanding.

## Level 3 — Hierarchy and attention

**Question:** What should the viewer notice first, next, and last?

Concepts:
- Primary, secondary, tertiary, and utility/decorative levels.
- Relative visual weight: size, contrast, colour, isolation, position, sharpness, orientation, and face/subject salience.
- Reading order and visual flow.
- Grouping and chunking.
- Competing focal points and attention conflicts.
- Intended hierarchy versus observed hierarchy.

Hierarchy is contextual. The largest element is not automatically the most important. A date or call-to-action can be the primary task in a functional graphic. The model must compare the observed hierarchy to the communication goal.

Exercises:
- Rank design components by intended priority from the brief.
- Rank apparent visual attention order from the image.
- Compare intended and observed hierarchy; explain mismatches.
- Pairwise comparison: choose which of two versions better communicates a supplied brief.

Assessment:
- Kendall's tau or Spearman rank correlation against reviewed hierarchy order.
- Pairwise preference agreement.
- Separate score for whether the model correctly distinguishes intended from observed hierarchy.

**Exit gate:** the model can explain why an element attracts attention and whether that attention order serves the brief.

## Level 4 — Design principles and composition

**Question:** How are the components organised?

Principles and concepts:
- Contrast, alignment, proximity, repetition, balance, proportion, scale, rhythm, unity, variety, emphasis, hierarchy, and negative space.
- Grid, margins, columns, baseline alignment, modular systems, and safe areas.
- Symmetrical, asymmetrical, radial, diagonal, centered, and editorial compositions.
- Typography: type roles, size relationships, weight, width, line length, leading, tracking, legibility, and pairing.
- Colour: palette roles, value contrast, saturation, temperature, harmony, and functional colour use.
- Image treatment: crop, focal placement, masking, overlap, depth, and edge interaction.

Do not force every principle onto every design. `not_applicable` is a valid annotation.

Exercises:
- Identify evidence for a principle, not just its name.
- Detect alignment, spacing, and overlap issues.
- Evaluate text/background contrast and likely legibility.
- Explain how composition changes across aspect ratios.

Assessment:
- Principle classification with evidence.
- Geometry metrics for measurable claims.
- Ordinal reviewer agreement for qualitative judgments.

**Exit gate:** the model explains design principles through specific relationships visible in the image.

## Level 5 — Design critique

**Question:** How effectively does the design work for its purpose?

Critique dimensions:
- Brief/message clarity
- Hierarchy and information prioritisation
- Readability and accessibility
- Composition and balance
- Typography system
- Colour system
- Image/asset integration
- Consistency and craft
- Audience and context suitability

Every critique item must include:
- the claim;
- affected element IDs;
- visible evidence;
- severity or impact;
- whether the judgment is objective, brief-dependent, or subjective;
- uncertainty / alternative interpretation where relevant.

Avoid ungrounded statements such as “looks professional” unless the model explains what observable qualities support the judgment.

Assessment:
- Agreement with human-reviewed ordinal ratings.
- Evidence-groundedness: fraction of critique claims linked to elements or relationships.
- Unsupported-claim rate.
- Inter-reviewer agreement and adjudication rate.

**Exit gate:** the model produces useful, evidence-based critique and acknowledges uncertainty.

## Level 6 — Creative reasoning and revision

**Question:** What should change, and why?

Learning objectives:
- Propose targeted edits tied to the brief and diagnosed issue.
- Preserve working elements rather than redesigning everything.
- Explain expected benefits and trade-offs.
- Generate alternative directions with distinct design rationales.
- Prioritise revisions by communication impact, not personal taste alone.
- Re-evaluate the revised design and compare before/after outcomes.

Exercises:
- Give three revisions at different intervention levels: minimal, moderate, ambitious.
- Explain which constraints must remain fixed.
- Review a before/after pair and determine whether the change improved the intended outcome.

Assessment:
- Expert preference on pairwise alternatives.
- Constraint preservation.
- Improvement in measurable legibility/hierarchy/composition criteria.
- Human usefulness rating for recommendations.

**Exit gate:** recommendations are specific, brief-aware, feasible, and demonstrably better on held-out review tasks.

---

## Teaching sequence and data flow

1. Store design terminology and principle explanations in the Design Knowledge Base.
2. Store human-reviewed examples in the Design Evaluation Dataset.
3. Store accepted/rejected alternatives and reasons in the Preference/Feedback Dataset.
4. Retrieve relevant curriculum knowledge at inference time; do not stuff the entire textbook into every prompt.
5. Evaluate the unmodified Qwen baseline before training.
6. Inspect systematic errors and improve annotation coverage before deciding on fine-tuning.
7. Fine-tune only against a frozen benchmark and compare the candidate with the original model on unseen designs.

## Non-goals

- Do not train the model to imitate a single creator's style by default.
- Do not use popularity, likes, or views as a proxy for design quality.
- Do not collapse all visual judgments into one unexplained score.
- Do not infer the designer's intent when it is not present in the brief or supported by evidence.
- Do not treat automated model-generated labels as ground truth.
