"""Contains evaluator — 1.0 iff ``expected`` is a substring of ``output``."""

from app.evaluation.base import Evaluator, Score


class ContainsEvaluator(Evaluator):
    """Awards 1.0 when ``expected`` appears anywhere inside ``output``, 0.0 otherwise.

    Comparison is case-sensitive by design.  Callers that want case-insensitive
    substring matching should lower-case both strings before passing them in.

    Edge case: an empty ``expected`` string is always found in any ``output``
    (this is standard Python ``in`` semantics — ``"" in "anything"`` is
    ``True``).  This is intentional and documented rather than special-cased,
    because silently raising or returning 0.0 would be a bigger surprise.
    """

    async def score(self, *, input: str, output: str, expected: str) -> Score:
        if expected in output:
            return Score(name="contains", value=1.0, rationale=None)
        return Score(
            name="contains",
            value=0.0,
            rationale=f"expected {expected!r} not found in output",
        )
