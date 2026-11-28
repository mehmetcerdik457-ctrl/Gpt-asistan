#!/usr/bin/env python3
"""KRAL server-only OpenAI model inventory; no billable model calls.

Default execution is completely offline. --check-api performs an explicitly
requested read-only GET /v1/models using an already configured server key.
Returned catalog presence is NOT proof that Responses API invocation is allowed.
No key, response body, owner ID, or private data is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

API_MODELS_URL = "https://api.openai.com/v1/models"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9._:/-]{1,160}\Z")

# Names directly documented by the official OpenAI API model catalog,
# as checked November 3, 2026; not a statement about user project access.
DOCUMENTED = (
    "gpt-6-astra", "gpt-6-sol", "gpt-6-luna",
    "gpt-6.1-sol", "gpt-6.1-terra", "gpt-5.6-sol",
)


class CatalogError(ValueError):
    pass


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise CatalogError("API_REDIRECT_DENIED")


def parse_catalog(raw: bytes) -> set[str]:
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise CatalogError("API_CATALOG_SIZE_INVALID")
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError):
        raise CatalogError("API_CATALOG_INVALID") from None
    if not isinstance(doc, dict) or doc.get("object") != "list":
        raise CatalogError("API_CATALOG_INVALID")
    values = doc.get("data")
    if not isinstance(values, list) or len(values) > 5000:
        raise CatalogError("API_CATALOG_INVALID")
    found = set()
    for model in values:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            raise CatalogError("API_CATALOG_INVALID")
        model_id = model["id"]
        if not ID.fullmatch(model_id) or model_id in found:
            raise CatalogError("API_CATALOG_INVALID")
        found.add(model_id)
    return found


def read_project_catalog(key: str, *, opener=None) -> set[str]:
    """No Responses create call; never follow redirects to other hosts."""
    if not isinstance(key, str) or not key.strip():
        raise CatalogError("API_KEY_NOT_CONFIGURED")
    request = urllib.request.Request(
        API_MODELS_URL, method="GET",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json",
                 "User-Agent": "kral-readonly-model-inventory/1.0"},
    )
    transport = opener if opener is not None else urllib.request.build_opener(RejectRedirects())
    try:
        with transport.open(request, timeout=10) as response:
            if response.status != 200:
                raise CatalogError("API_CATALOG_HTTP_ERROR")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()  # Do not print the upstream body, which could contain secrets.
        if status == 401:
            raise CatalogError("API_KEY_ACCESS_DENIED") from None
        if status == 403:
            raise CatalogError("API_PROJECT_PERMISSION_DENIED") from None
        if status == 429:
            raise CatalogError("API_RATE_LIMITED") from None
        raise CatalogError("API_CATALOG_HTTP_ERROR") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise CatalogError("API_NETWORK_UNAVAILABLE") from None
    return parse_catalog(raw)


def collect_inventory(environ=None, *, check_api: bool = False, opener=None) -> dict:
    env = os.environ if environ is None else environ
    allowed = tuple(x.strip() for x in env.get("OPENAI_ALLOWED_MODELS", "").split(",") if x.strip())
    allowlist_valid = len(allowed) <= 4 and all(ID.fullmatch(x) for x in allowed)
    key = env.get("OPENAI_API_KEY", "")
    configured = bool(isinstance(key, str) and key.strip())
    listed = None
    catalog_result = "NOT_CHECKED"
    if check_api:
        try:
            listed = read_project_catalog(key, opener=opener)
            catalog_result = "READ_ONLY_GET_SUCCEEDED_NOT_LIVE_VERIFIED"
        except CatalogError as exc:
            catalog_result = str(exc)
    rows = [
        {
            "model_id": model,
            "official_catalog_documented": True,
            "configured_in_gateway_allowlist": model in allowed if allowlist_valid else False,
            "listed_in_connected_api_project": model in listed if listed is not None else None,
            "responses_call_verified": False,
        }
        for model in DOCUMENTED
    ]
    return {
        "mode": "READ_ONLY_GET" if check_api else "OFFLINE_NO_NETWORK",
        "key_present_server_side": configured,
        "gateway_allowlist_valid": allowlist_valid,
        "gateway_allowlist_count": len(allowed),
        "gateway_max_active_models": 4,
        "catalog_result": catalog_result,
        "models": rows,
        "live_responses_calls_made": 0,
        "account_entitlement_fully_verified": False,
        "keys_created_or_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-api", action="store_true",
        help="Opt in to read-only GET /v1/models; never invokes Responses or tools",
    )
    args = parser.parse_args()
    result = collect_inventory(check_api=args.check_api)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 2 if args.check_api and result["catalog_result"] != "READ_ONLY_GET_SUCCEEDED_NOT_LIVE_VERIFIED" else 0


if __name__ == "__main__":
    sys.exit(main())
