"""
Unit tests for app/evaluation/base.py — Score and Evaluator.
"""

import pytest
from dataclasses import FrozenInstanceError

from app.evaluation.base import Evaluator, Score


# ---------------------------------------------------------------------------
# Score tests
# ---------------------------------------------------------------------------


def test_score_is_frozen_raises_on_attribute_assignment():
    """Score is a frozen dataclass — any field assignment must raise FrozenInstanceError."""
    s = Score(name="exact_match", value=1.0)

    with pytest.raises(FrozenInstanceError):
        s.value = 0.5  # type: ignore[misc]


def test_score_is_frozen_raises_on_name_assignment():
    """Mutation of any field — including ``name`` — must be blocked."""
    s = Score(name="exact_match", value=1.0)

    with pytest.raises(FrozenInstanceError):
        s.name = "contains"  # type: ignore[misc]


def test_score_is_frozen_raises_on_rationale_assignment():
    """Setting ``rationale`` after construction must also raise FrozenInstanceError."""
    s = Score(name="exact_match", value=1.0, rationale=None)

    with pytest.raises(FrozenInstanceError):
        s.rationale = "looks good"  # type: ignore[misc]


def test_score_stores_fields_correctly():
    """Constructor fields must be readable and correctly stored."""
    s = Score(name="contains", value=0.75, rationale="keyword found")

    assert s.name == "contains"
    assert s.value == 0.75
    assert s.rationale == "keyword found"


def test_score_rationale_defaults_to_none():
    """``rationale`` must default to ``None`` when not supplied."""
    s = Score(name="exact_match", value=1.0)

    assert s.rationale is None


# ---------------------------------------------------------------------------
# Evaluator tests
# ---------------------------------------------------------------------------


def test_evaluator_cannot_be_instantiated_directly():
    """Evaluator is abstract — direct instantiation must raise TypeError."""
    with pytest.raises(TypeError):
        Evaluator()  # type: ignore[abstract]


def test_evaluator_subclass_without_score_cannot_be_instantiated():
    """A subclass that does not implement ``score`` must still raise TypeError."""

    class IncompleteEvaluator(Evaluator):
        pass  # score() not implemented

    with pytest.raises(TypeError):
        IncompleteEvaluator()


@pytest.mark.asyncio
async def test_evaluator_concrete_subclass_can_be_instantiated_and_called():
    """A fully implemented subclass must be instantiable and its score() awaitable."""

    class AlwaysPerfect(Evaluator):
        async def score(self, *, input: str, output: str, expected: str) -> Score:
            return Score(name="always_perfect", value=1.0)

    grader = AlwaysPerfect()
    result = await grader.score(input="q", output="a", expected="a")

    assert isinstance(result, Score)
    assert result.value == 1.0
    assert result.name == "always_perfect"
