"""Chronological walk-forward helpers that never leak holdout observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class WalkForwardFold:
    train: tuple
    test: tuple


def expanding_walk_forward(
    rows: Sequence[T], *, train_size: int, test_size: int, step_size: int | None = None
) -> list[WalkForwardFold]:
    """Return expanding-window train/test folds in strict chronological order."""
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size and test_size must be positive")
    step = step_size or test_size
    if step <= 0:
        raise ValueError("step_size must be positive")
    folds: list[WalkForwardFold] = []
    train_end = train_size
    while train_end + test_size <= len(rows):
        folds.append(WalkForwardFold(tuple(rows[:train_end]), tuple(rows[train_end:train_end + test_size])))
        train_end += step
    return folds
