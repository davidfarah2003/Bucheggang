"""Command line for one live scenario run.

    uv run python -m leash.runner.cli --scenario SCEN0101 --mandate-id TM... \
        --draft path/to/confirmed_draft.json --evaluate engine

--draft is the confirmed PolicyDraft (JSON) that the mandate was created from.

The pure engine is used by default. LEASH_ENABLE_MODELS=1 explicitly requires
the configured classifier artifact and provider. A failed operation raises and
stops the runner without submitting a replacement decision.
"""

import argparse
import json
import os
from pathlib import Path
from datetime import timedelta

from leash.contracts import PolicyDraft

from leash.engine import state as state_store
from leash.policy.store import DraftStore

from . import loop, records, routes, stepups, policy_context
from .coordinator import Coordinator


def serve(book: stepups.StepUpBook, port: int, store: DraftStore) -> None:
    """Serve the step-up router alone for a local try. The demo mounts it in leash.api."""
    import threading

    import uvicorn
    from fastapi import FastAPI, Header

    def local_customer(x_local_customer: str = Header()) -> str:
        return x_local_customer

    app = FastAPI()
    app.include_router(routes.step_up_router(book, local_customer, store))
    app.include_router(routes.history_router(local_customer, store))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, name="step-up-routes", daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Drive one scenario run against the simulator.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--mandate-id", required=True)
    parser.add_argument("--draft", required=True, type=Path, help="confirmed PolicyDraft JSON")
    parser.add_argument("--evaluate", default="engine", choices=["engine"])
    parser.add_argument("--serve-port", type=int, help="also serve the step-up routes on 127.0.0.1:PORT (local try only)")
    parser.add_argument("--run-id", help="attach to a run that is already started instead of starting one")
    args = parser.parse_args()

    store_root = os.environ.get("LEASH_POLICY_STORE")
    if not store_root:
        raise RuntimeError("runner requires LEASH_POLICY_STORE with the customer confirmations")
    store = DraftStore(Path(store_root))
    policy = PolicyDraft.model_validate(json.loads(args.draft.read_text()))
    loop.configure_logging()
    record, _ = policy_context.confirmation(store, args.mandate_id)
    if record["hash"] != policy.hash or record["version"] != policy.version:
        raise loop.RunLoopError("supplied draft differs from the stored customer confirmation")
    book = stepups.StepUpBook()
    with Coordinator(store, book).locked(args.mandate_id, deadline_at=loop._now() + timedelta(seconds=30)) as ids:
        start_state = state_store.load(args.mandate_id, customer_mandates=ids)
    run = loop.run_progress(args.run_id) if args.run_id else loop.start_run(args.scenario, args.mandate_id)
    if run["scenario_id"] != args.scenario or run["mandate_id"] != args.mandate_id:
        raise loop.RunLoopError(f"run {run['run_id']} is for {run['scenario_id']}/{run['mandate_id']}")
    print("run:", json.dumps(run, default=str))
    print("state at start:", json.dumps({"handled": sorted(start_state.handled), "approvals": len(start_state.approvals),
                                        "pending_step_ups": start_state.pending_step_ups, "customer_approvals": len(start_state.customer_approvals)}))
    window_s = stepups.human_window_s()
    book.start(args.mandate_id, run["run_id"], store)
    try:
        if args.serve_port is not None:
            serve(book, args.serve_port, store)
        state = loop.run_loop(run["run_id"], book.evaluator, policy, args.mandate_id, book, window_s, store)
    except Exception:
        loop.log.exception("runner stopped after an operation failed")
        raise
    finally:
        book.stop()
    print("final run:", json.dumps(loop.run_progress(run["run_id"]), default=str))
    print("state:", state.model_dump_json())


if __name__ == "__main__":
    main()
