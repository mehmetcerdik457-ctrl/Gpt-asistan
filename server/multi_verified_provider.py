"""Opt-in, single-owner provider pool for KRAL's EXISTING gateway.

The pool never performs inference for discovery. Individual providers still
use their own API credentials, model allowlists, no-redirect validation, and
quota / security policy. All provider probes are disabled unless the owner
has explicitly allowed potentially billable multi-provider requests.

A pool permits choice between independently *actually verified* models;
it is NOT an automatic cross-provider transfer of personal context.
"""
from __future__ import annotations

import os

from .gateway import Denied

PROVIDERS = ("openai", "owner_gateway", "cloudflare_workers_ai")
MAX_DISCOVERY_MODELS = 4


class VerifiedProviderPool:
    name = "verified_pool"

    def __init__(self, providers=None, environ=None):
        self.env = os.environ if environ is None else environ
        if providers is None:
            # Lazy construction preserves existing single-provider startup.
            from .gateway import OpenAIProvider
            from .owner_gateway_provider import OwnerGatewayProvider
            from .cloudflare_workers_ai_provider import CloudflareWorkersAIProvider
            providers = {
                "openai": OpenAIProvider(),
                "owner_gateway": OwnerGatewayProvider(self.env),
                "cloudflare_workers_ai": CloudflareWorkersAIProvider(self.env),
            }
        self.providers = providers

    def _selected(self):
        e = self.env
        if (e.get("KRAL_MULTI_ROUTER_APPROVED") != "YES" or
                e.get("KRAL_MULTI_COST_APPROVED") != "YES"):
            return ()
        raw = e.get("KRAL_MULTI_PROVIDERS", "")
        names = tuple(s.strip() for s in raw.split(","))
        if (not names or len(names) > len(PROVIDERS) or
                len(set(names)) != len(names) or
                any(n not in PROVIDERS or n not in self.providers for n in names)):
            return ()
        return names

    def configured(self):
        return any(self.providers[name].configured() for name in self._selected())

    def candidates(self):
        if not self.configured():
            raise Denied("MULTI_ROUTER_NOT_APPROVED_OR_CONFIGURED", 503)
        results = []
        for name in self._selected():
            provider = self.providers[name]
            if not provider.configured():
                continue
            for candidate in provider.candidates():
                results.append((name, candidate))
                if len(results) > MAX_DISCOVERY_MODELS:
                    raise Denied("MULTI_MODEL_BUDGET_EXCEEDED", 503)
        return tuple(results)

    def provider_name_for(self, candidate):
        if (not isinstance(candidate, tuple) or len(candidate) != 2 or
                not all(isinstance(x, str) for x in candidate)):
            raise Denied("MULTI_ROUTE_INVALID", 403)
        name, _ = candidate
        if name not in self._selected() or name not in self.providers:
            raise Denied("MULTI_ROUTE_DENIED", 403)
        return name

    def reply(self, candidate, message, *, probe=False):
        name = self.provider_name_for(candidate)
        model = candidate[1]
        provider = self.providers[name]
        if not provider.configured() or model not in provider.candidates():
            raise Denied("MULTI_ROUTE_NOT_CONFIGURED", 503)
        return provider.reply(model, message, probe=probe)
