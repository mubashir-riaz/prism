"""Exact-match evaluator — 1.0 iff output equals expected character-for-character."""

from app.evaluation.base import Evaluator, Score


class ExactMatchEvaluator(Evaluator):
    """Awards 1.0 when ``output`` is identical to ``expected``, 0.0 otherwise.

    Comparison is case-sensitive and whitespace-sensitive by design.
    Callers that want case-insensitive matching should normalise both strings
    before passing them in, or use a different evaluator.
    """

    async def score(self, *, input: str, output: str, expected: str) -> Score:
        if output == expected:
            return Score(name="exact_match", value=1.0, rationale=None)
        return Score(
            name="exact_match",
            value=0.0,
            rationale=f"expected {expected!r}, got {output!r}",
        )
