"""Offline readiness, read-only model catalog, or one explicitly authorized paid probe.

The --approve-paid flag records the caller's choice; it does not grant authority.
Obtain explicit user consent before selecting --live. No mode retries a request.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

from server.gateway import Denied, OpenAIProvider
from server.openai_config import api_key
from server.openai_model_inventory import CatalogError, read_project_catalog


FIXTURE_INPUT = "Reply with exactly KRAL_OK."
FIXTURE_OUTPUT = "KRAL_OK"
_SAFE_ERRORS = frozenset({
    "MODEL_CONFIGURATION_INVALID", "PROVIDER_NOT_CONFIGURED", "PROVIDER_AUTH_DENIED",
    "PROVIDER_MODEL_OR_PERMISSION_DENIED", "PROVIDER_MODEL_NOT_AVAILABLE",
    "PROVIDER_QUOTA_OR_RATE_LIMIT", "PROVIDER_HTTP_FAILURE", "PROVIDER_CONNECTION_FAILED",
    "PROVIDER_REDIRECT_DENIED", "PROVIDER_RESPONSE_TOO_LARGE", "PROVIDER_RESPONSE_INCOMPLETE",
    "PROVIDER_MODEL_MISSING", "PROVIDER_RESPONSE_ID_INVALID", "PROVIDER_TEXT_INVALID",
    "PROVIDER_RESPONSE_INVALID", "API_KEY_NOT_CONFIGURED", "API_KEY_ACCESS_DENIED",
    "API_PROJECT_PERMISSION_DENIED", "API_RATE_LIMITED", "API_CATALOG_HTTP_ERROR",
    "API_NETWORK_UNAVAILABLE", "API_REDIRECT_DENIED", "API_CATALOG_SIZE_INVALID",
    "API_CATALOG_INVALID",
})


def _error_code(error):
    code = error.code if isinstance(error, Denied) else str(error) if isinstance(error, CatalogError) else None
    return code if code in _SAFE_ERRORS else "ACCEPTANCE_CHECK_FAILED"


def run_acceptance(*, list_models=False, live=False, approve_paid=False, model=None):
    """Return redacted evidence and an exit code without retrying any operation."""
    mode = "LIVE_ONE_SHOT" if live else "READ_ONLY_MODEL_LIST" if list_models else "OFFLINE_READINESS"
    key = api_key()
    provider = OpenAIProvider()
    report = {
        "mode": mode, "status": "BLOCKED",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "key_present": bool(key), "allowlist_valid": False, "configured_models": [],
        "account_access": "NOT_VERIFIED", "model_access": "NOT_VERIFIED",
        "catalog_status": "NOT_CHECKED", "responses_attempted": 0, "errors": [],
    }
    try:
        allowed = provider.candidates()
        report["allowlist_valid"] = True
        report["configured_models"] = list(allowed)
    except Exception as error:
        report["errors"].append(_error_code(error))
        return report, 1 if live or list_models else 0

    if live and not approve_paid:
        report["errors"].append("PAID_APPROVAL_REQUIRED")
    elif approve_paid and not live:
        report["errors"].append("PAID_APPROVAL_REQUIRES_LIVE_MODE")
    if live and (not isinstance(model, str) or not model):
        report["errors"].append("EXPLICIT_MODEL_REQUIRED")
    elif live and model not in allowed:
        report["errors"].append("SELECTED_MODEL_NOT_ALLOWLISTED")
    if not key:
        report["errors"].append("PROVIDER_NOT_CONFIGURED")
    if not allowed and not list_models:
        report["errors"].append("MODEL_ALLOWLIST_EMPTY")
    if report["errors"]:
        return report, 1 if live or list_models or approve_paid else 0
    if not live and not list_models:
        report["status"] = "READY_FOR_AUTHORIZED_CHECK"
        return report, 0

    if list_models:
        try:
            catalog = read_project_catalog(key)
            report["catalog_status"] = "READ_ONLY_GET_SUCCEEDED"
            report["catalog_count"] = len(catalog)
            report["configured_models_listed"] = {name: name in catalog for name in allowed}
            report["account_access"] = "READ_ONLY_CATALOG_ACCESS_VERIFIED"
            report["model_access"] = "CATALOG_PRESENCE_ONLY_NOT_RESPONSES_VERIFIED"
            if not all(report["configured_models_listed"].values()):
                report["errors"].append("CONFIGURED_MODEL_NOT_LISTED")
                return report, 1
            report["status"] = "CATALOG_CHECK_PASSED"
            return report, 0
        except Exception as error:
            report["errors"].append(_error_code(error))
            return report, 1

    correlation_id = uuid.uuid4().hex
    report.update({"requested_model": model, "client_request_id": correlation_id,
                   "responses_attempted": 1})
    try:
        # Exactly one bounded synthetic request; no discovery probe, fallback or retry.
        text, actual_model, elapsed, metadata = provider.reply_with_metadata(
            model, FIXTURE_INPUT, probe=True,
            request_metadata={"request_id": correlation_id, "kral_acceptance": "oct26"},
            client_request_id=correlation_id,
        )
        response_id, request_id = metadata.get("response_id"), metadata.get("request_id")
        if (not isinstance(text, str) or not text.strip() or
                not isinstance(actual_model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,160}", actual_model) or
                not isinstance(response_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", response_id) or
                (request_id is not None and (not isinstance(request_id, str) or
                 not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", request_id))) or
                type(elapsed) is not int or elapsed < 0):
            report["errors"].append("LIVE_EVIDENCE_INVALID")
            return report, 1
        report.update({
            "response_id": response_id, "provider_request_id": request_id,
            "returned_model": actual_model, "model_matches_requested": actual_model == model,
            "latency_ms": elapsed, "output_nonempty": True,
            "output_matches_fixture": text.strip() == FIXTURE_OUTPUT,
            "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "account_access": "SINGLE_RESPONSES_REQUEST_SUCCEEDED",
            "model_access": "SINGLE_RESPONSES_REQUEST_VERIFIED",
        })
        if not report["output_matches_fixture"]:
            report["errors"].append("LIVE_FIXTURE_MISMATCH")
            return report, 1
        report["status"] = "LIVE_CHECK_PASSED"
        return report, 0
    except Exception as error:
        report["errors"].append(_error_code(error))
        return report, 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--list-models", action="store_true", help="Read-only GET /v1/models; no Responses calls")
    modes.add_argument("--live", action="store_true", help="One paid synthetic Responses probe; explicit consent required first")
    parser.add_argument("--approve-paid", action="store_true", help="Required with --live; does not replace explicit user consent")
    parser.add_argument("--model", help="Explicit allowlisted model for --live; never guessed or replaced")
    parser.add_argument("--output", help="Create a new redacted JSON evidence file; existing files are preserved")
    args = parser.parse_args(argv)
    evidence = None
    if args.output:
        try:
            # Reserve the evidence destination before any possible billable request.
            evidence = Path(args.output).open("x", encoding="utf-8")
        except OSError:
            print(json.dumps({"status": "BLOCKED", "responses_attempted": 0,
                              "errors": ["EVIDENCE_WRITE_FAILED"]}, sort_keys=True))
            return 1
    report, code = run_acceptance(list_models=args.list_models, live=args.live,
                                  approve_paid=args.approve_paid, model=args.model)
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if evidence is not None:
        try:
            with evidence:
                evidence.write(serialized)
        except OSError:
            report["errors"].append("EVIDENCE_WRITE_FAILED")
            report["status"] = "BLOCKED"
            serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            code = 1
    print(serialized, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
