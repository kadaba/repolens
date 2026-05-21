"""Stdlib HTTP wrapper for LLM adapters. Pure urllib — zero deps."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

DEFAULT_TIMEOUT_SEC = 30.0
DEFAULT_RETRIES = 1
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


def post_json(
    url: str,
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    retries: int = DEFAULT_RETRIES,
) -> Optional[Dict[str, Any]]:
    """POST JSON, return parsed dict. Returns None on non-retryable failure.

    - One retry on transient 5xx and 429 (with 2s backoff).
    - Returns None on 4xx (except 429), network errors after retries exhausted.
    - Never raises — adapters expect Optional handling per design contract.
    """
    payload = json.dumps(body).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=payload, headers=req_headers, method="POST")

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.getcode()
                raw = resp.read()
                if status >= 400:
                    if status in RETRYABLE_STATUSES and attempt < retries:
                        time.sleep(2.0)
                        continue
                    return None
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in RETRYABLE_STATUSES and attempt < retries:
                time.sleep(2.0)
                continue
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt < retries:
                time.sleep(2.0)
                continue
            return None
    return None
