import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from evaluation.design_rubric import f1_counts, require_approved_reference, spearman_order


def test_multiset_f1_counts_duplicates_and_errors():
    result = f1_counts(["headline", "headline", "person"], ["headline", "person", "logo"])
    assert result["true_positive"] == 2
    assert result["precision"] == pytest.approx(2/3)
    assert result["recall"] == pytest.approx(2/3)


def test_rank_correlation_for_identical_and_reversed_orders():
    assert spearman_order(["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1)
    assert spearman_order(["a", "b", "c"], ["c", "b", "a"]) == pytest.approx(-1)
    assert spearman_order(["a"], ["a"]) is None


def test_unreviewed_annotation_cannot_be_used_as_reference():
    with pytest.raises(ValueError, match="human-approved"):
        require_approved_reference({"human_review": {"status": "draft"}})


def test_approved_annotation_can_be_used_as_reference():
    require_approved_reference({"human_review": {"status": "approved"}})
