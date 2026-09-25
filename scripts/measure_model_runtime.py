"""One measured replay through the current production model evaluator."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import replay
from leash.contracts import MandateState, PolicyDraft, PurchaseFacts
from leash.engine.state import apply
from leash.extract import extract_event
from leash.policy.store import draft_hash
from leash.runner.budget import DecisionBudget
from leash.runner.evaluation import ModelEvaluator
from leash.runner.loop import decide_with_guard
from leash.runner.settings import EvaluationSettings

stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')
out = ROOT / '.cotal' / f'current-model-replay-{stamp}'
out.mkdir(mode=0o700)
paths = {
    'SCEN0000': 'docs/eval/replay-policies/SCEN0000.json',
    'SCEN0001': 'docs/eval/replay-policies/SCEN0001.json',
    'SCEN0002': 'docs/samples/scen0002_draft.json',
    'SCEN0003': 'docs/eval/replay-policies/SCEN0003.json',
    'SCEN0004': 'docs/eval/replay-policies/SCEN0004.json',
}
scenarios, authorities, merchants, attempts, items = replay.load_pack()
policies = {}
for scenario_id, name in paths.items():
    raw = json.loads((ROOT/name).read_text())
    policy = PolicyDraft.model_validate(raw)
    expected = draft_hash(raw['instruction'], raw['rules'], raw['uncertainty_policy'],
                          hash_version=policy.hash_version, boundary_cases=raw.get('boundary_cases'))
    if policy.hash != expected or policy.instruction != scenarios[scenario_id]['cardholder_instruction']:
        raise ValueError(f'{scenario_id}: policy hash or instruction mismatch')
    policies[scenario_id] = policy

runtime_files = ['src/leash/runner/evaluation.py', 'src/leash/engine/evaluate.py',
                 'src/leash/engine/model_checks.py', 'src/leash/engine/classifier/assess.py',
                 'src/leash/engine/classifier/behaviour.py', 'src/leash/engine/classifier/jev.py',
                 'src/leash/contracts/classifier.py']
summary = {
    'status': 'running',
    'started_at': datetime.now(UTC).isoformat(),
    'source_head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
    'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'runtime_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in runtime_files},
    'policy_hashes': {key: value.hash for key, value in policies.items()},
    'purchase_budget_s': 20, 'model_cap_s': 6, 'behaviour_threshold': .498,
    'completed_rows': 0, 'completed_rows_with_model_evidence': 0,
    'simulator_submissions': 0, 'customer_answers': 0,
    'retries': 0, 'scope': 'Real model calls; sequential offline purchase/state replay, no live Wallet journey.',
}
summary_path = out/'summary.json'
summary_path.write_text(json.dumps(summary, indent=2))
print('Evidence:', out, flush=True)
results = []
current = None
try:
    evaluator = ModelEvaluator(EvaluationSettings(True, ROOT/'docs/eval/classifier/model-manifest.json', .498), cap_s=6)
    with (out/'decisions.jsonl').open('x') as stream, ThreadPoolExecutor(max_workers=1) as pool:
        for scenario_id, policy in sorted(policies.items()):
            rows = sorted((row for row in attempts.values() if row['scenario_id'] == scenario_id),
                          key=lambda row: int(row['replay_order']))
            if len(rows) != int(scenarios[scenario_id]['event_count']):
                raise ValueError(f'{scenario_id}: attempt count differs')
            state = MandateState(mandate_id=f'offline-mandate-{uuid4().hex}')
            prior = {}
            for row in rows:
                current = row['authorization_id']
                event = replay.build_event(row, authorities[row['authority_id']], merchants[row['merchant_id']],
                                           items[current], policy, state, prior, 20)
                started = time.perf_counter()
                facts = [PurchaseFacts.model_validate(value) for value in
                         extract_event(event.model_dump(mode='json'), requested=replay.requested_item(policy))]
                decision = decide_with_guard(evaluator, event, policy, state, facts, pool,
                                             budget=DecisionBudget.until(event.deadline_at))
                elapsed = (time.perf_counter()-started)*1000
                record = {
                    'scenario_id': scenario_id, 'authorization_id': current,
                    'decision': decision.model_dump(mode='json'), 'elapsed_ms': round(elapsed, 3),
                    'model_evidence_count': sum(check.source == 'model' for check in decision.evidence),
                }
                stream.write(json.dumps(record)+'\n')
                stream.flush()
                results.append(record)
                state = apply(state, event, decision)
                prior[current] = event
                print(f'{len(results)}/45 {current} {decision.decision} {elapsed:.1f}ms model_checks={record["model_evidence_count"]}', flush=True)
    if len(results) != 45:
        raise ValueError(f'expected 45 completed rows, got {len(results)}')
    summary['status'] = 'completed'
except Exception as exc:
    summary['status'] = 'failed'
    summary['failed_authorization'] = current
    summary['error_type'] = type(exc).__name__
    summary['error'] = str(exc)
    raise
finally:
    summary['completed_rows'] = len(results)
    summary['completed_rows_with_model_evidence'] = sum(row['model_evidence_count'] > 0 for row in results)
    summary['decisions'] = dict(Counter(row['decision']['decision'] for row in results))
    summary['finished_at'] = datetime.now(UTC).isoformat()
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
