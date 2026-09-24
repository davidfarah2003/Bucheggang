"""Static customer app assets for the shared FastAPI shell."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


REPO_ROOT = Path(__file__).resolve().parents[3]


def mount_customer_app(api: FastAPI) -> None:
    """Expose the customer UI."""
    app_dir = REPO_ROOT / "app"
    if not (app_dir / "index.html").is_file():
        raise FileNotFoundError(f"Customer app entrypoint is missing: {app_dir / 'index.html'}")

    api.mount("/app", StaticFiles(directory=app_dir, html=True), name="customer-app")
