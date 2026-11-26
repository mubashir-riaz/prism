"""
Unit tests for app/evaluation/registry.py.

Covers: build_evaluator, UnknownEvaluatorError, run_evaluators,
        weighted_average, and determinism guarantees.
"""

import pytest

from app.evaluation.base import Score
from app.evaluation.heuristics.contains import ContainsEvaluator
from app.evaluation.heuristics.exact_match import ExactMatchEvaluator
from app.evaluation.heuristics.length_bounds import LengthBoundsEvaluator
from app.evaluation.registry import (
    UnknownEvaluatorError,
    build_evaluator,
    run_evaluators,
    weighted_average,
)


# ===========================================================================
# build_evaluator
# ===========================================================================


class TestBuildEvaluator:
    def test_exact_match_returns_exact_match_evaluator(self):
        ev = build_evaluator("exact_match")
        assert isinstance(ev, ExactMatchEvaluator)

    def test_contains_returns_contains_evaluator(self):
        ev = build_evaluator("contains")
        assert isinstance(ev, ContainsEvaluator)

    def test_length_bounds_returns_length_bounds_evaluator(self):
        ev = build_evaluator("length_bounds")
        assert isinstance(ev, LengthBoundsEvaluator)

    def test_unknown_name_raises_unknown_evaluator_error(self):
        with pytest.raises(UnknownEvaluatorError) as exc_info:
            build_evaluator("nonexistent_evaluator")
        assert exc_info.value.name == "nonexistent_evaluator"

    def test_unknown_error_message_contains_the_name(self):
        with pytest.raises(UnknownEvaluatorError) as exc_info:
            build_evaluator("my_missing_grader")
        assert "my_missing_grader" in str(exc_info.value)

    def test_params_are_forwarded_to_constructor(self):
        ev = build_evaluator("length_bounds", {"min_len": 10, "max_len": 20})
        assert isinstance(ev, LengthBoundsEvaluator)
        assert ev.min_len == 10
        assert ev.max_len == 20

    def test_none_params_treated_as_empty_dict(self):
        """build_evaluator(..., None) must not raise — treated as no params."""
        ev = build_evaluator("length_bounds", None)
        assert isinstance(ev, LengthBoundsEvaluator)
        # Defaults must be intact
        assert ev.min_len == 1
        assert ev.max_len == 2000

    def test_each_call_returns_a_new_instance(self):
        """Registry must not cache instances — callers get fresh objects."""
        ev1 = build_evaluator("exact_match")
        ev2 = build_evaluator("exact_match")
        assert ev1 is not ev2


# ===========================================================================
# run_evaluators
# ===========================================================================


class TestRunEvaluators:
    # --- Happy path ---

    @pytest.mark.asyncio
    async def test_three_configs_return_three_scores_in_order(self):
        configs = [
            {"name": "exact_match"},
            {"name": "contains"},
            {"name": "length_bounds"},
        ]
        scores = await run_evaluators(
            configs,
            input="What is 2+2?",
            output="4",
            expected="4",
        )
        assert len(scores) == 3
        # Order must match config order
        assert scores[0].name == "exact_match"
        assert scores[1].name == "contains"
        assert scores[2].name == "length_bounds"

    @pytest.mark.asyncio
    async def test_all_scores_are_score_instances(self):
        configs = [{"name": "exact_match"}, {"name": "contains"}]
        scores = await run_evaluators(
            configs, input="q", output="hello", expected="hello"
        )
        assert all(isinstance(s, Score) for s in scores)

    @pytest.mark.asyncio
    async def test_params_forwarded_through_run_evaluators(self):
        """Params in config must reach the evaluator constructor."""
        configs = [{"name": "length_bounds", "params": {"min_len": 10, "max_len": 20}}]
        # output of length 15 should pass custom bounds → 1.0
        scores = await run_evaluators(
            configs, input="q", output="a" * 15, expected=""
        )
        assert scores[0].value == 1.0

    # --- Error path ---

    @pytest.mark.asyncio
    async def test_unknown_evaluator_name_raises_before_any_scoring(self):
        """UnknownEvaluatorError must be raised at build time, not after partial scoring."""
        configs = [
            {"name": "exact_match"},
            {"name": "totally_unknown"},
        ]
        with pytest.raises(UnknownEvaluatorError) as exc_info:
            await run_evaluators(configs, input="q", output="a", expected="a")
        assert exc_info.value.name == "totally_unknown"

    # --- Determinism ---

    @pytest.mark.asyncio
    async def test_determinism_identical_results_across_runs(self):
        configs = [
            {"name": "exact_match"},
            {"name": "contains"},
            {"name": "length_bounds"},
        ]
        kwargs = {"input": "question", "output": "answer", "expected": "answer"}

        results = [await run_evaluators(configs, **kwargs) for _ in range(3)]

        # Every run must produce the same list of Scores
        for run in results[1:]:
            assert len(run) == len(results[0])
            for s_a, s_b in zip(run, results[0]):
                assert s_a == s_b


# ===========================================================================
# weighted_average
# ===========================================================================


def _score(value: float) -> Score:
    """Convenience constructor for Score objects in weighted_average tests."""
    return Score(name="test", value=value)


class TestWeightedAverage:
    def test_equal_weights_all_ones_average(self):
        """[1.0, 0.0, 1.0] with weights [1, 1, 1] → 2/3 ≈ 0.666…"""
        scores = [_score(1.0), _score(0.0), _score(1.0)]
        result = weighted_average(scores, [1.0, 1.0, 1.0])
        assert result == pytest.approx(2 / 3, rel=1e-6)

    def test_unequal_weights_shift_result(self):
        """[1.0, 0.0] with weights [2, 1] → (1*2 + 0*1) / 3 = 2/3 ≈ 0.666…"""
        scores = [_score(1.0), _score(0.0)]
        result = weighted_average(scores, [2.0, 1.0])
        assert result == pytest.approx(2 / 3, rel=1e-6)

    def test_all_weights_zero_returns_zero(self):
        """Zero total weight must return 0.0, not raise ZeroDivisionError."""
        scores = [_score(1.0), _score(0.5)]
        result = weighted_average(scores, [0.0, 0.0])
        assert result == 0.0

    def test_single_score_weight_one_returns_its_value(self):
        scores = [_score(0.75)]
        result = weighted_average(scores, [1.0])
        assert result == pytest.approx(0.75)

    def test_all_perfect_scores_returns_one(self):
        scores = [_score(1.0), _score(1.0), _score(1.0)]
        result = weighted_average(scores, [1.0, 2.0, 3.0])
        assert result == pytest.approx(1.0)

    def test_all_zero_scores_returns_zero(self):
        scores = [_score(0.0), _score(0.0)]
        result = weighted_average(scores, [1.0, 5.0])
        assert result == pytest.approx(0.0)

    def test_high_weight_on_low_score_pulls_average_down(self):
        """weight=10 on 0.0 vs weight=1 on 1.0 → 1/11 ≈ 0.0909…"""
        scores = [_score(1.0), _score(0.0)]
        result = weighted_average(scores, [1.0, 10.0])
        assert result == pytest.approx(1 / 11, rel=1e-6)
