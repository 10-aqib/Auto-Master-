"""The committed API contract must match the code (regenerate with `make contracts`)."""

from __future__ import annotations

import json
from pathlib import Path

from webforge_api.cli import openapi_contract

CONTRACT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.json"


def test_openapi_contract_is_up_to_date() -> None:
    committed = json.loads(CONTRACT.read_text())
    assert committed == json.loads(json.dumps(openapi_contract())), (
        "packages/contracts/openapi.json is stale; run `make contracts`"
    )


def test_only_versioned_and_health_routes_exposed() -> None:
    paths = openapi_contract()["paths"]
    assert isinstance(paths, dict)
    # Provider webhooks (Phase 09) are the only public, unversioned API routes; they require a valid
    # HMAC signature. The unsubscribe page (/u/...) is excluded from the schema.
    assert all(p.startswith(("/api/v1/", "/health/", "/webhooks/email/")) for p in paths)
