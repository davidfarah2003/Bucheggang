"""Shared base configuration for every contract model."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    """Strict: unknown keys are rejected and no type is coerced.

    Datetimes and dates are the one exception. They arrive as ISO strings in
    JSON and dicts alike, so those fields parse strings (see `Timestamp`).
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=False)


Timestamp = Annotated[datetime, Field(strict=False)]
Day = Annotated[date, Field(strict=False)]
NonEmpty = Annotated[str, Field(min_length=1)]
