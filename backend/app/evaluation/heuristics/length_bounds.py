"""Length-bounds evaluator — 1.0 iff output length falls within [min_len, max_len]."""

from app.evaluation.base import Evaluator, Score


class LengthBoundsEvaluator(Evaluator):
    """Awards 1.0 when ``len(output)`` is within the configured bounds, 0.0 otherwise.

    Parameters
    ----------
    min_len : int
        Minimum acceptable character count (inclusive).  Default: 1.
    max_len : int
        Maximum acceptable character count (inclusive).  Default: 2000.

    Notes
    -----
    ``expected`` and ``input`` are accepted for interface consistency but are
    not used — this evaluator grades only on the length of the model's output.
    """

    def __init__(self, min_len: int = 1, max_len: int = 2000) -> None:
        self.min_len = min_len
        self.max_len = max_len

    async def score(self, *, input: str, output: str, expected: str) -> Score:
        actual_len = len(output)
        if self.min_len <= actual_len <= self.max_len:
            return Score(name="length_bounds", value=1.0, rationale=None)
        return Score(
            name="length_bounds",
            value=0.0,
            rationale=(
                f"output length {actual_len} is outside allowed range "
                f"[{self.min_len}, {self.max_len}]"
            ),
        )
