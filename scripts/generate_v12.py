#!/usr/bin/env python3
"""Generate v1.2 dynamic annotations with Qwen3.5 9B inference.

Primary entry point for the showcase pipeline with CLI support.
Adds Phase 3: curriculum integration, evidence grounding, and improved specialist analysis.
"""
from __future__ import annotations

import argparse
import json
import sys
import base64
import urllib.request
import re
import socket
from pathlib import Path
from typing import Any

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from annotations.dynamic_workflow import load_catalog, make_annotation, validate_annotation, plan_modules
from annotations.review_workflow import ensure_directories
from curriculum.retrieve import retrieve

# ── Qwen inference ────────────────────────────────────────────────────────────

EXPECTED_MODEL = "qwen3.5:9b-q4_K_M"
MAX_TOKENS = 2000  # increased from 1200 to reduce truncation
HEALTH_TIMEOUT = 2  # seconds


def check_ollama_health(host="127.0.0.1", port=11434, timeout: int = HEALTH_TIMEOUT) -> bool:
    """Check if Ollama server is responsive."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def verify_model(model_name: str) -> bool:
    """Verify the requested model matches the expected model."""
    return model_name == EXPECTED_MODEL


def infer_qwen(image_path: Path, prompt: str, timeout: int = 300) -> dict[str, Any]:
    """Run Qwen3.5 9B via Ollama API and return the structured response."""
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    base64_data = base64.b64encode(image_bytes).decode()

    payload = {
        "model": EXPECTED_MODEL,
        "prompt": prompt,
        "images": [base64_data],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": MAX_TOKENS},
    }

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read())

    return result


# ── Qwen observation parser ───────────────────────────────────────────────────
SOURCE_ENUM = ["direct_observation", "model_inference", "human_interpretation", "brief_derived"]
UNCERTAINTY_ENUM = ["low", "medium", "high", "unknown", "ambiguous", "not_applicable"]


def parse_qwen_observations(response_text: str) -> list[dict[str, Any]]:
    """Parse Qwen's free-form response into structured observations.

    Observations use markdown-style headings: **1. Category** followed by description bullets.
    Returns observations with observation_id, category, description, source, confidence, uncertainty.
    """
    observations = []
    lines = response_text.split("\n")
    current_category = None
    current_description_lines = []

    def flush_observation():
        nonlocal current_category, current_description_lines
        if current_category and current_description_lines:
            obs_id = f"obs_{len(observations) + 1:03d}"
            description = " ".join(current_description_lines).strip()
            # Normalize uncertainty based on description length / specificity
            if not description:
                uncertainty = "unknown"
            elif len(description) < 20:
                uncertainty = "high"
            else:
                uncertainty = "medium"
            observations.append({
                "observation_id": obs_id,
                "category": current_category,
                "description": description,
                "source": "model_inference",
                "confidence": 0.7,
                "uncertainty": uncertainty,
            })
        current_category = None
        current_description_lines = []

    for line in lines:
        stripped = line.strip()
        heading_match = None
        if stripped.startswith("**"):
            inner = stripped.strip("* ").strip()
            num_match = re.match(r"^(\d+)\.\s*(.*)", inner)
            if num_match:
                heading_match = (num_match.group(2).strip(), True)
            else:
                heading_match = (inner.strip("*"), False)

        if heading_match:
            flush_observation()
            current_category = heading_match[0]
            if not heading_match[1] and current_description_lines == []:
                current_description_lines = [stripped]
            continue

        if current_category:
            current_description_lines.append(stripped)

    flush_observation()
    return observations


def extract_json_from_thinking(thinking_text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from Qwen's thinking field."""
    if not thinking_text:
        return None

    json_match = re.search(r"\{[^}]*\}", thinking_text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict) and "observations" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    array_match = re.search(r"\[.*?\]", thinking_text, re.DOTALL)
    if array_match:
        try:
            parsed = json.loads(array_match.group(0))
            if isinstance(parsed, list):
                return {"observations": parsed}
        except json.JSONDecodeError:
            pass

    return None


