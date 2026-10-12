"""Download the pinned front-end libraries from the npm registry into ``strategy_lab/ui/static/vendor/``.

The pages load these from the jsDelivr CDN (pinned versions) unless a local copy exists; this script makes the
UI work offline or where the CDN is blocked. Each tarball is checked against the registry's SHA-512 integrity
value before anything is extracted. Run by ``make setup``; safe to re-run.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "strategy_lab" / "ui" / "static" / "vendor"
# package, version, file inside the tarball, local name — keep in sync with strategy_lab/ui/assets.py
ASSETS = [
    ("htmx.org", "2.0.4", "package/dist/htmx.min.js", "htmx.min.js"),
    (
        "lightweight-charts",
        "4.2.3",
        "package/dist/lightweight-charts.standalone.production.js",
        "lightweight-charts.standalone.production.js",
    ),
    ("plotly.js-dist-min", "2.35.2", "package/plotly.min.js", "plotly.min.js"),
]


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # fixed https registry URLs only
        data: bytes = response.read()
        return data


def vendor(package: str, version: str, member: str, name: str) -> None:
    target = VENDOR / name
    if target.exists():
        print(f"ok      {name} (already present)")
        return
    meta = json.loads(fetch(f"https://registry.npmjs.org/{package}/{version}"))
    algo, _, expected = meta["dist"]["integrity"].partition("-")
    if algo != "sha512":
        raise RuntimeError(f"{package}: unexpected integrity algorithm {algo}")
    tarball = fetch(meta["dist"]["tarball"])
    if base64.b64encode(hashlib.sha512(tarball).digest()).decode() != expected:
        raise RuntimeError(f"{package}@{version}: integrity check failed")
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
        extracted = archive.extractfile(member)
        if extracted is None:
            raise RuntimeError(f"{package}: {member} not in the tarball")
        target.write_bytes(extracted.read())
    print(f"vendored {name} from {package}@{version} (sha512 verified)")


def main() -> None:
    VENDOR.mkdir(parents=True, exist_ok=True)
    for asset in ASSETS:
        try:
            vendor(*asset)
        except Exception as exc:  # report and continue: the pages fall back to the CDN
            print(f"skipped {asset[3]}: {exc} — the UI will load it from the CDN", file=sys.stderr)


if __name__ == "__main__":
    main()
