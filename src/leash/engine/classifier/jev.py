"""TypeSafe Jev history-risk assessment through OpenRouter System One."""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .types import HistoryFeatures, JevAnswer, SemanticAssessment

URL = "https://openrouter.ai/api/v1/systemone"
REQUESTED_MODEL = "typesafe/jev-1.13-20260917"
SERVED_PROVIDER = "TypeSafe"
PROMPT_VERSION = "history-risk-1"
DEADLINE_RESERVE_SECONDS = 2.25
QUESTIONS = {
    "spend_pattern": {
        "type": "choice",
        "instructions": (
            "Using only the numeric history summary, classify whether this purchase's "
            "amount is unusual for prior approved purchases. Do not infer merchant or item facts."
        ),
        "criteria": {
            "ordinary": "Prior category amounts support the current amount as ordinary.",
            "unusual": "The current amount is unusually large against supported history.",
            "unclear": "The summary has too little relevant history to decide.",
        },
    },
    "activity_pattern": {
        "type": "choice",
        "instructions": (
            "Using only the numeric history summary, classify whether recent purchasing "
            "activity is unusual. Do not infer authorization or a customer answer."
        ),
        "criteria": {
            "ordinary": "Earlier purchases and recent attempts support ordinary activity.",
            "unusual": "Recent attempts or unfamiliarity support an unusual-activity signal.",
            "unclear": "The summary has too little relevant history to decide.",
        },
    },
}


class JevResponseError(ValueError):
    """The provider returned a response that cannot be used as a risk signal."""


def _read_key() -> str:
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=Path(__file__).resolve().parent, capture_output=True, text=True, check=True,
        timeout=1.0,
    ).stdout.strip()
    path = Path(common).parent / ".env"
    matches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "OPENROUTER_API":
            matches.append(value.strip().strip('"').strip("'"))
    if len(matches) != 1 or not matches[0]:
        raise RuntimeError(f"{path}: expected one nonempty OPENROUTER_API entry")
    return matches[0]


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise JevResponseError(f"Jev response repeats JSON key {key!r}")
        result[key] = value
    return result


def _parse_response(text: str, latency_ms: int) -> SemanticAssessment:
    try:
        body = json.loads(text, object_pairs_hook=_unique_pairs)
    except json.JSONDecodeError as error:
        raise JevResponseError("Jev response is not valid JSON") from error
    if not isinstance(body, dict):
        raise JevResponseError("Jev response is not an object")
    model = body.get("model")
    if model != REQUESTED_MODEL or body.get("provider") != SERVED_PROVIDER:
        raise JevResponseError(f"unexpected Jev model or provider: {model!r}, {body.get('provider')!r}")
    answers = body.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(QUESTIONS):
        raise JevResponseError("Jev response has missing or unexpected questions")
    validated = []
    for question_id, question in QUESTIONS.items():
        answer = answers[question_id]
        options = set(question["criteria"])
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            raise JevResponseError(f"{question_id}: expected a choice answer")
        probabilities = answer.get("probabilities")
        if not isinstance(probabilities, dict) or set(probabilities) != options:
            raise JevResponseError(f"{question_id}: probability option keys differ from request")
        if not all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
                   for value in probabilities.values()):
            raise JevResponseError(f"{question_id}: non-finite or out-of-range probability")
        if not math.isclose(sum(probabilities.values()), 1.0, rel_tol=0, abs_tol=1e-6):
            raise JevResponseError(f"{question_id}: probabilities do not sum to one")
        top = max(probabilities.values())
        winners = [option for option, value in probabilities.items() if value == top]
        choice = answer.get("choice")
        if choice not in options or choice not in winners:
            raise JevResponseError(f"{question_id}: provider choice differs from local argmax")
        selected = winners[0] if len(winners) == 1 else None
        validated.append(JevAnswer(question_id=question_id,
                                   options={key: float(value) for key, value in probabilities.items()},
                                   selected=selected))
    return SemanticAssessment(
        requested_model=REQUESTED_MODEL, served_model=model,
        prompt_version=PROMPT_VERSION, answers=validated, latency_ms=latency_ms,
    )


async def assess_jev(features: HistoryFeatures, deadline_at: datetime) -> SemanticAssessment:
    """Use numeric history only; fail before the runner's absolute deadline reserve."""
    if deadline_at.tzinfo is None:
        raise ValueError("Jev deadline lacks timezone")
    key = _read_key()
    remaining = (deadline_at - datetime.now(UTC)).total_seconds() - DEADLINE_RESERVE_SECONDS
    if remaining <= 0:
        raise TimeoutError("Jev has no time remaining before the deadline reserve")
    state = {
        "feature_schema_version": features.schema_version,
        "values": features.values,
        "missing": features.missing,
        "support": features.support,
    }
    request = {
        "model": REQUESTED_MODEL,
        "provider": {"only": ["typesafe"], "allow_fallbacks": False},
        "state": state,
        "questions": QUESTIONS,
    }
    started = time.perf_counter()
    async with asyncio.timeout_at(asyncio.get_running_loop().time() + remaining):
        async with httpx.AsyncClient(timeout=remaining, follow_redirects=False) as client:
            response = await client.post(URL, json=request,
                                         headers={"Authorization": f"Bearer {key}"})
    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        raise JevResponseError(f"Jev HTTP {response.status_code}")
    return _parse_response(response.text, latency_ms)
