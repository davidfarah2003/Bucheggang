"""Command line for one live scenario run.

    uv run python -m leash.runner.cli --scenario SCEN0101 --mandate-id TM... \
        --draft path/to/confirmed_draft.json --evaluate decline_everything_smoke

--draft is the confirmed PolicyDraft (JSON) that the mandate was created from.

The evaluate callable is chosen by name from EVALUATORS. The only entry today is
decline_everything_smoke, a smoke-test evaluator that declines every purchase so
the loop can be tried live before leash.engine.evaluate exists. The demo never
uses it; the engine's evaluate is added here when engine task 5 lands.
"""

import argparse
import json
import time
from pathlib import Path

from leash.contracts import Decision, Event, MandateState, PolicyDraft, PurchaseFacts

from . import loop


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


EVALUATORS = {"decline_everything_smoke": decline_everything_smoke}


def main() -> None:
    parser = argparse.ArgumentParser(description="Drive one scenario run against the simulator.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--mandate-id", required=True)
    parser.add_argument("--draft", required=True, type=Path, help="confirmed PolicyDraft JSON")
    parser.add_argument("--evaluate", required=True, choices=sorted(EVALUATORS))
    parser.add_argument("--run-id", help="attach to a run that is already started instead of starting one")
    args = parser.parse_args()

    policy = PolicyDraft.model_validate(json.loads(args.draft.read_text()))
    loop.configure_logging()
    run = loop.run_progress(args.run_id) if args.run_id else loop.start_run(args.scenario, args.mandate_id)
    if run["scenario_id"] != args.scenario or run["mandate_id"] != args.mandate_id:
        raise loop.RunLoopError(f"run {run['run_id']} is for {run['scenario_id']}/{run['mandate_id']}")
    print("run:", json.dumps(run, default=str))
    state = MandateState(mandate_id=args.mandate_id)
    state = loop.run_loop(run["run_id"], EVALUATORS[args.evaluate], policy, state)
    print("final run:", json.dumps(loop.run_progress(run["run_id"]), default=str))
    print("state:", state.model_dump_json())


if __name__ == "__main__":
    main()
