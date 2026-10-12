"""Shared HTTP download helpers: retries with backoff, HTTP 429 handling, SHA-256, parallel fetch.

Downloads go to ``data/raw/<source>/...`` and are skipped when already present (and, where a checksum is
known, verified). A host blocked by an egress proxy surfaces as ``SourceUnavailableError`` so the pipeline can
record it and move to the next fallback instead of crashing.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "strategy-lab/0.1 (backtest research; contact: repository owner)"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class SourceUnavailableError(RuntimeError):
    """The host could not be reached at all (DNS, TLS, proxy policy) — try the next source."""


class NotFoundError(RuntimeError):
    """HTTP 404 — e.g. a monthly file that does not exist (yet)."""


@dataclass(frozen=True)
class Download:
    url: str
    path: Path
    sha256: str | None = None


def client(timeout_s: float = 60.0) -> httpx.Client:
    return httpx.Client(timeout=timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_with_retries(
    http: httpx.Client,
    url: str,
    params: dict[str, Any] | None = None,
    attempts: int = 5,
    base_delay_s: float = 2.0,
) -> httpx.Response:
    """GET with exponential backoff on 429/5xx and transient network errors.

    ``Retry-After`` is honoured on 429. Proxy refusals (403 on CONNECT) are not retried: they are policy.
    """
    for attempt in range(1, attempts + 1):
        try:
            response = http.get(url, params=params)
        except httpx.ProxyError as exc:
            raise SourceUnavailableError(f"{url}: proxy refused ({exc})") from exc
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            if attempt == attempts:
                raise SourceUnavailableError(f"{url}: cannot connect ({exc})") from exc
            time.sleep(base_delay_s * 2 ** (attempt - 1))
            continue
        except (httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ReadError) as exc:
            if attempt == attempts:
                raise
            log.warning("transient error on %s (%s); retrying", url, exc)
            time.sleep(base_delay_s * 2 ** (attempt - 1))
            continue
        if response.status_code == 404:
            raise NotFoundError(url)
        if response.status_code in RETRY_STATUSES and attempt < attempts:
            retry_after = response.headers.get("Retry-After")
            delay = (
                float(retry_after) if retry_after and retry_after.isdigit() else base_delay_s * 2 ** (attempt - 1)
            )
            log.warning("HTTP %s on %s; sleeping %.1fs", response.status_code, url, delay)
            time.sleep(delay)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError(f"unreachable: retries exhausted for {url}")  # pragma: no cover


def fetch_to_file(http: httpx.Client, item: Download) -> Path:
    """Download ``item`` unless an intact copy exists. Verifies ``sha256`` when given."""
    if item.path.exists() and (item.sha256 is None or sha256_file(item.path) == item.sha256):
        return item.path
    item.path.parent.mkdir(parents=True, exist_ok=True)
    tmp = item.path.with_suffix(item.path.suffix + ".part")
    response = request_with_retries(http, item.url)
    tmp.write_bytes(response.content)
    if item.sha256 is not None:
        actual = sha256_file(tmp)
        if actual != item.sha256:
            tmp.unlink()
            raise ValueError(f"checksum mismatch for {item.url}: expected {item.sha256}, got {actual}")
    tmp.replace(item.path)
    return item.path


def fetch_many(
    items: Iterable[Download],
    workers: int = 8,
    on_done: Callable[[Download, Path | Exception], None] | None = None,
) -> dict[str, Path | Exception]:
    """Download in parallel. Returns url -> path, or the exception for that file (never raises per file)."""
    results: dict[str, Path | Exception] = {}
    with client() as http, ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_to_file, http, item): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                outcome: Path | Exception = future.result()
            except Exception as exc:  # recorded per file; the caller decides what is fatal
                outcome = exc
            results[item.url] = outcome
            if on_done is not None:
                on_done(item, outcome)
    return results


def probe(url: str, timeout_s: float = 15.0) -> str | None:
    """Return None if ``url``'s host answers at all, else a short reason (used before bulk downloads)."""
    try:
        with client(timeout_s) as http:
            http.head(url)
    except httpx.ProxyError as exc:
        return f"blocked by proxy: {exc}"
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None
