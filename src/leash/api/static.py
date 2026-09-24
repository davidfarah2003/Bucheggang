"""Static customer app assets for the shared FastAPI shell."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


REPO_ROOT = Path(__file__).resolve().parents[3]


def mount_customer_app(api: FastAPI) -> None:
    """Expose the customer UI and its temporary policy sample."""
    app_dir = REPO_ROOT / "app"
    sample_dir = REPO_ROOT / "docs" / "samples"
    if not (app_dir / "index.html").is_file():
        raise FileNotFoundError(f"Customer app entrypoint is missing: {app_dir / 'index.html'}")
    if not (sample_dir / "scen0002_draft.json").is_file():
        raise FileNotFoundError(f"Policy sample is missing: {sample_dir / 'scen0002_draft.json'}")
    api.mount("/docs/samples", StaticFiles(directory=sample_dir), name="policy-samples")
    api.mount("/app", StaticFiles(directory=app_dir, html=True), name="customer-app")
