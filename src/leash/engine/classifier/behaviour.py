"""Load one versioned history model with an explicit operating-point selection."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import catboost
import joblib
import numpy as np
import sklearn

from leash.contracts import BehaviorAssessment, FEATURE_SCHEMA_VERSION, HistoryFeatures

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MANIFEST = ROOT / "docs" / "eval" / "classifier" / "model-manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BehaviorModel:
    """Score an explicit evaluation or selected operating-point configuration."""

    def __init__(self, manifest_path: Path = DEFAULT_MANIFEST):
        configuration_bytes = manifest_path.read_bytes()
        configuration = json.loads(configuration_bytes)
        threshold = None
        operating_id = None
        if "base_manifest" in configuration:
            relative = Path(configuration["base_manifest"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("operating point base manifest leaves the repository")
            base_path = (ROOT / relative).resolve()
            if not base_path.is_relative_to(ROOT.resolve()):
                raise ValueError("operating point base manifest symlink leaves the repository")
            base_bytes = base_path.read_bytes()
            if hashlib.sha256(base_bytes).hexdigest() != configuration["base_manifest_sha256"]:
                raise ValueError("operating point base manifest SHA-256 differs")
            if configuration["release_status"] != "o4_selected_pending_integrated_review":
                raise ValueError("operating point release status is unexpected")
            threshold = configuration["score_cut"]
            if type(threshold) is not float or not math.isfinite(threshold) or not 0 < threshold < 1:
                raise ValueError("operating point score cut must be a finite fraction")
            manifest = json.loads(base_bytes)
            if not any(
                proposal["requested_rate"] == configuration["requested_june_rate"]
                and proposal["score_cut"] == threshold
                for proposal in manifest["june_threshold_proposals"]
            ):
                raise ValueError("operating point differs from the frozen June proposals")
            operating_id = hashlib.sha256(configuration_bytes).hexdigest()[:16]
        else:
            manifest = configuration
        if manifest["feature_schema_version"] != FEATURE_SCHEMA_VERSION:
            raise ValueError("model manifest has an incompatible feature schema")
        if manifest["artifact_release_status"] != "evaluation_only_no_operational_threshold":
            raise ValueError("model artifact release status is unexpected")
        if manifest["threshold_status"] != "proposals_only_owner_O4_pending":
            raise ValueError("model threshold status is unexpected")
        versions = {"numpy": np.__version__, "scikit-learn": sklearn.__version__,
                    "catboost": catboost.__version__}
        if manifest["library_versions"] != versions:
            raise ValueError(f"model library versions differ: installed {versions}, expected {manifest['library_versions']}")
        relative = Path(manifest["artifact_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("model artifact path leaves the repository")
        artifact_path = (ROOT / relative).resolve()
        if not artifact_path.is_relative_to(ROOT.resolve()):
            raise ValueError("model artifact symlink leaves the repository")
        artifact_hash = _sha256(artifact_path)
        if artifact_hash != manifest["artifact_sha256"]:
            raise ValueError("model artifact SHA-256 differs from manifest")
        split_path = ROOT / "docs" / "eval" / "classifier" / "split-manifest.json"
        if _sha256(split_path) != manifest["split_manifest_sha256"]:
            raise ValueError("model split manifest SHA-256 changed")
        if manifest["selected_candidate"] not in {"lr", "catboost"}:
            raise ValueError("model manifest names an unsupported candidate")
        loaded = joblib.load(artifact_path)
        if loaded["feature_schema_version"] != FEATURE_SCHEMA_VERSION:
            raise ValueError("model artifact has an incompatible feature schema")
        if loaded["selected_candidate"] != manifest["selected_candidate"]:
            raise ValueError("model artifact candidate differs from manifest")
        names = tuple(manifest["feature_names"])
        if not names or tuple(loaded["feature_names"]) != names or len(set(names)) != len(names):
            raise ValueError("model artifact feature names differ from manifest")
        self._model = loaded["model"]
        self._calibrator = loaded["calibrator"]
        self.feature_names = names
        self.model_id = (manifest["selected_candidate"] if operating_id is None
                         else f"{manifest['selected_candidate']}:o4:{operating_id}")
        self.artifact_version = artifact_hash
        self._threshold = threshold

    def score(self, features: HistoryFeatures) -> BehaviorAssessment:
        if features.schema_version != FEATURE_SCHEMA_VERSION:
            raise ValueError("purchase feature schema differs from model")
        if tuple(sorted(features.values)) != self.feature_names:
            raise ValueError("purchase feature names differ from model")
        vector = np.asarray([
            np.nan if features.values[name] is None else features.values[name]
            for name in self.feature_names
        ], dtype=np.float64).reshape(1, -1)
        if not np.isfinite(vector[~np.isnan(vector)]).all():
            raise ValueError("purchase has a non-finite history feature")
        raw = np.asarray(self._model.predict_proba(vector))
        if (raw.shape != (1, 2) or not np.isfinite(raw).all()
                or ((raw < 0) | (raw > 1)).any()
                or not math.isclose(float(raw.sum()), 1.0, rel_tol=0, abs_tol=1e-6)):
            raise ValueError("history model returned an invalid distribution")
        clipped = float(np.clip(raw[0, 1], 1e-6, 1 - 1e-6))
        logit = math.log(clipped / (1 - clipped))
        calibrated = np.asarray(self._calibrator.predict_proba([[logit]]))
        if (calibrated.shape != (1, 2) or not np.isfinite(calibrated).all()
                or ((calibrated < 0) | (calibrated > 1)).any()
                or not math.isclose(float(calibrated.sum()), 1.0, rel_tol=0, abs_tol=1e-6)):
            raise ValueError("history calibrator returned an invalid distribution")
        score = float(calibrated[0, 1])
        return BehaviorAssessment(
            score=score, model_id=self.model_id,
            artifact_version=self.artifact_version,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            support=features.support.copy(),
            escalation_fired=self._threshold is not None and score >= self._threshold,
        )
