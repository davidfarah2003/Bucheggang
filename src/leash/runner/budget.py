"""One monotonic allowance shared by the stages of a decision operation."""

from __future__ import annotations

import math
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class DecisionBudget:
    deadline_at: datetime
    stop_at: float

    @classmethod
    def until(cls, deadline_at: datetime) -> DecisionBudget:
        if deadline_at.utcoffset() is None:
            raise ValueError("decision deadline must have a timezone")
        remaining = (deadline_at - datetime.now(UTC)).total_seconds()
        if not math.isfinite(remaining):
            raise ValueError("decision deadline must be finite")
        return cls(deadline_at, time.monotonic() + remaining)

    def remaining(self, reserve_s: float = 0) -> float:
        return min(
            self.stop_at - time.monotonic(),
            (self.deadline_at - datetime.now(UTC)).total_seconds(),
        ) - reserve_s

    def wall_deadline(self, reserve_s: float = 0) -> datetime:
        return min(
            self.deadline_at - timedelta(seconds=reserve_s),
            datetime.now(UTC) + timedelta(seconds=self.stop_at - time.monotonic() - reserve_s),
        )


_active_budget: ContextVar[DecisionBudget | None] = ContextVar("decision_budget", default=None)


def current_budget(deadline_at: datetime) -> DecisionBudget:
    """Direct evaluator calls establish their own budget; guarded calls inherit it."""
    active = _active_budget.get()
    return DecisionBudget.until(deadline_at) if active is None else active


def within_budget(budget: DecisionBudget, function: Callable[..., T], *args) -> T:
    token = _active_budget.set(budget)
    try:
        return function(*args)
    finally:
        _active_budget.reset(token)
