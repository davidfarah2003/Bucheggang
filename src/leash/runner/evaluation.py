"""Startup-selected evaluation with required, bounded model dependencies."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from leash.contracts import AssessmentBundle, Decision, Event, MandateState, PolicyDraft, PurchaseFacts
from leash.engine.evaluate import evaluate

from .budget import current_budget
from .settings import EvaluationSettings, SettingsError, load_evaluation, load_openrouter

Evaluate = Callable[[Event, PolicyDraft, MandateState, list[PurchaseFacts] | None], Decision]
MODEL_CAP_S = 1.0
MODEL_RESERVE_S = 2.0
log = logging.getLogger("leash.runner.evaluation")


class ModelDeadlineError(TimeoutError):
    """Required assessments exceeded their allowance; no decision was substituted."""


class ModelEvaluator:
    def __init__(self, configuration: EvaluationSettings):
        if not configuration.models_enabled or configuration.model_manifest is None:
            raise SettingsError("model evaluator requires explicit opt-in and a manifest")
        try:
            from leash.engine.classifier.assess import assess
            from leash.engine.classifier.behaviour import BehaviorModel
            from leash.engine.classifier.history import HistoryIndex
            from leash.engine.classifier.jev import DEADLINE_RESERVE_SECONDS, PROMPT_VERSION, REQUESTED_MODEL
        except ModuleNotFoundError as exc:
            raise SettingsError(
                "model-enabled startup requires the classifier package and its classifier dependency group"
            ) from exc
        self._model = BehaviorModel(configuration.model_manifest)
        if self._model.operating_threshold is None:
            raise SettingsError("model-enabled startup requires a selected O4 operating point")
        self._history = HistoryIndex()
        self._provider = load_openrouter()
        self._assess = assess
        self._requested_model = REQUESTED_MODEL
        self._prompt_version = PROMPT_VERSION
        self._provider_reserve_s = DEADLINE_RESERVE_SECONDS
        log.info("model configuration ready: jev=%s artifact=%s operating_point=%s model_id=%s",
                 self._requested_model, self._model.artifact_version,
                 self._model.operating_threshold, self._model.model_id)

    def __call__(self, event: Event, policy: PolicyDraft, state: MandateState,
                 facts: list[PurchaseFacts] | None) -> Decision:
        if facts is None:
            raise ValueError(f"{event.authorization.authorization_id}: extraction facts are missing")
        budget = current_budget(event.deadline_at)
        if budget.remaining(MODEL_RESERVE_S) <= 0:
            log.error("%s: no model allowance before the submission reserve", event.authorization.authorization_id)
            raise ModelDeadlineError(f"{event.authorization.authorization_id}: no model allowance before the submission reserve")
        baseline = evaluate(event, policy, state, facts)
        if any(check.result == "fail" for check in baseline.evidence):
            log.info("%s: deterministic failure, model calls not required", event.authorization.authorization_id)
            return baseline
        allowance = min(MODEL_CAP_S, budget.remaining(MODEL_RESERVE_S))
        if allowance <= 0:
            log.error("%s: model allowance expired before dispatch", event.authorization.authorization_id)
            raise ModelDeadlineError(f"{event.authorization.authorization_id}: model allowance expired before dispatch")
        started = time.monotonic()
        stage_event = event.model_copy(update={"deadline_at": min(
            budget.wall_deadline(),
            datetime.now(UTC) + timedelta(seconds=allowance + self._provider_reserve_s),
        )})

        async def completed_assessments() -> AssessmentBundle:
            async with asyncio.timeout_at(asyncio.get_running_loop().time() + allowance):
                return await self._assess(
                    stage_event, policy, state, self._history, api_key=self._provider.api_key,
                    behaviour_model=self._model,
                )

        try:
            bundle = asyncio.run(completed_assessments())
            bundle = AssessmentBundle.model_validate(bundle.model_dump(mode="python"))
            if bundle.behaviour is None or bundle.semantic is None:
                raise ValueError("configured model evaluator requires both completed assessments")
            expected_features = self._history.for_event(event)
            if bundle.features != expected_features:
                raise ValueError("assessment history differs from the authorized pre-event profile")
            expected_behaviour = self._model.score(expected_features)
            if bundle.behaviour != expected_behaviour:
                raise ValueError("assessment differs from the configured behavioural score and operating point")
            if (bundle.semantic.requested_model != self._requested_model
                    or bundle.semantic.prompt_version != self._prompt_version):
                raise ValueError("assessment differs from the configured Jev model or prompt")
            if time.monotonic() - started >= allowance or budget.remaining(MODEL_RESERVE_S) <= 0:
                raise ModelDeadlineError(f"{event.authorization.authorization_id}: model stage exceeded its allowance")
            decision = evaluate(event, policy, state, facts, assessments=bundle)
            if budget.remaining(MODEL_RESERVE_S) <= 0:
                raise ModelDeadlineError(f"{event.authorization.authorization_id}: model composition exhausted its reserve")
        except TimeoutError as exc:
            log.error("%s: required model deadline expired; no replacement decision", event.authorization.authorization_id)
            raise ModelDeadlineError(
                f"{event.authorization.authorization_id}: required model stage exceeded its deadline allowance"
            ) from exc
        except Exception as exc:
            log.error("%s: required model evaluation failed (%s); no replacement decision",
                      event.authorization.authorization_id, type(exc).__name__)
            raise
        log.info("%s: model assessments completed in %.3f ms, purchase_digest=%s",
                 event.authorization.authorization_id, (time.monotonic() - started) * 1000,
                 bundle.purchase_digest)
        return decision


def load_evaluator() -> Evaluate:
    configuration = load_evaluation()
    if not configuration.models_enabled:
        from leash.engine.classifier.bridge import HistoryOnlyEvaluator
        from leash.engine.classifier.history import HistoryIndex

        evaluator = HistoryOnlyEvaluator(HistoryIndex())
        log.info("evaluation configuration: history only, models off")
        return evaluator
    return ModelEvaluator(configuration)
