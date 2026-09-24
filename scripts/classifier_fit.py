"""Compare LR and CatBoost on frozen customer/time splits, evaluation only.

    PYTHONPATH=src python scripts/classifier_fit.py

No score enters the live evaluator. The June threshold table is a proposal for
owner ruling O4, and this script never chooses an operational threshold.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from time import perf_counter

import catboost
import joblib
import numpy as np
import sklearn
from catboost import CatBoostClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from leash.engine.classifier.history import HistoryIndex
from leash.engine.classifier.types import FEATURE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "docs" / "eval" / "classifier"
SPLIT = EVAL / "split-manifest.json"
ARTIFACT = EVAL / "model-evaluation-only.joblib"
MANIFEST = EVAL / "model-manifest.json"
REPORT = EVAL / "m2-report.md"
RATES = (0.01, 0.02, 0.05, 0.10)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_split() -> dict:
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    if split["feature_schema_version"] != FEATURE_SCHEMA_VERSION:
        raise ValueError("split manifest has a different history feature schema")
    for name, expected in split["input_sha256"].items():
        if _sha256(ROOT / name) != expected:
            raise ValueError(f"split input changed: {name}")
    fitting, reserved = set(split["fitting_customers"]), set(split["reserved_customers"])
    if fitting & reserved or len(fitting) != 400 or len(reserved) != 100:
        raise ValueError("split customer membership is invalid")
    if split["protocol"]["g1_disposition"] != (
        "variant 3: label seen-customer July as selection-informed; reserved July is primary"
    ):
        raise ValueError("split selection-bias disposition changed")
    return split


def _window(day: str, windows: dict[str, list[str]]) -> str:
    matches = [name for name, (start, end) in windows.items() if start <= day < end]
    if len(matches) != 1:
        raise ValueError(f"purchase day {day} belongs to {len(matches)} windows")
    return matches[0]


def _issuer_pass(row: dict[str, str], month_spend_before: float) -> bool:
    """Issuer restrictions available in history; no mandate rule is inferred."""
    amount = float(row["billing_amount_chf"])
    per_limit = float(row["per_transaction_limit_chf"])
    monthly_limit = float(row["monthly_limit_chf"])
    if not all(map(math.isfinite, (amount, per_limit, monthly_limit, month_spend_before))):
        raise ValueError(f"{row['authorization_id']}: non-finite issuer restriction")
    online = row["online_enabled"]
    international = row["international_enabled"]
    if online not in {"true", "false"} or international not in {"true", "false"}:
        raise ValueError(f"{row['authorization_id']}: invalid issuer switch")
    online_channel = row["channel"] in {"ecommerce", "recurring"}
    return (
        row["card_status"] == "active"
        and (not online_channel or online == "true")
        and (row["merchant_country"] == "CH" or international == "true")
        and amount <= per_limit
        and month_spend_before + amount <= monthly_limit
    )


def _data(split: dict) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray], tuple[str, ...]]:
    count = sum(sum(groups.values()) for groups in split["purchase_counts"].values())
    names: tuple[str, ...] = ()
    matrix = np.empty((count, 50), dtype=np.float64)
    labels = np.empty(count, dtype=np.int8)
    meta: dict[str, list] = {name: [] for name in (
        "window", "population", "initiator", "issuer_pass", "customer_approved",
        "card_approved", "card_status", "customer_id", "card_id"
    )}
    fitting = set(split["fitting_customers"])
    reserved = set(split["reserved_customers"])
    monthly_spend: dict[tuple[str, str], float] = defaultdict(float)
    index = HistoryIndex()
    for i, (row, features) in enumerate(index.historical_purchases("additional")):
        if i >= count:
            raise ValueError("history has more purchases than split manifest")
        if not names:
            names = tuple(sorted(features.values))
            if len(names) != matrix.shape[1]:
                raise ValueError("hist-1 feature count differs from frozen schema")
        if tuple(sorted(features.values)) != names:
            raise ValueError(f"{row['authorization_id']}: inconsistent history feature names")
        matrix[i] = [np.nan if features.values[name] is None else features.values[name]
                     for name in names]
        labels[i] = row["status"] == "declined"
        customer_id = row["customer_id"]
        if customer_id not in fitting | reserved:
            raise ValueError(f"{row['authorization_id']}: customer outside frozen split")
        population = "seen" if customer_id in fitting else "reserved"
        day = row["timestamp"][:10]
        window = _window(day, split["windows_utc_half_open"])
        month_key = (row["account_id"], row["timestamp"][:7])
        issuer_pass = _issuer_pass(row, monthly_spend[month_key])
        if row["status"] == "approved":
            monthly_spend[month_key] += float(row["billing_amount_chf"])
        for key, value in (
            ("window", window), ("population", population),
            ("initiator", row["initiator_type"]), ("issuer_pass", issuer_pass),
            ("customer_approved", features.values["customer_approved_purchase_count"]),
            ("card_approved", features.values["card_approved_purchase_count"]),
            ("card_status", row["card_status"]),
            ("customer_id", customer_id), ("card_id", row["card_id"]),
        ):
            meta[key].append(value)
    if i + 1 != count:
        raise ValueError(f"history has {i + 1} purchases, split expects {count}")
    return matrix, labels, {key: np.asarray(values) for key, values in meta.items()}, names


def _candidate(name: str, seed: int) -> Pipeline:
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    if name == "lr":
        return Pipeline([
            ("impute", imputer), ("scale", StandardScaler()),
            ("model", LogisticRegression(C=1.0, solver="lbfgs", max_iter=500,
                                         random_state=seed)),
        ])
    if name == "catboost":
        return Pipeline([
            ("impute", imputer),
            ("model", CatBoostClassifier(
                iterations=300, depth=5, learning_rate=0.05, l2_leaf_reg=3.0,
                loss_function="Logloss", random_seed=seed, thread_count=4,
                verbose=False, allow_writing_files=False,
            )),
        ])
    raise ValueError(f"unknown candidate: {name}")


def _probabilities(model: Pipeline, matrix: np.ndarray) -> np.ndarray:
    scores = np.asarray(model.predict_proba(matrix)[:, 1], dtype=np.float64)
    if scores.shape != (len(matrix),) or not np.isfinite(scores).all():
        raise ValueError("model produced missing or non-finite scores")
    if ((scores < 0) | (scores > 1)).any():
        raise ValueError("model produced scores outside [0,1]")
    return scores


def _metrics(labels: np.ndarray, scores: np.ndarray, baseline: float) -> dict:
    n = len(labels)
    positives = int(labels.sum())
    if n == 0:
        return {"n": 0, "declines": 0, "status": "no examples"}
    result = {
        "n": n, "declines": positives, "decline_rate": positives / n,
        "brier": float(brier_score_loss(labels, scores)),
        "baseline_brier": float(brier_score_loss(labels, np.full(n, baseline))),
    }
    if n < 30 or positives < 5 or n - positives < 5:
        result.update(pr_auc=None, roc_auc=None,
                      status="insufficient rows or label outcomes for ranking")
    else:
        result.update(pr_auc=float(average_precision_score(labels, scores)),
                      roc_auc=float(roc_auc_score(labels, scores)), status="measured")
    return result


def _calibration_bands(labels: np.ndarray, scores: np.ndarray) -> list[dict]:
    bands = []
    for band in range(10):
        lower, upper = band / 10, (band + 1) / 10
        members = (scores >= lower) & ((scores < upper) if upper < 1 else (scores <= 1))
        subset = labels[members]
        positives = int(subset.sum())
        sufficient = len(subset) >= 30 and positives >= 5 and len(subset) - positives >= 5
        bands.append({
            "band": f"{lower:.1f}-{upper:.1f}", "n": len(subset),
            "declines": positives,
            "mean_score": float(scores[members].mean()) if len(subset) else None,
            "observed_rate": float(subset.mean()) if sufficient else None,
            "status": "measured" if sufficient else "insufficient outcomes",
        })
    return bands


def _thresholds(labels: np.ndarray, scores: np.ndarray,
                initiators: np.ndarray) -> list[dict]:
    if len(labels) == 0 or not labels.any():
        raise ValueError("threshold window has no declines")
    result = []
    ranked = np.sort(scores)[::-1]
    for requested in RATES:
        position = max(1, math.ceil(requested * len(scores))) - 1
        cut = float(ranked[position])
        escalated = scores >= cut
        record = {
            "requested_rate": requested, "score_cut": cut,
            "actual_rate": float(escalated.mean()),
            "decline_recall": float(labels[escalated].sum() / labels.sum()),
        }
        for initiator in ("agent", "human"):
            subset = initiators == initiator
            positives = int(labels[subset].sum())
            record[f"{initiator}_rate"] = float(escalated[subset].mean()) if subset.any() else None
            record[f"{initiator}_decline_recall"] = (
                float(labels[subset & escalated].sum() / positives) if positives else None
            )
        result.append(record)
    return result


def _render_table(rows: list[tuple[str, dict]]) -> str:
    lines = ["| Slice | Rows | Declines | PR-AUC | ROC-AUC | Brier | Constant Brier |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, values in rows:
        def cell(key: str) -> str:
            value = values.get(key)
            return "unavailable" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)
        lines.append("| " + " | ".join([name] + [cell(key) for key in
            ("n", "declines", "pr_auc", "roc_auc", "brier", "baseline_brier")]) + " |")
    return "\n".join(lines)


def main() -> None:
    for target in (ARTIFACT, MANIFEST, REPORT):
        if target.exists():
            raise FileExistsError(f"M2 output already exists: {target}")
    split = _load_split()
    started = perf_counter()
    matrix, labels, meta, names = _data(split)
    loaded_s = perf_counter() - started
    seen = meta["population"] == "seen"
    windows = {name: meta["window"] == name for name in split["windows_utc_half_open"]}
    fit = seen & windows["fit"]
    may = seen & windows["select"]
    refit = fit | may
    calibrate = seen & windows["calibrate"]
    threshold = seen & windows["threshold"]
    july = windows["evaluate"]
    for name, mask in (("fit", fit), ("may", may), ("refit", refit),
                       ("calibrate", calibrate), ("threshold", threshold), ("july", july)):
        if not mask.any() or len(np.unique(labels[mask])) != 2:
            raise ValueError(f"{name}: missing rows or one label class")

    candidates = {}
    fit_prevalence = float(labels[fit].mean())
    for name in ("lr", "catboost"):
        model = _candidate(name, split["seed"])
        model.fit(matrix[fit], labels[fit])
        scores = _probabilities(model, matrix[may])
        candidates[name] = _metrics(labels[may], scores, fit_prevalence)
        print(name, "May", candidates[name])
    selected = max(("lr", "catboost"), key=lambda name: (candidates[name]["pr_auc"],
                                                       name == "lr"))
    model = _candidate(selected, split["seed"])
    model.fit(matrix[refit], labels[refit])
    refit_prevalence = float(labels[refit].mean())

    calibration_input = _probabilities(model, matrix[calibrate])
    clipped = np.clip(calibration_input, 1e-6, 1 - 1e-6)
    calibration_logits = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500,
                                    random_state=split["seed"])
    calibrator.fit(calibration_logits, labels[calibrate])

    def calibrated(mask: np.ndarray) -> np.ndarray:
        raw = np.clip(_probabilities(model, matrix[mask]), 1e-6, 1 - 1e-6)
        scores = calibrator.predict_proba(np.log(raw / (1 - raw)).reshape(-1, 1))[:, 1]
        if not np.isfinite(scores).all() or ((scores < 0) | (scores > 1)).any():
            raise ValueError("calibrator produced invalid scores")
        return scores

    june_scores = calibrated(threshold)
    proposals = _thresholds(labels[threshold], june_scores, meta["initiator"][threshold])
    result_rows = []
    calibration = {}
    july_proposals = {}
    for population in ("reserved", "seen"):
        cohort = july & (meta["population"] == population)
        passes = cohort & meta["issuer_pass"]
        slices = [
            (f"{population}: issuer-rule-pass proxy", passes),
            (f"{population}: card lifecycle violation", cohort & (meta["card_status"] != "active")),
            (f"{population}: all purchases", cohort),
            (f"{population}: agent purchases", cohort & (meta["initiator"] == "agent")),
            (f"{population}: human purchases", cohort & (meta["initiator"] == "human")),
            (f"{population}: zero prior customer approvals", cohort & (meta["customer_approved"] == 0)),
            (f"{population}: low support 1-5", cohort & (meta["customer_approved"] >= 1)
             & (meta["customer_approved"] <= 5)),
            (f"{population}: new card, known customer", cohort & (meta["card_approved"] == 0)
             & (meta["customer_approved"] > 0)),
        ]
        for name, mask in slices:
            scores = calibrated(mask) if mask.any() else np.asarray([], dtype=float)
            result_rows.append((name, _metrics(labels[mask], scores, refit_prevalence)))
            if name.endswith(("issuer-rule-pass proxy", "all purchases",
                              "agent purchases", "human purchases")):
                calibration[name] = _calibration_bands(labels[mask], scores)
        july_scores = calibrated(cohort)
        july_proposals[population] = [
            {"june_requested_rate": item["requested_rate"],
             "june_score_cut": item["score_cut"],
             "july_actual_rate": float((july_scores >= item["score_cut"]).mean()),
             "july_agent_rate": float((july_scores[meta["initiator"][cohort] == "agent"]
                                        >= item["score_cut"]).mean()),
             "july_human_rate": float((july_scores[meta["initiator"][cohort] == "human"]
                                        >= item["score_cut"]).mean())}
            for item in proposals
        ]

    EVAL.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "calibrator": calibrator, "feature_names": names,
                 "feature_schema_version": FEATURE_SCHEMA_VERSION,
                 "selected_candidate": selected}, ARTIFACT)
    artifact_hash = _sha256(ARTIFACT)
    manifest = {
        "schema_version": "model-eval-1",
        "artifact_sha256": artifact_hash,
        "artifact_path": str(ARTIFACT.relative_to(ROOT)),
        "artifact_release_status": "evaluation_only_no_operational_threshold",
        "input_sha256": split["input_sha256"],
        "split_manifest_sha256": _sha256(SPLIT),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": list(names),
        "candidate_configurations": {
            "lr": {"C": 1.0, "solver": "lbfgs", "max_iter": 500},
            "catboost": {"iterations": 300, "depth": 5, "learning_rate": 0.05,
                         "l2_leaf_reg": 3.0, "thread_count": 4},
        },
        "selected_candidate": selected,
        "selection_metric": "May average precision, fixed LR tie-break",
        "calibration_method": "L2 logistic regression on clipped model log-odds, June 1-15",
        "threshold_status": "proposals_only_owner_O4_pending",
        "library_versions": {"numpy": np.__version__, "scikit-learn": sklearn.__version__,
                             "catboost": catboost.__version__},
        "fit_customer_count": len(split["fitting_customers"]),
        "reserved_customer_count": len(split["reserved_customers"]),
        "calibration_bands": calibration,
        "june_threshold_proposals": proposals,
        "july_rates_at_june_proposals": july_proposals,
    }
    with MANIFEST.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        stream.write("\n")

    baseline = _render_table(result_rows)
    may = _render_table([(name, values) for name, values in candidates.items()])
    proposal_lines = [
        "| Requested June rate | Score cut | Actual June rate | Decline recall | Agent rate | Agent recall | Human rate | Human recall |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in proposals:
        proposal_lines.append("| " + " | ".join(f"{item[key]:.4f}" for key in (
            "requested_rate", "score_cut", "actual_rate", "decline_recall",
            "agent_rate", "agent_decline_recall", "human_rate", "human_decline_recall")) + " |")
    lines = [
        "# M2 behavioural-model comparison",
        "",
        f"Additional-pack purchases: {len(labels):,}. Frozen split: 400 fitting and 100 reserved customers, seed {split['seed']}.",
        "Base-pack customers never enter fitting, calibration or threshold proposals. Reserved customers' earlier outcomes only construct their own strictly pre-event profiles; they never fit parameters or choose a model, calibrator or cut.",
        f"Data loading and feature derivation: {loaded_s:.2f} seconds. Feature schema: {FEATURE_SCHEMA_VERSION}, {len(names)} numeric keys.",
        f"The refit majority class is approve, with constant-class accuracy {1 - refit_prevalence:.4f}; table baseline Brier uses the refit decline prevalence {refit_prevalence:.4f}.",
        "Only numeric HistoryFeatures.values enter the estimators. IDs and persona fields are grouping metadata, never predictors.",
        "", "## May candidate comparison", "",
        "Candidates fit on seen customers through April. May selects by PR-AUC with an LR tie-break.",
        may, "", f"Selected: `{selected}`. Refit on seen customers through May, then calibrate on June 1-15.",
        "", "## July evaluation", "",
        "Reserved-customer rows lead as the primary generalization estimate. Seen-customer rows are selection-informed.",
        "The issuer-rule-pass proxy uses recorded card status, online/international switches, transaction limit and reconstructed account calendar-month approved purchase spend. It is not a complete mandate-rule evaluation.",
        baseline, "",
        "July zero-prior-approved customer rows are absent. Low-support and new-card slices are distinct. Slices below 30 rows or five outcomes per class have unavailable ranking metrics; sparse score bands do not claim calibration.",
        "Sparse-slice Brier values are descriptive, not evidence of calibrated scores. Calibration by 0.1-wide score band for all, issuer-pass, agent and human slices, plus per-initiator July rates, is in model-manifest.json.",
        "", "## June escalation proposals", "",
        "These are evaluation points from June 16-30 only. No operational threshold is approved or enabled.",
        "\n".join(proposal_lines), "",
        "July reserved and seen rates at each unchanged June score cut are in model-manifest.json. July did not select a candidate or cut.",
        "", "## Artifact and limits", "",
        f"Evaluation-only artifact SHA-256 `{artifact_hash}`. Manifest SHA-256 `{_sha256(MANIFEST)}`.",
        "A missing or incompatible artifact must stop a model-enabled startup. There is no score default or substitute model.",
        "Historical status is decline propensity, not an authorization recommendation. Model effects remain off pending owner threshold O4 and engine/runner integration.",
        "No live simulator, app, customer answer or model-enabled decision was exercised by this fitting command.",
    ]
    with REPORT.open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    print(f"additional purchase rows {len(labels)}, selected {selected}, artifact {artifact_hash}")
    print(f"reserved July issuer-pass {result_rows[0][1]}")
    print(f"report {REPORT}")


if __name__ == "__main__":
    main()
