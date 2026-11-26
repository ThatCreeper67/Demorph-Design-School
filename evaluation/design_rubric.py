"""Design intelligence scores with explicit human-reference and method fields."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


DIMENSIONS = [
    "visual_understanding", "component_identification", "functional_role_classification",
    "hierarchy_understanding", "spatial_reasoning", "typography_understanding",
    "colour_understanding", "design_principle_understanding", "communication_evaluation",
    "design_critique", "evidence_and_uncertainty_handling",
]


def require_approved_reference(annotation: dict[str, Any]) -> None:
    if annotation.get("human_review", {}).get("status") != "approved":
        raise ValueError("Only human-approved annotations may be used as evaluation references")


def f1_counts(reference: Iterable[str], prediction: Iterable[str]) -> dict[str, float | int]:
    ref, pred = Counter(reference), Counter(prediction)
    true_positive = sum((ref & pred).values())
    ref_count, pred_count = sum(ref.values()), sum(pred.values())
    precision = true_positive / pred_count if pred_count else (1.0 if not ref_count else 0.0)
    recall = true_positive / ref_count if ref_count else (1.0 if not pred_count else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"true_positive": true_positive, "reference_count": ref_count, "prediction_count": pred_count,
            "precision": precision, "recall": recall, "f1": f1}


def _ranks(values: list[str]) -> dict[str, float]:
    return {value: float(index + 1) for index, value in enumerate(values)}


def spearman_order(reference_order: list[str], prediction_order: list[str]) -> float | None:
    common = [value for value in reference_order if value in set(prediction_order)]
    if len(common) < 2:
        return None
    ref, pred = _ranks(reference_order), _ranks(prediction_order)
    xs, ys = [ref[x] for x in common], [pred[x] for x in common]
    xbar, ybar = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x-xbar)*(y-ybar) for x,y in zip(xs,ys))
    denominator = (sum((x-xbar)**2 for x in xs) * sum((y-ybar)**2 for y in ys)) ** 0.5
    return numerator / denominator if denominator else None


def score_record(*, dimension: str, reference_annotation: dict[str, Any], prediction: Any,
                 method: str, score: float | None, explanation: str, error_category: str | None = None) -> dict[str, Any]:
    return {"dimension": dimension, "reference_annotation": reference_annotation, "prediction": prediction,
            "evaluation_method": method, "score": score, "explanation": explanation,
            "error_category": error_category}


def score_element_types(reference: dict[str, Any], predicted_types: list[str], prediction: Any) -> dict[str, Any]:
    require_approved_reference(reference)
    metric = f1_counts((item["element_type"] for item in reference["elements"]), predicted_types)
    return score_record(dimension="visual_understanding", reference_annotation=reference, prediction=prediction,
                        method="multiset precision/recall/F1 by reviewed element type", score=metric["f1"],
                        explanation=json_metric(metric), error_category=None if metric["f1"] == 1 else "incorrect_element_identification")


def score_roles(reference: dict[str, Any], predicted_roles: dict[str, str], prediction: Any) -> dict[str, Any]:
    require_approved_reference(reference)
    expected = {item["element_id"]: item["primary_role"] for item in reference["roles"]}
    if not expected:
        return score_record(dimension="functional_role_classification", reference_annotation=reference, prediction=prediction,
                            method="exact primary-role accuracy", score=None, explanation="No reviewed role references exist.", error_category=None)
    correct = sum(predicted_roles.get(key) == value for key,value in expected.items())
    score = correct / len(expected)
    return score_record(dimension="functional_role_classification", reference_annotation=reference, prediction=prediction,
                        method="exact primary-role accuracy", score=score,
                        explanation=f"{correct}/{len(expected)} reviewed roles matched.", error_category=None if score == 1 else "incorrect_component_role")


def score_hierarchy(reference: dict[str, Any], predicted_order: list[str], prediction: Any) -> dict[str, Any]:
    require_approved_reference(reference)
    hierarchy = [item for item in reference["hierarchy"] if item["kind"] == "apparent_attention_prediction"]
    reference_order = [item["element_id"] for item in sorted(hierarchy, key=lambda item: (item["reading_order"] or 10**9, item["element_id"]))]
    score = spearman_order(reference_order, predicted_order)
    return score_record(dimension="hierarchy_understanding", reference_annotation=reference, prediction=prediction,
                        method="Spearman rank correlation on apparent hierarchy", score=score,
                        explanation="Insufficient common reviewed components." if score is None else f"Rank correlation across {len(set(reference_order) & set(predicted_order))} common components.",
                        error_category=None if score in (None, 1.0) else "incorrect_hierarchy")


def json_metric(metric: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value:.3f}" if isinstance(value, float) else f"{key}={value}" for key,value in metric.items())
