"""TypeSafe Jev history-risk assessment through OpenRouter System One."""

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import UTC, datetime

import httpx

from leash.contracts import HistoryFeatures, JevAnswer, SemanticAssessment

URL = "https://openrouter.ai/api/v1/systemone"
REQUESTED_MODEL = "typesafe/jev-1.13-20260917"
SERVED_PROVIDER = "TypeSafe"
PROMPT_VERSION = "history-risk-1"
DEADLINE_RESERVE_SECONDS = 2.25
MINIMUM_RECHECK_SECONDS = 2.0
MAX_RESPONSE_BYTES = 64_000
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
        if len(winners) == 1:
            if choice != winners[0]:
                raise JevResponseError(f"{question_id}: provider choice differs from local argmax")
            selected = winners[0]
        else:
            if choice is not None and choice not in winners:
                raise JevResponseError(f"{question_id}: provider choice is outside the tied options")
            selected = None
        validated.append(JevAnswer(question_id=question_id,
                                   options={key: float(value) for key, value in probabilities.items()},
                                   selected=selected))
    return SemanticAssessment(
        requested_model=REQUESTED_MODEL, served_model=model,
        prompt_version=PROMPT_VERSION, answers=validated, latency_ms=latency_ms,
    )


async def assess_jev(features: HistoryFeatures, deadline_at: datetime, *,
                     api_key: str) -> SemanticAssessment:
    """Use numeric history only; the startup caller supplies a scoped Jev credential."""
    if deadline_at.tzinfo is None:
        raise ValueError("Jev deadline lacks timezone")
    if not api_key:
        raise RuntimeError("Jev API key is missing")
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
            async with client.stream("POST", URL, json=request,
                                     headers={"Authorization": f"Bearer {api_key}"}) as response:
                if response.status_code != 200:
                    raise JevResponseError(f"Jev HTTP {response.status_code}")
                chunks = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise JevResponseError("Jev response exceeds the bounded result size")
                    chunks.append(chunk)
        try:
            text = b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError as error:
            raise JevResponseError("Jev response is not UTF-8") from error
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = _parse_response(text, latency_ms)
    if (deadline_at - datetime.now(UTC)).total_seconds() < MINIMUM_RECHECK_SECONDS:
        raise TimeoutError("Jev result left too little time for state recheck")
    return result
