"""Phase 5 structured design reasoning validation and envelope helpers."""
from __future__ import annotations

import copy
from typing import Any

VERSION = "1.2.0"


def validate_reasoning(value: dict[str, Any]) -> None:
    """Validate Phase 5 references and avoid accepting empty/generic output as success."""
    if value.get("schema_version") != VERSION:
        raise ValueError("unsupported Phase 5 annotation version")
    evidence = value.get("evidence", [])
    observations = value.get("observations", [])
    relationships = value.get("relationships", [])
    ids = [item.get("evidence_id") for item in evidence]
    obs_ids = [item.get("observation_id") for item in observations]
    rel_ids = [item.get("relationship_id") for item in relationships]
    if not evidence or not observations:
        raise ValueError("Phase 5 output needs image evidence and observations")
    if len(ids) != len(set(ids)) or len(obs_ids) != len(set(obs_ids)) or len(rel_ids) != len(set(rel_ids)):
        raise ValueError("duplicate evidence, observation, or relationship id")
    evidence_ids, observation_ids, relationship_ids = set(ids), set(obs_ids), set(rel_ids)
    for item in observations:
        if not item.get("text") or not item.get("evidence_refs") or not set(item.get("evidence_refs", [])) <= evidence_ids:
            raise ValueError("observation has empty text or invalid evidence refs")
    for item in relationships:
        if not item.get("effect") or not set(item.get("observation_refs", [])) <= observation_ids:
            raise ValueError("relationship has empty effect or invalid observation refs")
        if not item.get("evidence_refs") or not set(item.get("evidence_refs", [])) <= evidence_ids:
            raise ValueError("relationship has invalid evidence refs")
        if not (set(item.get("subject_refs", [])) | set(item.get("object_refs", []))) <= observation_ids:
            raise ValueError("relationship endpoint does not reference an observation")
    curriculum_ids = set(value.get("curriculum_refs", []))
    for item in relationships:
        if not set(item.get("curriculum_refs", [])) <= curriculum_ids:
            raise ValueError("relationship has invalid curriculum refs")
    hierarchy = value.get("hierarchy", {})
    for item in hierarchy.get("apparent_order", []):
        if item.get("observation_ref") not in observation_ids:
            raise ValueError("hierarchy order has invalid observation ref")
    for item in hierarchy.get("reading_flow", []):
        if not set(item.get("sequence", [])) <= observation_ids:
            raise ValueError("reading flow has invalid observation refs")
    eval_ids = [item.get("evaluation_id") for item in value.get("evaluations", [])]
    if len(eval_ids) != len(set(eval_ids)):
        raise ValueError("duplicate evaluation id")
    for item in value.get("evaluations", []):
        if not set(item.get("relationship_refs", [])) <= relationship_ids:
            raise ValueError("evaluation has invalid relationship refs")
        if not set(item.get("observation_refs", [])) <= observation_ids:
            raise ValueError("evaluation has invalid observation refs")
        if not item.get("evidence_refs") or not set(item.get("evidence_refs", [])) <= evidence_ids:
            raise ValueError("evaluation has invalid evidence refs")
        if not set(item.get("curriculum_refs", [])) <= curriculum_ids:
            raise ValueError("evaluation has invalid curriculum refs")
    for item in value.get("recommendations", []):
        if not set(item.get("evaluation_refs", [])) <= {x.get("evaluation_id") for x in value.get("evaluations", [])}:
            raise ValueError("recommendation has invalid evaluation refs")
        if not item.get("evidence_refs") or not set(item.get("evidence_refs", [])) <= evidence_ids:
            raise ValueError("recommendation has invalid evidence refs")
    for item in value.get("specialists", []):
        if not item.get("evidence_refs") or not set(item.get("evidence_refs", [])) <= evidence_ids:
            raise ValueError("specialist has invalid evidence refs")
        if not set(item.get("relationship_refs", [])) <= relationship_ids:
            raise ValueError("specialist has invalid relationship refs")
        if not set(item.get("curriculum_refs", [])) <= curriculum_ids:
            raise ValueError("specialist has invalid curriculum refs")
    allowed = {"critical", "meaningful", "optional", "subjective"}
    if any(item.get("priority") not in allowed for item in value.get("recommendations", [])):
        raise ValueError("recommendation has invalid priority")


