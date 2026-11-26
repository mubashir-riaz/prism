"""Evaluator registry — factory, runner, and aggregation utilities.

Public API
----------
``_REGISTRY``
    Dict mapping string names → Evaluator subclasses.  Add a new entry here
    to make a new evaluator available everywhere without touching any other file.

``UnknownEvaluatorError``
    Raised loud and immediately when an unregistered name is requested.
    Never silently falls back to a default.

``build_evaluator(name, params)``
    Instantiate a registered evaluator, forwarding ``params`` as keyword
    arguments to its constructor.

``run_evaluators(configs, *, input, output, expected)``
    Run a list of evaluator configs concurrently via ``asyncio.gather`` and
    return one Score per config, in the same order as the input list.

``weighted_average(scores, weights)``
    Collapse a list of Scores into a single float using per-score weights.
    Returns 0.0 when the total weight is zero (avoids ZeroDivisionError).
"""

import asyncio
from typing import Any

from app.evaluation.base import Evaluator, Score
from app.evaluation.heuristics.contains import ContainsEvaluator
from app.evaluation.heuristics.exact_match import ExactMatchEvaluator
from app.evaluation.heuristics.length_bounds import LengthBoundsEvaluator


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class UnknownEvaluatorError(Exception):
    """Raised when a requested evaluator name is not in the registry.

    Attributes
    ----------
    name : str
        The unrecognised name that was requested.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Unknown evaluator: {name!r}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[Evaluator]] = {
    "exact_match": ExactMatchEvaluator,
    "contains": ContainsEvaluator,
    "length_bounds": LengthBoundsEvaluator,
}
"""Map of evaluator name → class.

To register a new evaluator, add one line here — no other file needs changing.
"""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_evaluator(
    name: str,
    params: dict[str, Any] | None = None,
) -> Evaluator:
    """Instantiate and return an evaluator by name.

    Parameters
    ----------
    name : str
        Registered evaluator name (e.g. ``"exact_match"``).
    params : dict | None
        Constructor keyword arguments forwarded to the evaluator class.
        ``None`` is treated as an empty dict — no params.

    Returns
    -------
    Evaluator
        A fresh instance of the requested evaluator.

    Raises
    ------
    UnknownEvaluatorError
        If ``name`` is not in ``_REGISTRY``.
    """
    if name not in _REGISTRY:
        raise UnknownEvaluatorError(name)
    cls = _REGISTRY[name]
    return cls(**(params or {}))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_evaluators(
    configs: list[dict[str, Any]],
    *,
    input: str,
    output: str,
    expected: str,
) -> list[Score]:
    """Run multiple evaluators concurrently and return their scores.

    Each entry in ``configs`` is a dict with:
        ``name`` (str, required)
            Registered evaluator name.
        ``params`` (dict, optional)
            Constructor kwargs forwarded to :func:`build_evaluator`.

    Scores are returned in the **same order** as the input ``configs`` list —
    ``asyncio.gather`` preserves insertion order.

    Parameters
    ----------
    configs : list[dict]
        Evaluator configurations to run.
    input, output, expected : str
        Keyword-only strings forwarded to every evaluator's ``score()`` method.

    Returns
    -------
    list[Score]
        One Score per config entry, in config order.

    Raises
    ------
    UnknownEvaluatorError
        If any config contains an unregistered evaluator name.
        Raised eagerly at construction time, before any scoring begins.
    """
    # Build all evaluators up front — unknown names fail fast here, before
    # any async work is started, so the caller gets a clean error.
    evaluators: list[Evaluator] = [
        build_evaluator(cfg["name"], cfg.get("params")) for cfg in configs
    ]

    scores = await asyncio.gather(
        *[
            ev.score(input=input, output=output, expected=expected)
            for ev in evaluators
        ]
    )
    return list(scores)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def weighted_average(scores: list[Score], weights: list[float]) -> float:
    """Compute the weighted average of a list of Scores.

    Parameters
    ----------
    scores : list[Score]
        Scored results from one or more evaluators.
    weights : list[float]
        Per-score weights, in the same order as ``scores``.

    Returns
    -------
    float
        Weighted mean of ``score.value`` values.  Returns ``0.0`` when the
        total weight sums to zero (prevents ZeroDivisionError and is a
        sensible sentinel for "no meaningful signal").

    Notes
    -----
    ``len(scores)`` must equal ``len(weights)``; no assertion is made here
    for performance — callers are responsible for passing parallel lists.
    """
    total_weight = sum(weights)
    if total_weight == 0.0:
        return 0.0
    return sum(s.value * w for s, w in zip(scores, weights)) / total_weight