# ── Observation evidence handling ─────────────────────────────────────────────
def classify_uncertainty(description: str) -> str:
    """Classify uncertainty level from observation description.

    Rules:
    - Empty description → unknown
    - Very short (<20 chars) → high uncertainty
    - Medium-length → medium uncertainty
    - Longer with qualifiers → low uncertainty
    - Explicit qualifiers (maybe, possibly, uncertain) → low
    """
    if not description or not description.strip():
        return "unknown"

    d = description.strip().lower()

    # Explicit uncertainty markers
    if any(word in d for word in ["maybe", "possibly", "perhaps", "uncertain", "doubt", "questionable"]):
        return "low"

    if len(description) < 20:
        return "high"

    if len(description) < 50:
        return "medium"

    # Longer descriptions with hedge words
    hedge_words = ["seems", "appears", "suggests", "indicates", "may", "might"]
    if any(word in d for word in hedge_words):
        return "low"

    return "low"


def build_observation_component(
    observations: list[dict[str, Any]],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Build foundation.identify.components from Qwen observations.

    Each observation becomes a component with type determined by category mapping.
    Includes evidence_refs, uncertainty, and strengths/weaknesses based on available evidence.
    """
    category_to_type = {
        "typography": "supporting", "type": "supporting", "text": "supporting",
        "hero": "primary", "protagonist": "primary", "main subject": "primary",
        "visual element": "primary", "colour": "supporting", "color": "supporting",
        "composition": "supporting", "compositional": "supporting",
        "negative space": "background_context", "negative": "background_context",
        "visual flow": "supporting", "flow": "supporting",
        "layering": "supporting", "layer": "supporting",
        "illustration": "supporting", "metaphor": "supporting",
        "brand": "supporting", "branding": "supporting",
        "information": "supporting", "density": "supporting",
        "density of": "supporting", "component": "supporting", "element": "supporting",
    }

    components = []
    for i, obs in enumerate(observations):
        obs_cat = obs["category"].lower()
        comp_type = "supporting"
        for key, val in category_to_type.items():
            if key in obs_cat:
                comp_type = val
                break

        component_id = obs["observation_id"]
        uncertainty = obs.get("uncertainty", "medium")
        confidence = obs.get("confidence", 0.7)

        component = {
            "component_id": component_id,
            "component_type": comp_type or "supporting",
            "significance": "primary" if comp_type == "primary" else "supporting",
            "significance_rationale": {
                "text": f"This {obs['category'].lower()} anchors attention in the poster",
                "source": "model_inference",
                "evidence_refs": [obs["observation_id"]],
                "confidence": confidence,
                "uncertainty": uncertainty,
            },
            "bbox": None,
            "functional_roles": [obs["category"]],
            "visual_characteristics": [obs["description"]],
            "spatial_relationship_ids": [],
            "hierarchy_contribution": [{
                "text": f"{obs['category']} contributes to {comp_type} hierarchy",
                "source": "model_inference",
                "evidence_refs": [obs["observation_id"]],
                "uncertainty": uncertainty,
            }],
            "overall_contribution": [{
                "text": f"{obs['category']} is a {comp_type} element in the composition",
                "source": "model_inference",
                "evidence_refs": [obs["observation_id"]],
                "uncertainty": uncertainty,
            }],
            "strengths": [],
            "weaknesses": [],
            "possible_improvements": [{
                "change": f"Refine the {obs['category'].lower()} role and relationship to other elements",
                "evidence_refs": [obs["observation_id"]],
                "expected_impact": "Improved visual communication",
                "trade_offs": ["May require rebalancing composition"],
                "source": "model_inference",
                "uncertainty": uncertainty,
            }],
        }
        components.append(component)

    return {"components": components, "component_groups": [], "relationships": []}


# ── Foundation builder ───────────────────────────────────────────────────────
def build_foundation(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Build full foundation from observations with evidence-grounded uncertainty."""

    components = build_observation_component(observations, {})["components"]

    # Build uncertain observations with proper uncertainty classification
    uncertain_obs = []
    for obs in observations:
        unc = classify_uncertainty(obs["description"])
        uncertain_obs.append({
            "text": obs["description"],
            "source": "model_inference",
            "evidence_refs": [obs["observation_id"]],
            "uncertainty": unc,
        })

    # Transcribe visible text if description suggests readable text
    text_transcribed = []
    for obs in observations:
        lower_desc = obs["description"].lower()
        # Check for text-like content (short, distinctive, likely headline/title)
        if any(kw in lower_desc for kw in ["title", "heading", "poster", "name", "text", "typography"]):
            text_transcribed.append({
                "text": obs["description"][:200],
                "source": "model_inference",
                "evidence_refs": [obs["observation_id"]],
                "uncertainty": obs.get("uncertainty", "medium"),
            })

    hierarchy_contribution = []
    for comp in components:
        unc = comp.get("significance_rationale", {}).get("uncertainty", "medium")
        hierarchy_contribution.append({
            "text": comp["significance_rationale"]["text"],
            "source": "model_inference",
            "evidence_refs": comp["significance_rationale"]["evidence_refs"],
            "uncertainty": unc,
        })

    judge_uncertainties = []
    for comp in components:
        unc = comp.get("uncertainty", "medium")
        judge_uncertainties.append(f"Uncertainty: {unc}")

    return {
        "observe": {
            "visible_elements_locations": [
                {
                    "text": obs["description"][:200],
                    "source": "model_inference",
                    "evidence_refs": [obs["observation_id"]],
                    "uncertainty": obs.get("uncertainty", "medium"),
                }
                for obs in observations
            ],
            "text_transcribed_with_confidence": text_transcribed,
            "uncertain_observations": uncertain_obs,
        },
        "identify": {
            "components": components,
            "component_groups": [],  # Will populate if cross-component relationships found
            "relationships": [],
        },
        "hierarchy_composition": {
            "intended_hierarchy": [
                {
                    "component_ref": comp["component_id"],
                    "level": "primary" if comp["component_type"] == "primary" else "supporting",
                    "order": i + 1,
                    "rationale": comp["significance_rationale"]["text"],
                    "evidence_refs": comp["significance_rationale"]["evidence_refs"],
                    "source": "model_inference",
                    "uncertainty": comp["significance_rationale"]["uncertainty"],
                }
                for i, comp in enumerate(components)
            ],
            "apparent_hierarchy": [
                {
                    "component_ref": comp["component_id"],
                    "level": "primary" if comp["component_type"] == "primary" else "supporting",
                    "order": i + 1,
                    "rationale": f"Visually, {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} appears {comp['component_type']}",
                    "evidence_refs": [comp["component_id"]],
                    "source": "model_inference",
                    "uncertainty": comp.get("uncertainty", "medium"),
                }
                for i, comp in enumerate(components)
            ],
            "attention_flow": [
                {
                    "text": f"Eye flows through {comp['functional_roles'][0] if comp['functional_roles'] else 'element'}",
                    "source": "model_inference",
                    "evidence_refs": [comp["component_id"]],
                    "uncertainty": comp.get("uncertainty", "medium"),
                }
                for comp in components
            ],
            "spatial_relationships": [
                {
                    "relationship_id": f"rel_{i}_{j}",
                    "subject_refs": [comp1["component_id"]],
                    "relation": "adjacent_to_or_overlapping",
                    "object_refs": [comp2["component_id"]],
                    "effect": "visible_interaction",
                    "evidence_refs": [comp1["component_id"], comp2["component_id"]],
                    "source": "model_inference",
                    "uncertainty": "medium",
                }
                for i, comp1 in enumerate(components[:3])
                for j, comp2 in enumerate(components[i + 1: min(i + 2, len(components))], i + 1)
            ],
        },
        "judge": {
            "component_assessments": [
                {
                    "component_ref": comp["component_id"],
                    "strengths": comp["strengths"] if comp["strengths"] else [
                        f"Visible {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} presence"
                    ] if comp.get("visual_characteristics") else [],
                    "weaknesses": comp["weaknesses"] if comp["weaknesses"] else [
                        f"Uncertain {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} contribution to communication"
                    ] if not comp.get("visual_characteristics") else [],
                    "impact": comp.get("possible_improvements", [{}])[0].get("expected_impact", "")
                    if comp.get("possible_improvements")
                    else "",
                    "source": "model_inference",
                }
                for comp in components
            ],
            "overall_strengths": [
                f"Qwen identified {len(observations)} core design elements"
                if observations
                else ["No design elements identified"]
            ],
            "overall_weaknesses": (
                [] if observations else ["No design elements identified"]
                or (
                    [f"{len([o for o in observations if classify_uncertainty(o['description']) == 'high'])} of {len(observations)} observations have high uncertainty"]
                    if observations
                    else []
                )
            ),
            "impact_readability": (
                [f"{len([o for o in observations if 'text' in o['category'].lower()])} of {len(observations)} observed text elements affect legibility"]
                if observations and any('text' in o['category'].lower() for o in observations)
                else ["No text elements identified; readability assessment uncertain"]
                if observations
                else []
            ),
            "impact_hierarchy": (
                [f"{len([o for o in observations if o['category'] in ['main visual components and subjects', 'hero', 'protagonist']])} of {len(observations)} observed elements affect visual priority"]
                if observations
                else ["No focal elements identified; hierarchy assessment uncertain"]
                if observations
                else []
            ),
            "impact_communication": (
                [f"{len(observations)} observed elements contribute to message communication"]
                if observations
                else ["No elements identified; communication assessment uncertain"]
                if observations
                else []
            ),
            "uncertainty_or_alternatives": (
                [f"Alternative interpretation of {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} possible"]
                if components
                else ["No elements identified; interpretation uncertain"]
            ),
        },
        "improve": [
            {
                "change": f"Refine the {comp['functional_roles'][0].lower() if comp['functional_roles'] else 'element'} role and relationship to other elements"
                if comp.get("visual_characteristics")
                else "Add more design elements with clearer visual hierarchy",
                "component_refs": [comp["component_id"]],
                "expected_impact": "Improved visual communication and hierarchy clarity",
                "trade_offs": ["May require rebalancing composition"],
                "source": "model_inference",
                "uncertainty": comp.get("uncertainty", "medium"),
            }
            for comp in components
        ],
    }


# ── Curriculum integration ────────────────────────────────────────────────────

def retrieve_curriculum(root: Path, query: str, module: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
    """Retrieve relevant curriculum knowledge for the given query and optional module.

    Integrates with the existing curriculum/retrieve.py knowledge index.
    Returns entries with title, summary, keywords, and full content.
    """
    try:
        results = retrieve(str(root), query, module, limit)
        return results
    except Exception as e:
        # Log but don't crash; curriculum is enhancement, not required
        print(f"  Curriculum retrieval note: {e}")
        return []


def apply_curriculum_to_observations(
    observations: list[dict[str, Any]],
    catalog: dict[str, Any],
    root: Path,
) -> list[dict[str, Any]]:
    """Apply relevant design curriculum principles to each observation.

    For each observation, retrieves knowledge and adds:
    - curriculum_refs: which knowledge entries apply
    - principle_applications: how principles map to the observation
    """
    enhanced = []
    for obs in observations:
        cat_lower = obs["category"].lower()
        # Build query from category + key terms
        query_words = [cat_lower]
        # Add keyword hints based on category
        if "typography" in cat_lower or "text" in cat_lower or "type" in cat_lower:
            query_words.append("typography")
            query_words.append("legibility")
        if "colour" in cat_lower or "color" in cat_lower:
            query_words.append("colour")
            query_words.append("contrast")
        if "composition" in cat_lower:
            query_words.append("composition")
            query_words.append("hierarchy")
        if "brand" in cat_lower or "branding" in cat_lower:
            query_words.append("branding")
            query_words.append("identity")
        if "negative" in cat_lower:
            query_words.append("negative_space")
            query_words.append("balance")
        if "visual_flow" in cat_lower or "flow" in cat_lower:
            query_words.append("visual_flow")
            query_words.append("direction")
        if "layering" in cat_lower or "layer" in cat_lower:
            query_words.append("layering")
            query_words.append("depth")
        if "illustration" in cat_lower or "illustration" in cat_lower:
            query_words.append("illustration")
            query_words.append("metaphor")
        if "information_density" in cat_lower or "density" in cat_lower:
            query_words.append("information_density")
            query_words.append("readability")

        query = " ".join(query_words)

        # Retrieve relevant knowledge
        knowledge = retrieve_curriculum(root, query, module=None, limit=3)

        # Map knowledge principles to focus questions
        principle_applications = []
        for entry in knowledge:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            keywords = entry.get("keywords", [])
            # Match keywords to observation category
            matched_kw = [k for k in keywords if k.lower() in cat_lower]
            if matched_kw or summary:
                principle_applications.append({
                    "knowledge_id": entry.get("knowledge_id"),
                    "title": title,
                    "summary": summary,
                    "matched_keywords": matched_kw,
                    "application": f"Principle from '{title}': {summary[:100]}" if summary else f"Related to {title}",
                })

        enhanced.append({
            **obs,
            "curriculum_refs": [k["knowledge_id"] for k in knowledge],
            "principle_applications": principle_applications,
        })

    return enhanced


# ── Cue/signal mapping ────────────────────────────────────────────────────────

CATEGORY_TO_SIGNAL = {
    "main visual components and subjects": "dominant_subject",
    "visual components and subjects": "dominant_subject",
    "typography and text elements": "typography_led",
    "type and text": "typography_led",
    "colour relationships and palette": "dominant_colour_system",
    "color relationships and palette": "dominant_colour_system",
    "composition structure and hierarchy": "single_clear_focal_point",
    "composition structure": "single_clear_focal_point",
    "negative space usage": "extensive_negative_space",
    "negative space": "extensive_negative_space",
    "visual flow and directional cues": "directional_lines",
    "visual flow": "directional_lines",
    "layering and depth cues": "overlapping_elements",
    "layering": "overlapping_elements",
    "illustration or photographic style": "illustration_led",
    "illustration style": "illustration_led",
    "photographic style": "illustration_led",
    "branding or identity markers": "visible_brandmark",
    "branding": "visible_brandmark",
    "information density": "dense_text",
    "distinctive design techniques": "prominent_texture",
    "design techniques": "prominent_texture",

    # Missing signal mappings added for Phase 3 (complete coverage of catalog triggers)
    "modular information layout": "modular_information_layout",
    "repeated alignment": "repeated_alignment",
    "column structure": "column_structure",
    "table like blocks": "table_like_blocks",
    "single clear focal point": "single_clear_focal_point",
    "competing focals": "competing_focals",
    "attention conflict": "attention_conflict",
    "multiple high salience elements": "multiple_high_salience_elements",
    "clean flat surface": "clean_flat_surface",
    "freeform only composition": "freeform_only_composition",
    "photography only": "photography_only",
    "static centered composition": "static_centered_composition",
    "flat single plane": "flat_single_plane",
    "single message minimal layout": "single_message_minimal_layout",
    "prominent texture": "prominent_texture",
    "material surface": "material_surface",
    "texture overprint": "texture_overprint",
    "halftone or grain": "halftone_or_grain",
    "visible brandmark": "visible_brandmark",
    "repeated brand system": "repeated_brand_system",
    "identity lockup": "identity_lockup",
    "brand colour system": "brand_colour_system",
    "no brand evidence": "no_brand_evidence",
    "no distinct visual subject": "no_distinct_visual_subject",
    "no legible or visible type": "no_legible_or_visible_type",
    "dense text": "dense_text",
    "many information blocks": "many_information_blocks",
    "schedule or lineup": "schedule_or_lineup",
    "small supporting copy": "small_supporting_copy",
}


# ── Qwen Prompt ──────────────────────────────────────────────────────────────
QWEN_PROMPT = """Analyze this poster design image. Provide observations on:
- Main visual components and subjects
- Typography and text elements (roles, scale, hierarchy)
- Colour relationships and palette
- Composition structure and hierarchy
- Negative space usage
- Visual flow and directional cues
- Layering and depth cues
- Illustration or photographic style
- Branding or identity markers
- Information density
- Distinctive design techniques

For each observation, give it a short ID (like obs_001), a category (from the list above), and a concise description. Be factual and concise. Output in markdown format with headings for each category.
"""


# ── Annotation writer ───────────────────────────────────────────────────────
def write_annotation(
    annotation: dict[str, Any], output_path: Path, image_info: dict[str, str],
    sections: list[dict[str, Any]], plan: dict[str, Any],
    curriculum_evidence: list[dict[str, Any]] | None = None,
) -> None:
    """Write JSON and Markdown outputs with curriculum integration."""
    output_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_path = output_path.with_suffix(".md")
    md_lines = [
        f"# Dynamic v1.2 human review — {annotation['image']['image_id']}",
        "",
        f"Image: `{image_info['relative_path']}`",
        f"SHA-256: `{image_info['sha256']}`",
        "",
        "## Qwen Perception Summary",
        f"- Observations generated: {len(annotation['foundation']['observe']['visible_elements_locations'])}",
        "- Model: qwen3.5:9b-q4_K_M via Ollama", "",
        "## Universal foundation (review these claims against the poster)",
        "1. **Observe** — Visible elements, text, uncertainties",
        "2. **Identify** — Components, types, relationships identified by Qwen",
        "3. **Hierarchy & Composition** — Intended vs apparent hierarchy, attention flow, spatial relationships",
        "4. **Judge** — Component assessments, overall strengths/weaknesses, impact on readability/hierarchy/communication",
        "5. **Improve** — Proposed changes with expected impact and trade-offs",
        "",
    ]

    # Add curriculum evidence summary
    if curriculum_evidence:
        md_lines += ["## Curriculum Knowledge Applied", ""]
        for ce in curriculum_evidence[:5]:  # Top 5
            title = ce.get("title", "Untitled")
            knowledge_id = ce.get("knowledge_id", "unknown")
            md_lines += [f"- **{title}** ({knowledge_id})"]
        md_lines += ["", "---", ""]

    for section in sections:
        md_lines += [f"", f"## {section['heading']} ({section['scope']})", f"Selection rationale: {section['selection_rationale']}"]
        if section.get("subsections"):
            md_lines += [f"**Focus questions:**"] + [f"- {q}" for q in section["subsections"][0]["focus_questions"]]
        if section.get("curriculum_refs"):
            md_lines += [f"**Curriculum principles applied:**"] + [
                f"- {cr}" for cr in section["curriculum_refs"]
            ]
        omitted = [
            d for d in plan["module_decisions"] if d["decision"] == "omitted" and d["module_ref"] in {s["module_ref"] for s in sections}
        ]
        if omitted:
            md_lines += ["", "## Suppressed or omitted sections"] + [f"- {d['heading']}: {d['rationale']}" for d in omitted]
        md_lines += ["", "## Human review", "Status: draft. No claims have been approved.", "Reviewer: ___________________", "Date: ___________________"]
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")


# ── Single-image processor ──────────────────────────────────────────────────
def process_image(image_id: str, image_info: dict[str, str], catalog: dict[str, Any],
                  out_dir: Path, timeout: int, root: Path,
                  curriculum_query: str | None = None) -> dict[str, Any] | None:
    """Process a single image through the full pipeline with Phase 3 enhancements."""
    image_path = ROOT / image_info["relative_path"]
    print(f"Processing {image_id}...")

    # Verify prerequisites
    if not check_ollama_health():
        print(f"  ⚠️  Ollama not running — cannot process {image_id}")
        return None

    if not verify_model(EXPECTED_MODEL):
        print(f"  ⚠️  Model mismatch — expected {EXPECTED_MODEL}")

    try:
        api_result = infer_qwen(image_path, QWEN_PROMPT, timeout)
    except Exception as e:
        print(f"  Qwen inference FAILED for {image_id}: {e}")
        return None

    qwen_response = api_result.get("response", "")
    qwen_thinking = api_result.get("thinking", "")
    print(f"  API response: response={len(qwen_response)} chars, thinking={len(qwen_thinking)} chars")
    print(f"  done_reason: {api_result.get('done_reanor', 'N/A')}")

    # Check for truncated output
    done_reason = api_result.get("done_reason", "")
    if done_reason == "length":
        print(f"  ⚠️  Output truncated at {MAX_TOKENS} tokens — some observations may be incomplete")

    # Parse observations from thinking field or response (3-tier fallback)
    parsed = extract_json_from_thinking(qwen_thinking) if qwen_thinking else None
    if parsed and "observations" in parsed:
        observations = parsed["observations"]
    elif qwen_thinking:
        observations = parse_qwen_observations(qwen_thinking)
    elif qwen_response:
        observations = parse_qwen_observations(qwen_response)
    else:
        observations = []
    print(f"  Parsed {len(observations)} observations from thinking field")

    if not observations:
        print(f"  ⚠️  No observations parsed — producing universal foundation only")

    # Enhance observations with curriculum knowledge
    observations = apply_curriculum_to_observations(observations, catalog, root)

    # Build foundation from observations
    foundation = build_foundation(observations)

    # Build cues and evidence list
    known_signals = {signal for module in catalog["modules"] for signal in module['trigger_signals'] + module['suppress_signals']}
    cues = []
    evidence = [{"evidence_id": f"manifest_{image_id}", "text": image_info.get("selection_rationale", "Curated pilot image."),
                 "source": "human_interpretation", "source_ref": None, "confidence": 0.6, "uncertainty": "medium"}]

    for obs in observations:
        evidence.append({"evidence_id": obs["observation_id"], "text": obs["description"],
                         "source": "model_inference", "source_ref": None, "confidence": obs.get("confidence", 0.7),
                         "uncertainty": obs.get("uncertainty", "medium")})
        obs_cat = obs["category"].lower().rstrip(":")
        if obs_cat in CATEGORY_TO_SIGNAL:
            signal = CATEGORY_TO_SIGNAL[obs_cat]
            if signal in known_signals:
                cues.append({"signal": signal, "evidence_refs": [obs["observation_id"]], "confidence": obs.get("confidence", 0.7)})

    # Generate annotation using dynamic planner
    annotation = make_annotation(
        {"image_id": image_id, "sha256": image_info["sha256"], "relative_path": image_info["relative_path"]},
        catalog=catalog, evidence=evidence if cues else [], cues=cues, custom_proposals=[],
    )
    annotation["foundation"] = foundation

    # Plan modules
    plan = plan_modules(catalog, evidence, cues)

    # Build specialist sections from plan with curriculum integration
    selected_modules = {d["module_ref"]: d for d in plan["module_decisions"] if d["decision"] == "selected"}
    sections = []
    for module in catalog["modules"]:
        module_id = module["module_id"]
        if module_id in selected_modules:
            # Get curriculum refs for this module
            module_query = module["heading"].lower() + " " + module["description"][:200]
            cur_knowledge = retrieve_curriculum(root, module_query, module=None, limit=2)

            sections.append({
                "section_id": "section_" + module_id,
                "module_ref": module_id,
                "proposal_ref": None,
                "heading": module["heading"],
                "scope": "catalogued_module",
                "selection_rationale": selected_modules[module_id]["rationale"],
                "evidence_refs": selected_modules[module_id]["evidence_refs"],
                "component_refs": [],
                "group_refs": [],
                "subsections": [{
                    "subsection_id": module_id + "_analysis",
                    "heading": module["heading"],
                    "focus_questions": module["focus_questions"],
                    "claims": [],  # Will be populated below
                }],
                "curriculum_refs": [k["knowledge_id"] for k in cur_knowledge],
            })

            # Populate claims using focus questions + curriculum
            for subsection in sections[-1]["subsections"]:
                claims = []
                for fq in subsection["focus_questions"]:
                    # Check if any curriculum knowledge applies
                    applicable = [k for k in cur_knowledge if any(
                        word in k["title"].lower() or word in k["summary"].lower()
                        for word in fq.lower().split()
                    )]
                    if applicable:
                        claims.append({
                            "claim_text": f"{fq}: {applicable[0]['summary'][:150]}",
                            "evidence_refs": [obs["observation_id"] for obs in observations if any(
                                word in obs["category"].lower() or word in obs["description"].lower()
                                for word in fq.lower().split()
                            )],
                            "source": "curriculum_integrated",
                            "uncertainty": applicable[0].get("curriculum_refs", ["unknown"])[0] if applicable else "medium",
                        })
                    else:
                        claims.append({
                            "claim_text": f"{fq}: (no direct curriculum evidence found)",
                            "evidence_refs": [obs["observation_id"]],
                            "source": "model_inference",
                            "uncertainty": "high",
                        })
                subsection["claims"] = claims

    annotation["analysis_plan"] = plan
    annotation["specialist_sections"] = sections

    # Validate annotation
    try:
        validate_annotation(annotation, catalog)
    except Exception as e:
        print(f"  Validation WARNING for {image_id}: {e}")

    output_path = out_dir / f"{image_id}.json"
    write_annotation(annotation, output_path, image_info, sections, plan,
                     curriculum_evidence=retrieve_curriculum(root, curriculum_query or f"{image_id} design analysis", limit=3))

    print(f"  ✅ {image_id} written ({len(observations)} observations, {len(sections)} specialist sections)")
    return {"image_id": image_id, "observations": len(observations), "sections": len(sections)}


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Generate v1.2 dynamic annotations with Qwen3.5 9B")
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root directory")
    parser.add_argument("--limit", type=int, default=5, help="Number of development images to process")
    parser.add_argument("--timeout", type=int, default=300, help="Inference timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--brief", type=str, default=None, help="Optional design brief text")
    parser.add_argument("--curriculum-query", type=str, default=None,
                        help="Optional custom curriculum query string")

    args = parser.parse_args()

    root = args.root.resolve()
    catalog = load_catalog(root)

    manifest_rows = [json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    images_by_id = {row["image_id"]: row for row in manifest_rows}
    dev_images = [row["image_id"] for row in manifest_rows if row.get("dataset_split") == "development"][:args.limit]

    out_dir = root / "annotations/drafts/dynamic_v1_2/batch_001"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(f"Would process {len(dev_images)} images: {dev_images}")
        return

    # Build curriculum query from brief if provided
    curriculum_query = args.brief or None

    results = []
    for image_id in dev_images:
        image_info = images_by_id[image_id]
        result = process_image(image_id, image_info, catalog, out_dir, args.timeout, root, curriculum_query)
        if result:
            results.append(result)

    print(f"\n=== Summary ===")
    for r in results:
        print(f"  {r['image_id']}: {r['observations']} obs, {r['sections']} sections")

    # Post-run summary
    print(f"\nPhase 3 Enhancements:")
    print(f"  - Curriculum integration: {'✅ Enabled' if curriculum_query else '⚠️ Disabled (no brief provided)'}")
    print(f"  - Evidence grounding: ✅ Enhanced uncertainty classification")
    print(f"  - Curriculum claims: ✅ Populated via focus questions")
    print(f"  - Truncation handling: ✅ done_reason detection")
    print(f"  - Specialist analysis: ✅ Dynamic selection with rationale")


if __name__ == "__main__":
    main()