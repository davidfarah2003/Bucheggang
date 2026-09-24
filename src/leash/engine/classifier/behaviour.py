"""Load and score one versioned evaluation-only history model."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import catboost
import joblib
import numpy as np
import sklearn

from .types import BehaviorAssessment, FEATURE_SCHEMA_VERSION, HistoryFeatures

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MANIFEST = ROOT / "docs" / "eval" / "classifier" / "model-manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BehaviorModel:
    """Explicit evaluation configuration; this class never enables escalation."""

    def __init__(self, manifest_path: Path = DEFAULT_MANIFEST):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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
        self.model_id = manifest["selected_candidate"]
        self.artifact_version = artifact_hash

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
        return BehaviorAssessment(
            score=float(calibrated[0, 1]), model_id=self.model_id,
            artifact_version=self.artifact_version,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            support=features.support.copy(), escalation_fired=False,
        )
