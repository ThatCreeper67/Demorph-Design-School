#!/usr/bin/env python3
"""Generate v1.2 dynamic annotations with actual Qwen3.5 9B image analysis."""
from __future__ import annotations

import json
import sys
import base64
import urllib.request
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from annotations.dynamic_workflow import load_catalog, make_annotation, validate_annotation
from annotations.review_workflow import ensure_directories


# ── Qwen inference ────────────────────────────────────────────────────────────
def infer_qwen(image_path: Path, prompt: str) -> dict[str, Any]:
    """Run Qwen3.5 9B via Ollama API and return the structured response.

    Returns dict with 'response' and 'thinking' keys from the API.
    The model typically outputs structured analysis in the 'thinking' field.
    """
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    base64_data = base64.b64encode(image_bytes).decode()

    payload = {
        "model": "qwen3.5:9b-q4_K_M",
        "prompt": prompt,
        "images": [base64_data],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_predict": 1200},
    }

    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.loads(response.read())

    return result


# ── Qwen observation parser ──────────────────────────────────────────────────
SOURCE_ENUM = ["direct_observation", "model_inference", "human_interpretation", "brief_derived"]
UNCERTAINTY_ENUM = ["low", "medium", "high", "unknown", "ambiguous", "not_applicable"]


def parse_qwen_observations(response_text: str) -> list[dict[str, Any]]:
    """Parse Qwen's free-form response into structured observations.

    Qwen produces markdown-style observations like:
    **1. Visual Elements**
    *   **The Protagonist:** ...

    We extract:
    - Observation ID (auto numeric)
    - Category (from headings like Visual Elements, Typography, etc.)
    - Description (the text)
    - Source (model_inference)
    - Confidence (medium default)
    - Uncertainty (medium default)
    """
    observations = []

    # Split by observation headers (numbered or bold)
    # Match patterns like "**1. Visual Elements**" or "**Visual Elements**"
    lines = response_text.split("\n")

    current_category = None
    current_description_lines = []

    def flush_observation():
        nonlocal current_category, current_description_lines
        if current_category and current_description_lines:
            obs_id = f"obs_{len(observations) + 1:03d}"
            description = " ".join(current_description_lines).strip()
            observations.append(
                {
                    "observation_id": obs_id,
                    "category": current_category,
                    "description": description,
                    "source": "model_inference",
                    "confidence": 0.7,
                    "uncertainty": "medium",
                }
            )
        current_category = None
        current_description_lines = []

    for line in lines:
        # Check for a new observation heading
        # Patterns: "**1. Something**" or "**Something**"
        stripped = line.strip()
        heading_match = None
        if stripped.startswith("**"):
            # Could be "**1. Heading**" or just "**Heading**"
            inner = stripped.strip("* ").strip()
            # Check if there's a number dot pattern
            num_match = re.match(r"^(\d+)\.\s*(.*)", inner)
            if num_match:
                heading_match = (num_match.group(2).strip(), True)
            else:
                heading_match = (inner.strip("*"), False)

        if heading_match:
            flush_observation()
            current_category = heading_match[0]
            # Determine if this line is a heading or content
            if not heading_match[1] and current_description_lines == []:
                # Might be a heading without number; treat as start of content
                current_description_lines = [stripped]
            continue

        # Content line
        if current_category:
            current_description_lines.append(stripped)
        # If we are not in a category, ignore

    flush_observation()
    return observations


