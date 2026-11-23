"""Base abstractions for the Prism evaluator framework.

Design notes
------------
Score
    A frozen dataclass — once a grader returns a score it cannot be mutated
    downstream.  ``value`` must be in [0.0, 1.0]; enforcement is the
    responsibility of each concrete Evaluator (not asserted here so the base
    stays dependency-free and fast).

Evaluator
    Abstract base class with a single async ``score()`` method.  All three
    parameters are keyword-only (``*``) to prevent accidental positional
    misuse and to make every call site self-documenting::

        await grader.score(input=q, output=resp, expected=ref)

    ``score()`` is async even for heuristic (CPU-only) evaluators.  This is
    intentional: Phase 7's LLM-as-judge evaluator will call OpenAI inside
    ``score()``, and a single async interface avoids a later refactor of every
    caller.

    No try/except here — if an evaluator raises, it should crash loud.
    Per-row error handling is added in Phase 6.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Score:
    """Immutable result returned by every Evaluator.

    Attributes
    ----------
    name : str
        Human-readable label for the metric (e.g. ``"exact_match"``).
    value : float
        Numeric score in the closed interval [0.0, 1.0].  Convention:
        0.0 = complete failure, 1.0 = perfect.
    rationale : str | None
        Optional free-text explanation of why this score was assigned.
        Always ``None`` for deterministic heuristics; populated by
        LLM-as-judge evaluators in Phase 7.
    """

    name: str
    value: float
    rationale: str | None = None


class Evaluator(ABC):
    """Abstract base class for all Prism evaluators.

    Subclasses must implement :meth:`score`.  The method signature is
    intentionally identical for heuristic and LLM-backed evaluators so the
    evaluation runner in Phase 6 can call any evaluator through this single
    interface without branching.
    """

    @abstractmethod
    async def score(
        self,
        *,
        input: str,
        output: str,
        expected: str,
    ) -> Score:
        """Grade a single model response.

        Parameters
        ----------
        input : str
            The original prompt / question fed to the model.
        output : str
            The model's response being evaluated.
        expected : str
            The reference / gold-standard answer from the dataset.

        Returns
        -------
        Score
            An immutable :class:`Score` with ``value`` in [0.0, 1.0].
        """
        ...
