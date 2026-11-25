"""
Unit tests for the three heuristic evaluators.

All evaluators are deterministic and pure — no mocking required.
"""

import pytest

from app.evaluation.base import Score
from app.evaluation.heuristics.contains import ContainsEvaluator
from app.evaluation.heuristics.exact_match import ExactMatchEvaluator
from app.evaluation.heuristics.length_bounds import LengthBoundsEvaluator


# ===========================================================================
# ExactMatchEvaluator
# ===========================================================================


class TestExactMatchEvaluator:
    @pytest.fixture
    def grader(self) -> ExactMatchEvaluator:
        return ExactMatchEvaluator()

    @pytest.mark.asyncio
    async def test_exact_match_returns_1(self, grader):
        s = await grader.score(input="q", output="Paris", expected="Paris")
        assert s.value == 1.0
        assert s.name == "exact_match"
        # On a hit, rationale must be None
        assert s.rationale is None

    @pytest.mark.asyncio
    async def test_different_output_returns_0(self, grader):
        s = await grader.score(input="q", output="London", expected="Paris")
        assert s.value == 0.0
        assert s.rationale is not None and len(s.rationale) > 0

    @pytest.mark.asyncio
    async def test_case_different_returns_0(self, grader):
        # Case-sensitive by design — "paris" != "Paris"
        s = await grader.score(input="q", output="paris", expected="Paris")
        assert s.value == 0.0

    @pytest.mark.asyncio
    async def test_empty_equals_empty_returns_1(self, grader):
        s = await grader.score(input="q", output="", expected="")
        assert s.value == 1.0

    @pytest.mark.asyncio
    async def test_rationale_contains_expected_and_got_on_miss(self, grader):
        s = await grader.score(input="q", output="London", expected="Paris")
        assert "Paris" in s.rationale
        assert "London" in s.rationale

    @pytest.mark.asyncio
    async def test_determinism(self, grader):
        """Same input → identical Score on every call."""
        scores = [
            await grader.score(input="q", output="X", expected="Y")
            for _ in range(5)
        ]
        assert all(s == scores[0] for s in scores)


# ===========================================================================
# ContainsEvaluator
# ===========================================================================


class TestContainsEvaluator:
    @pytest.fixture
    def grader(self) -> ContainsEvaluator:
        return ContainsEvaluator()

    @pytest.mark.asyncio
    async def test_substring_present_returns_1(self, grader):
        s = await grader.score(
            input="q",
            output="The capital of France is Paris.",
            expected="Paris",
        )
        assert s.value == 1.0
        assert s.name == "contains"
        assert s.rationale is None

    @pytest.mark.asyncio
    async def test_substring_absent_returns_0(self, grader):
        s = await grader.score(
            input="q",
            output="The capital of France is Lyon.",
            expected="Paris",
        )
        assert s.value == 0.0
        assert s.rationale is not None

    @pytest.mark.asyncio
    async def test_case_different_returns_0(self, grader):
        # Case-sensitive: "A" is NOT in "abc"
        s = await grader.score(input="q", output="abc", expected="A")
        assert s.value == 0.0

    @pytest.mark.asyncio
    async def test_empty_expected_in_any_output_returns_1(self, grader):
        # Python semantics: "" in "anything" is True.
        # Documented quirk — not special-cased.
        s = await grader.score(input="q", output="anything", expected="")
        assert s.value == 1.0

    @pytest.mark.asyncio
    async def test_rationale_mentions_expected_on_miss(self, grader):
        s = await grader.score(input="q", output="no match here", expected="Paris")
        assert "Paris" in s.rationale

    @pytest.mark.asyncio
    async def test_determinism(self, grader):
        """Same input → identical Score on every call."""
        scores = [
            await grader.score(input="q", output="hello world", expected="world")
            for _ in range(5)
        ]
        assert all(s == scores[0] for s in scores)


# ===========================================================================
# LengthBoundsEvaluator
# ===========================================================================


class TestLengthBoundsEvaluator:
    @pytest.fixture
    def grader(self) -> LengthBoundsEvaluator:
        return LengthBoundsEvaluator()  # defaults: min=1, max=2000

    @pytest.mark.asyncio
    async def test_length_5_within_defaults_returns_1(self, grader):
        s = await grader.score(input="q", output="hello", expected="")
        assert s.value == 1.0
        assert s.name == "length_bounds"
        assert s.rationale is None

    @pytest.mark.asyncio
    async def test_length_0_below_default_min_returns_0(self, grader):
        s = await grader.score(input="q", output="", expected="")
        assert s.value == 0.0

    @pytest.mark.asyncio
    async def test_length_3000_above_default_max_returns_0(self, grader):
        s = await grader.score(input="q", output="x" * 3000, expected="")
        assert s.value == 0.0

    @pytest.mark.asyncio
    async def test_custom_bounds_within_range_returns_1(self):
        grader = LengthBoundsEvaluator(min_len=10, max_len=20)
        s = await grader.score(input="q", output="a" * 15, expected="")
        assert s.value == 1.0

    @pytest.mark.asyncio
    async def test_custom_bounds_below_min_returns_0(self):
        grader = LengthBoundsEvaluator(min_len=10, max_len=20)
        s = await grader.score(input="q", output="hello", expected="")  # len 5
        assert s.value == 0.0

    @pytest.mark.asyncio
    async def test_custom_bounds_above_max_returns_0(self):
        grader = LengthBoundsEvaluator(min_len=10, max_len=20)
        s = await grader.score(input="q", output="a" * 25, expected="")
        assert s.value == 0.0

    @pytest.mark.asyncio
    async def test_rationale_includes_actual_length_and_range_on_miss(self, grader):
        s = await grader.score(input="q", output="", expected="")
        assert "0" in s.rationale       # actual length
        assert "1" in s.rationale       # min_len
        assert "2000" in s.rationale    # max_len

    @pytest.mark.asyncio
    async def test_boundary_min_inclusive_returns_1(self):
        grader = LengthBoundsEvaluator(min_len=5, max_len=10)
        s = await grader.score(input="q", output="a" * 5, expected="")
        assert s.value == 1.0

    @pytest.mark.asyncio
    async def test_boundary_max_inclusive_returns_1(self):
        grader = LengthBoundsEvaluator(min_len=5, max_len=10)
        s = await grader.score(input="q", output="a" * 10, expected="")
        assert s.value == 1.0

    @pytest.mark.asyncio
    async def test_determinism(self, grader):
        """Same input → identical Score on every call."""
        scores = [
            await grader.score(input="q", output="hello", expected="")
            for _ in range(5)
        ]
        assert all(s == scores[0] for s in scores)