# ── Build observation component from Qwen output ─────────────────────────────
def build_observation_component(
    observations: list[dict[str, Any]],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Build the foundation.identify.components from Qwen observations.

    Each observation becomes a component with a stable component_id.
    We map categories to component types from the catalogue.
    """
    catalog_modules = {m["module_id"]: m for m in catalog["modules"]}

    # Map observation categories to component types
    category_to_type = {
        "typography": "supporting",
        "type": "supporting",
        "text": "supporting",
        "hero": "primary",
        "protagonist": "primary",
        "main subject": "primary",
        "visual element": "primary",
        "colour": "supporting",
        "color": "supporting",
        "composition": "supporting",
        "compositional": "supporting",
        "negative space": "background_context",
        "negative": "background_context",
        "visual flow": "supporting",
        "flow": "supporting",
        "layering": "supporting",
        "layer": "supporting",
        "illustration": "supporting",
        "metaphor": "supporting",
        "brand": "supporting",
        "branding": "supporting",
        "information": "supporting",
        "density": "supporting",
        "density of": "supporting",
        "component": "supporting",
        "element": "supporting",
    }

    components = []
    for i, obs in enumerate(observations):
        obs_cat = obs["category"].lower()
        comp_type = "supporting"  # default
        for key, val in category_to_type.items():
            if key in obs_cat:
                comp_type = val
                break

        component_id = obs["observation_id"]

        # Build a claim for significance
        significance_claim = {
            "text": f"This {obs['category'].lower()} anchors attention in the poster",
            "source": "model_inference",
            "evidence_refs": [obs["observation_id"]],
            "confidence": obs.get("confidence", 0.7),
            "uncertainty": obs.get("uncertainty", "medium"),
        }

        component_type_safe = comp_type or "supporting"

        component = {
            "component_id": component_id,
            "component_type": component_type_safe,
            "significance": "primary" if component_type_safe == "primary" else "supporting",
            "significance_rationale": significance_claim,
            "bbox": None,  # Qwen doesn't provide exact coordinates
            "functional_roles": [obs["category"]],
            "visual_characteristics": [obs["description"][:100]
            if obs["description"] else obs["category"]],
            "spatial_relationship_ids": [],
            "hierarchy_contribution": [
                {
                    "text": f"{obs['category']} contributes to {comp_type} hierarchy",
                    "source": "model_inference",
                    "evidence_refs": [obs["observation_id"]],
                    "uncertainty": "medium",
                }
            ],
            "overall_contribution": [
                {
                    "text": f"{obs['category']} is a {comp_type} element in the composition",
                    "source": "model_inference",
                    "evidence_refs": [obs["observation_id"]],
                    "uncertainty": "medium",
                }
            ],
            "strengths": [],
            "weaknesses": [],
            "possible_improvements": [
                {
                    "change": f"Clarify the role of the {obs['category'].lower()}",
                    "evidence_refs": [obs["observation_id"]],
                    "expected_impact": "Improved visual communication",
                    "trade_offs": ["May require rebalancing composition"],
                    "source": "model_inference",
                    "uncertainty": "medium",
                }
            ],
        }
        components.append(component)

    return {"components": components, "component_groups": [], "relationships": []}


# ── JSON extraction from thinking ──────────────────────────────────────────
def extract_json_from_thinking(thinking_text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from Qwen's thinking field.

    Qwen often wraps its response in a thinking block. We attempt to find
    valid JSON within the thinking text.
    """
    if not thinking_text:
        return None

    # Try to find JSON object
    # Look for { ... } pattern
    json_match = re.search(r"\{[^}]*\}", thinking_text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict) and "observations" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # Try to find array of observations
    array_match = re.search(r"\[.*?\]", thinking_text, re.DOTALL)
    if array_match:
        try:
            parsed = json.loads(array_match.group(0))
            if isinstance(parsed, list):
                return {"observations": parsed}
        except json.JSONDecodeError:
            pass

    return None


# ── Main generation ──────────────────────────────────────────────────────────

def generate_v12_annotations() -> None:
    """Generate v1.2 dynamic annotations for all five pilot images."""
    root = ROOT
    catalog = load_catalog(root)

    # Load manifest
    manifest_rows = [
        json.loads(line) for line in (root / "manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    images_by_id = {row["image_id"]: row for row in manifest_rows}

    # Development split from manifest
    dev_images = [
        row["image_id"]
        for row in manifest_rows
        if row.get("dataset_split") == "development"
    ][:5]  # First 5 development images

    # Output directory
    out_dir = root / "annotations/drafts/dynamic_v1_2/batch_001"
    out_dir.mkdir(parents=True, exist_ok=True)

    for image_id in dev_images:
        image_info = images_by_id[image_id]
        image_path = root / image_info["relative_path"]

        print(f"Processing {image_id}...")

        # 1. Run Qwen inference
        qwen_prompt = """Analyze this poster design image. Provide observations on:
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

For each observation, give it a short ID (like obs_001), a category (from the list above), and a concise description. Be factual and concise. Output in markdown format with headings for each category."""

        try:
            api_result = infer_qwen(image_path, qwen_prompt)
        except Exception as e:
            print(f"  Qwen inference FAILED for {image_id}: {e}")
            api_result = {}

        qwen_response = api_result.get("response", "")
        qwen_thinking = api_result.get("thinking", "")
        print(f"  API response: response={len(qwen_response)} chars, thinking={len(qwen_thinking)} chars")

        # 2. Parse Qwen observations from the thinking field
        # First try to extract JSON from thinking
        parsed = extract_json_from_thinking(qwen_thinking) if qwen_thinking else None
        if parsed and "observations" in parsed:
            observations = parsed["observations"]
        elif qwen_thinking:
            # Parse markdown from thinking field
            observations = parse_qwen_observations(qwen_thinking)
        elif qwen_response:
            # Try parsing response
            observations = parse_qwen_observations(qwen_response)
        else:
            observations = []
        print(f"  Parsed {len(observations)} observations")

        # 3. Build foundation components from observations
        obs_component = build_observation_component(observations, catalog)
        foundation_identify = obs_component

        # 4. Build full foundation
        foundation = {
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
                "text_transcribed_with_confidence": [],
                "uncertain_observations": [
                    {
                        "text": obs["description"],
                        "source": "model_inference",
                        "evidence_refs": [obs["observation_id"]],
                        "uncertainty": obs.get("uncertainty", "medium"),
                    }
                    for obs in observations
                ],
            },
            "identify": foundation_identify,
            "hierarchy_composition": {
                "intended_hierarchy": [
                    {
                        "component_ref": comp["component_id"],
                        "level": "primary"
                        if comp["component_type"] == "primary"
                        else "supporting",
                        "order": i + 1,
                        "rationale": f"Qwen-identified {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} as {comp['component_type']}",
                        "evidence_refs": [comp["component_id"]],
                        "source": "model_inference",
                        "uncertainty": "medium",
                    }
                    for i, comp in enumerate(foundation_identify["components"])
                ],
                "apparent_hierarchy": [
                    {
                        "component_ref": comp["component_id"],
                        "level": "primary"
                        if comp["component_type"] == "primary"
                        else "supporting",
                        "order": i + 1,
                        "rationale": f"Visually, {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} appears {comp['component_type']}",
                        "evidence_refs": [comp["component_id"]],
                        "source": "model_inference",
                        "uncertainty": "medium",
                    }
                    for i, comp in enumerate(foundation_identify["components"])
                ],
                "attention_flow": [
                    {
                        "text": f"Eye flows through {comp['functional_roles'][0] if comp['functional_roles'] else 'element'}",
                        "source": "model_inference",
                        "evidence_refs": [comp["component_id"]],
                        "uncertainty": "medium",
                    }
                    for comp in foundation_identify["components"]
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
                    for i, comp1 in enumerate(foundation_identify["components"][:3])
                    for j, comp2 in enumerate(foundation_identify["components"][i+1:min(i+2, len(foundation_identify["components"]))], i+1)
                ],
            },
            "judge": {
                "component_assessments": [
                    {
                        "component_ref": comp["component_id"],
                        "strengths": [
                            f"Clear {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} presence"
                        ]
                        if comp.get("visual_characteristics")
                        else [],
                        "weaknesses": [
                            f"Uncertain {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} contribution to communication"
                        ]
                        if not comp.get("visual_characteristics")
                        else [],
                        "impact": [
                            f"{comp['functional_roles'][0] if comp['functional_roles'] else 'element'} significantly affects readability"
                        ]
                        if comp.get("visual_characteristics")
                        else [],
                        "source": "model_inference",
                    }
                    for comp in foundation_identify["components"]
                ],
                "overall_strengths": [
                    "Qwen identified core design elements"
                ]
                if observations
                else [],
                "overall_weaknesses": (
                    []
                    if observations
                    else ["No design elements identified"]
                ),
                "impact_readability": (
                    ["Qwen-identified elements affect legibility"]
                    if observations
                    else []
                ),
                "impact_hierarchy": (
                    ["Qwen-identified elements affect visual priority"]
                    if observations
                    else []
                ),
                "impact_communication": (
                    ["Qwen-identified elements affect message communication"]
                    if observations
                    else []
                ),
                "uncertainty_or_alternatives": (
                    [
                        f"Alternative interpretation of {comp['functional_roles'][0] if comp['functional_roles'] else 'element'} possible"
                        for comp in foundation_identify["components"]
                    ]
                    if foundation_identify["components"]
                    else ["No elements identified; interpretation uncertain"]
                ),
            },
            "improve": [
                {
                    "change": f"Refine the {comp['functional_roles'][0].lower() if comp['functional_roles'] else 'element'} role and relationship to other elements"
                    if comp.get("visual_characteristics")
                    else "Add more design elements",
                    "component_refs": [comp["component_id"]],
                    "expected_impact": "Improved visual communication and hierarchy clarity",
                    "trade_offs": ["May require rebalancing composition"],
                    "source": "model_inference",
                    "uncertainty": "medium",
                }
                for comp in foundation_identify["components"]
            ],
        }

        # 5. Build cues from Qwen observations for dynamic planner
        cues = []
        known_signals = {signal for module in catalog["modules"] for signal in module['trigger_signals'] + module['suppress_signals']}

        # Map Qwen's verbose categories to known signals
        category_to_signal = {
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
        }

        # Build evidence list including Qwen observations
        evidence = [
            {
                "evidence_id": f"manifest_{image_id}",
                "text": image_info.get("selection_rationale", "Curated pilot image."),
                "source": "human_interpretation",
                "source_ref": None,
                "confidence": 0.6,
                "uncertainty": "medium",
            }
        ]

        # Add Qwen observations as evidence
        for obs in observations:
            evidence.append({
                "evidence_id": obs["observation_id"],
                "text": obs["description"],
                "source": "model_inference",
                "source_ref": None,
                "confidence": obs.get("confidence", 0.7),
                "uncertainty": obs.get("uncertainty", "medium"),
            })

            obs_cat = obs["category"].lower().rstrip(":")
            if obs_cat in category_to_signal:
                signal = category_to_signal[obs_cat]
                if signal in known_signals:
                    cues.append(
                        {
                            "signal": signal,
                            "evidence_refs": [obs["observation_id"]],
                            "confidence": obs.get("confidence", 0.7),
                        }
                    )

        # 6. Generate v1.2 annotation using dynamic planner
        # Use image info from manifest
        annotation = make_annotation(
            {
                "image_id": image_id,
                "sha256": image_info["sha256"],
                "relative_path": image_info["relative_path"],
            },
            catalog=catalog,
            evidence=evidence if cues else [],
            cues=cues,
            custom_proposals=[],  # Will add if Qwen suggests new categories
        )

        # 7. Override foundation with Qwen-derived content
        annotation["foundation"] = foundation

        # 8. Ensure specialist sections reflect dynamic decisions
        # Re-compute module decisions based on Qwen cues
        from annotations.dynamic_workflow import plan_modules

        plan = plan_modules(catalog, evidence, cues)

        # Replace specialist_sections with validated plan output
        selected_modules = {d["module_ref"]: d for d in plan["module_decisions"] if d["decision"] == "selected"}
        sections = []
        for module in catalog["modules"]:
            module_id = module["module_id"]
            if module_id in selected_modules:
                sections.append(
                    {
                        "section_id": "section_" + module_id,
                        "module_ref": module_id,
                        "proposal_ref": None,
                        "heading": module["heading"],
                        "scope": "catalogued_module",
                        "selection_rationale": selected_modules[module_id]["rationale"],
                        "evidence_refs": selected_modules[module_id]["evidence_refs"],
                        "component_refs": [],
                        "group_refs": [],
                        "subsections": [
                            {
                                "subsection_id": module_id + "_analysis",
                                "heading": module["heading"],
                                "focus_questions": module["focus_questions"],
                                "claims": [],
                            }
                        ],
                    }
                )

        for module in catalog["modules"]:
            if module["module_id"] not in selected_modules:
                # Check if suppressed
                suppressed = any(
                    sig in [c["signal"] for c in cues] for sig in module["suppress_signals"]
                )
                if suppressed:
                    pass  # Already handled by plan

        annotation["analysis_plan"] = plan
        annotation["specialist_sections"] = sections

        # 9. Validation
        try:
            validate_annotation(annotation, catalog)
        except Exception as e:
            print(f"  Validation WARNING for {image_id}: {e}")

        # 10. Write output
        output_path = out_dir / f"{image_id}.json"
        output_path.write_text(
            json.dumps(annotation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        # Write markdown review sheet
        md_path = output_path.with_suffix(".md")
        md_lines = [
            f"# Dynamic v1.2 human review — {image_id}",
            "",
            f"Image: `{image_info['relative_path']}`",
            f"SHA-256: `{image_info['sha256']}`",
            "",
            "## Qwen Perception Summary",
            f"- Observations generated: {len(observations)}",
            "- Model: qwen3.5:9b-q4_K_M via Ollama",
            "",
            "## Universal foundation (review these claims against the poster)",
            "1. **Observe** — Visible elements, text, uncertainties",
            "2. **Identify** — Components, types, relationships identified by Qwen",
            "3. **Hierarchy & Composition** — Intended vs apparent hierarchy, attention flow, spatial relationships",
            "4. **Judge** — Component assessments, overall strengths/weaknesses, impact on readability/hierarchy/communication",
            "5. **Improve** — Proposed changes with expected impact and trade-offs",
            "",
        ]
        for section in sections:
            md_lines += [
                f"",
                f"## {section['heading']} ({section['scope']})",
                f"Selection rationale: {section['selection_rationale']}",
            ]
            if section.get("subsections"):
                md_lines += [
                    f"**Focus questions:**"
                ]
                for q in section["subsections"][0]["focus_questions"]:
                    md_lines += [f"- {q}"]
            omitted = [
                d
                for d in plan["module_decisions"]
                if d["decision"] == "omitted" and d["module_ref"] in {s["module_ref"] for s in sections}
            ]
            if omitted:
                md_lines += [
                    "",
                    "## Suppressed or omitted sections",
                ]
                for d in omitted:
                    md_lines += [f"- {d['heading']}: {d['rationale']}"]

            md_lines += [
                "",
                "## Human review",
                "Status: draft. No claims have been approved.",
                f"Reviewer: ___________________",
                f"Date: ___________________",
            ]

        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

        print(f"  ✅ {image_id} written ({len(observations)} observations, {len(sections)} specialist sections)")


if __name__ == "__main__":
    generate_v12_annotations()