#!/usr/bin/env python3
"""Check Supabase REST/Auth reachability without changing the project.

The checker performs read-only HTTP probes. It never applies SQL, prints keys,
or treats an unauthorized protected-table response as proof that a table exists.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

TABLES = ("profiles", "chat_sessions", "messages", "feedback", "bookmarks")


@dataclass(frozen=True)
class Probe:
    name: str
    url: str
    status: int | None
    detail: str


def _base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("SUPABASE_URL must be an http(s) project URL")
    return value


def _headers(key: str) -> dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _probe(client: httpx.Client, name: str, url: str, key: str) -> Probe:
    try:
        response = client.get(url, headers=_headers(key))
    except httpx.HTTPError as exc:
        return Probe(name, url, None, f"network error: {exc.__class__.__name__}")

    if response.status_code == 404:
        detail = "not found (check URL or schema)"
    elif response.status_code in {401, 403}:
        detail = "reachable but unauthorized for this key"
    elif response.status_code >= 400:
        detail = f"HTTP {response.status_code}"
    else:
        detail = f"HTTP {response.status_code}"
    return Probe(name, url, response.status_code, detail)


def run(url: str, key: str, timeout: float) -> int:
    root = _base_url(url)
    headers_key = key.strip()
    if not headers_key:
        raise ValueError(
            "set SUPABASE_ANON_KEY, SUPABASE_PUBLISHABLE_KEY, or SUPABASE_SERVICE_ROLE_KEY"
        )

    probes: list[Probe] = []
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        probes.append(_probe(client, "REST API", f"{root}/rest/v1/", headers_key))
        probes.append(_probe(client, "Auth API", f"{root}/auth/v1/settings", headers_key))
        for table in TABLES:
            probes.append(
                _probe(
                    client,
                    f"table {table}",
                    f"{root}/rest/v1/{table}?select=*&limit=1",
                    headers_key,
                )
            )

    failures = 0
    for probe in probes:
        # URLs contain only the configured host and endpoint; never include headers
        # or response bodies.
        print(f"{probe.name}: {probe.detail}")
        if probe.status is None or probe.status >= 500 or probe.status == 404:
            failures += 1

    table_results = [probe for probe in probes if probe.name.startswith("table ")]
    missing = [probe.name.removeprefix("table ") for probe in table_results if probe.status == 404]
    if missing:
        print(
            f"MISSING SCHEMA: {', '.join(missing)}; "
            "run supabase/schema.sql in SQL Editor or via CLI."
        )
        failures += 1
    elif any(probe.status in {401, 403} for probe in table_results):
        print(
            "TABLE ACCESS: protected rows require a user JWT or a trusted "
            "service-role key; endpoint existence is not confirmed for "
            "unauthorized probes."
        )

    if failures:
        print("Supabase check: FAIL (read-only; no schema changes were made).")
        return 1
    print("Supabase check: PASS (read-only; required endpoints responded).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds (default: 10)",
    )
    args = parser.parse_args()
    url = os.getenv("SUPABASE_URL", "")
    key = (
        os.getenv("SUPABASE_ANON_KEY", "")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    try:
        return run(url, key, args.timeout)
    except (ValueError, httpx.HTTPError) as exc:
        print(f"Supabase check: CONFIGURATION ERROR ({exc})")
        return 2


if __name__ == "__main__":
    sys.exit(main())
