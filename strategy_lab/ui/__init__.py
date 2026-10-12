"""Web UI assets: templates, static files, and the front-end libraries (pinned CDN or a vendored copy)."""

from __future__ import annotations

from pathlib import Path

UI_DIR = Path(__file__).resolve().parent
STATIC_DIR = UI_DIR / "static"
TEMPLATES_DIR = UI_DIR / "templates"

# name -> (local file under static/vendor, pinned CDN URL); versions match scripts/vendor_assets.py
ASSETS = {
    "htmx": ("htmx.min.js", "https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js"),
    "lightweight-charts": (
        "lightweight-charts.standalone.production.js",
        "https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js",
    ),
    "plotly": ("plotly.min.js", "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"),
}


def asset_url(name: str) -> str:
    """The vendored copy when ``make setup`` downloaded it, else the pinned CDN URL."""
    local, cdn = ASSETS[name]
    return f"/static/vendor/{local}" if (STATIC_DIR / "vendor" / local).exists() else cdn
