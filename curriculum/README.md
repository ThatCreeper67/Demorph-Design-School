# Design School Knowledge Base

The source textbook remains `design_curriculum.md` v1.0 and the source ontology remains `design_ontology.json` v1.0.0. The eight module files add retrieval-sized lessons while preserving the source curriculum's terminology and Observe → Classify → Relate → Judge → Improve sequence.

`design_ontology_extension_v1.1.json` is an additive vocabulary extension. It does not overwrite or silently change the source ontology. `knowledge_index.json` maps each module to its source level and searchable concepts.

Run keyword retrieval with:

```powershell
python curriculum/retrieve.py "hierarchy evidence" --limit 3
python curriculum/retrieve.py "font readability" --module typography
```

Retrieval is deterministic keyword matching, not semantic search. It returns source module text and index metadata for traceability.
