"""Command line for one live scenario run.

    uv run python -m leash.runner.cli --scenario SCEN0101 --mandate-id TM... \
        --draft path/to/confirmed_draft.json --evaluate engine

--draft is the confirmed PolicyDraft (JSON) that the mandate was created from.

The evaluate callable is chosen by name from EVALUATORS. "engine" is
leash.engine.evaluate.evaluate, the one the demo uses. The two smoke evaluators
decline or step up every purchase; they exercise the run loop and step-up
handling and the demo never uses them.
"""

import argparse
import json
import time
from pathlib import Path

from leash.contracts import Decision, Event, MandateState, PolicyDraft, PurchaseFacts

from leash.engine import state as state_store
from leash.engine.evaluate import evaluate as engine_evaluate

from . import loop, records, routes, stepups


def serve(book: stepups.StepUpBook, port: int) -> None:
    """Serve the step-up router alone for a local try. The demo mounts it in leash.api."""
    import threading

    import uvicorn
    from fastapi import FastAPI, Header

    def local_customer(x_local_customer: str = Header()) -> str:
        return x_local_customer

    app = FastAPI()
    app.include_router(routes.step_up_router(book, local_customer))
    app.include_router(routes.history_router(local_customer))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, name="step-up-routes", daemon=True).start()


def decline_everything_smoke(
    event: Event, policy: PolicyDraft, state: MandateState, facts: list[PurchaseFacts] | None
) -> Decision:
    """Smoke-test evaluator: declines every purchase. Never used in the demo."""
    started = time.monotonic()
    return Decision(
        authorization_id=event.authorization.authorization_id,
        decision="decline",
        reason_codes=[],
        customer_message="Declined by the runner smoke test.",
        evidence=[],
        explanation="Runner smoke test: this evaluator declines every purchase to exercise the run loop.",
        engine_version="runner-smoke-decline-everything",
        mandate_version=policy.version,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        decided_at=loop._now(),
    )


def step_up_everything_smoke(
    event: Event, policy: PolicyDraft, state: MandateState, facts: list[PurchaseFacts] | None
) -> Decision:
    """Smoke-test evaluator: asks the customer about every purchase. Never used in the demo."""
    started = time.monotonic()
    return Decision(
        authorization_id=event.authorization.authorization_id,
        decision="step_up",
        reason_codes=["customer_confirmation"],
        customer_message="Runner smoke test: please confirm or decline this purchase.",
        evidence=[],
        explanation="Runner smoke test: this evaluator steps up every purchase to exercise step-up handling.",
        engine_version="runner-smoke-step-up-everything",
        mandate_version=policy.version,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        decided_at=loop._now(),
    )


EVALUATORS = {
    "engine": engine_evaluate,
    "decline_everything_smoke": decline_everything_smoke,
    "step_up_everything_smoke": step_up_everything_smoke,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Drive one scenario run against the simulator.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--mandate-id", required=True)
    parser.add_argument("--draft", required=True, type=Path, help="confirmed PolicyDraft JSON")
    parser.add_argument("--evaluate", required=True, choices=sorted(EVALUATORS))
    parser.add_argument("--serve-port", type=int, help="also serve the step-up routes on 127.0.0.1:PORT (local try only)")
    parser.add_argument("--run-id", help="attach to a run that is already started instead of starting one")
    args = parser.parse_args()

    policy = PolicyDraft.model_validate(json.loads(args.draft.read_text()))
    loop.configure_logging()
    run = loop.run_progress(args.run_id) if args.run_id else loop.start_run(args.scenario, args.mandate_id)
    if run["scenario_id"] != args.scenario or run["mandate_id"] != args.mandate_id:
        raise loop.RunLoopError(f"run {run['run_id']} is for {run['scenario_id']}/{run['mandate_id']}")
    print("run:", json.dumps(run, default=str))
    records.check_consistent(args.mandate_id)
    with records.mandate_lock(args.mandate_id):
        start_state = state_store.load(args.mandate_id)
    print("state at start:", json.dumps({"handled": sorted(start_state.handled), "approvals": len(start_state.approvals),
                                        "pending_step_ups": start_state.pending_step_ups}))
    window_s = stepups.human_window_s()
    book = stepups.StepUpBook()
    book.start(args.mandate_id, run["run_id"])
    if args.serve_port:
        serve(book, args.serve_port)
    state = loop.run_loop(run["run_id"], EVALUATORS[args.evaluate], policy, args.mandate_id, book, window_s)
    book.stop()
    print("final run:", json.dumps(loop.run_progress(run["run_id"]), default=str))
    print("state:", state.model_dump_json())


if __name__ == "__main__":
    main()