def make_annotation(image: dict[str, Any], raw: dict[str, Any], *, curriculum_refs: list[str],
                    model: str, elapsed_ms: float, brief: str | None = None,
                    prompt_version: str = "design-intelligence-v1.0") -> dict[str, Any]:
    """Wrap model reasoning in a versioned envelope while retaining claim provenance."""
    raw = copy.deepcopy(raw)
    available_curriculum = set(curriculum_refs)
    # Qwen sometimes emits null or invented curriculum IDs. Keep only retrieved IDs;
    # an unsupported principle reference is omitted rather than silently legitimized.
    for section in ("relationships", "evaluations", "specialists"):
        for item in raw.get(section, []):
            if "curriculum_refs" in item:
                item["curriculum_refs"] = [ref for ref in item["curriculum_refs"] if ref in available_curriculum]
    quality_flags = []
    if not brief:
        unsupported = ("audience", "non-japanese", "global audience", "viewers unfamiliar", "unfamiliar with japanese", "translation", "unreadable japanese", "brand", "design intent", "hybrid design intent")
        def keep_supported(section: str, id_key: str, extra_check=None) -> set[str]:
            retained, kept_ids = [], set()
            for item in raw.get(section, []):
                searchable = " ".join(str(v) for k, v in item.items() if k not in {"evidence_refs", "observation_refs", "relationship_refs", "curriculum_refs"}).casefold()
                term = next((word for word in unsupported if word in searchable), None)
                reason = f"unsupported {term} claim without a brief" if term else None
                if not reason and extra_check:
                    reason = extra_check(item)
                if reason:
                    label = item.get(id_key) or item.get("area") or "finding"
                    quality_flags.append(f"Suppressed {section[:-1]} {label}: {reason}.")
                else:
                    retained.append(item)
                    if item.get(id_key): kept_ids.add(item[id_key])
            raw[section] = retained
            return kept_ids

        rel_ids = keep_supported("relationships", "relationship_id")
        eval_ids = keep_supported("evaluations", "evaluation_id", lambda x: "depends on a suppressed relationship" if set(x.get("relationship_refs", [])) - rel_ids else None)
        keep_supported("recommendations", "recommendation_id", lambda x: "depends on a suppressed evaluation" if set(x.get("evaluation_refs", [])) - eval_ids else None)
        keep_supported("specialists", "area", lambda x: "depends on a suppressed relationship" if set(x.get("relationship_refs", [])) - rel_ids else None)
    known_evidence = {item.get("evidence_id") for item in raw.get("evidence", [])}
    known_relationships = {item.get("relationship_id") for item in raw.get("relationships", [])}
    valid_specialists = []
    for item in raw.get("specialists", []):
        evidence_refs, relationship_refs = set(item.get("evidence_refs", [])), set(item.get("relationship_refs", []))
        curriculum = set(item.get("curriculum_refs", []))
        if (not item.get("area") or not item.get("finding") or not evidence_refs
                or not evidence_refs <= known_evidence or not relationship_refs <= known_relationships
                or not curriculum <= available_curriculum):
            quality_flags.append(f"Suppressed optional specialist {item.get('area') or 'finding'}: its evidence or reference links were invalid.")
        else:
            valid_specialists.append(item)
    raw["specialists"] = valid_specialists
    applied_curriculum = sorted({ref for section in ("relationships", "evaluations", "specialists")
                                 for item in raw.get(section, []) for ref in item.get("curriculum_refs", [])
                                 if ref in available_curriculum})
    payload = {
        "schema_version": VERSION,
        "annotation_id": "phase5_" + image["image_id"],
        "image": {key: image[key] for key in ("image_id", "sha256", "relative_path")},
        "brief_context": brief,
        "analysis_metadata": {"model": model, "runtime": "ollama", "elapsed_ms": round(elapsed_ms, 2),
                              "prompt_version": prompt_version, "human_review": "unreviewed"},
        "evidence": raw.get("evidence", []),
        "observations": raw.get("observations", []),
        "relationships": raw.get("relationships", []),
        "hierarchy": raw.get("hierarchy", {"apparent_order": [], "reading_flow": [], "intended_priority": "unknown"}),
        "evaluations": raw.get("evaluations", []),
        "recommendations": raw.get("recommendations", []),
        "specialists": raw.get("specialists", []),
        "uncertainties": [*raw.get("uncertainties", []), *quality_flags],
        "curriculum_refs": applied_curriculum,
    }
    validate_reasoning(payload)
    return payload
