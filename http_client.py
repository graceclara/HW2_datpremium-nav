from __future__ import annotations

import httpx


def get_client() -> httpx.AsyncClient:
    # Keep it simple: a single, shared-ish client per request scope.
    # (We instantiate per call site to avoid lifecycle complexity here.)
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={
            "User-Agent": "dat-premium-nav/1.0 (+https://example.local)",
            "Accept": "*/*",
        },
        follow_redirects=True,
    )
