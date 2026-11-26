"""AI providers for structured design briefs.

`AnthropicBriefModel` calls the Claude API through the official SDK with a strict JSON schema
(`output_config.format`) and no tools. `MockBriefModel` is a deterministic offline generator for
development and CI (labelled as mock; refused in production).

The default model and the price table below were checked on 2026-11-26 (see docs/versions.md).
Override the model with ANTHROPIC_MODEL. Refusals use server-side fallbacks
(`fallbacks: "default"`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from webforge_api.config import Settings
from webforge_api.design.brief_schema import SCHEMA_VERSION, api_json_schema

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# USD cents per million tokens (input, output). Unknown models are priced at the most expensive
# listed rate so budgets fail safe.
PRICES_MINOR_PER_MTOK: dict[str, tuple[int, int]] = {
    "claude-opus-5-5": (400, 2000),
    "claude-opus-5": (500, 2500),
    "claude-opus-4-8": (500, 2500),
    "claude-sonnet-5-5": (200, 1000),
    "claude-sonnet-5": (200, 1000),
    "claude-haiku-5-5": (10, 50),
    "claude-fable-5-2": (800, 4000),
}
MAX_PRICE = (1000, 5000)


def cost_milliminor(model: str, input_tokens: int, output_tokens: int) -> int:
    """Cost in thousandths of a cent (exact integer arithmetic, rounded up)."""
    pin, pout = PRICES_MINOR_PER_MTOK.get(model, MAX_PRICE)
    return -(-(input_tokens * pin + output_tokens * pout) // 1000)


class AIError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str | None
    request_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class BriefModel(Protocol):
    name: str
    is_mock: bool

    def complete(self, system: str, user: str, max_tokens: int) -> Completion: ...


class AnthropicBriefModel:
    is_mock = False

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        import anthropic

        self.name = settings.anthropic_model or DEFAULT_MODEL
        self.effort = settings.ai_effort
        key = settings.anthropic_api_key.get_secret_value()
        if client is None and not key:
            raise AIError("ai_not_configured", "ANTHROPIC_API_KEY is not set.")
        self.client = client or anthropic.Anthropic(
            api_key=key, timeout=float(settings.ai_request_timeout_seconds), max_retries=2
        )

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        import anthropic

        try:
            response = self.client.beta.messages.create(
                model=self.name,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": api_json_schema()},
                },
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise AIError(
                "ai_rate_limited", "Claude API rate limit reached.", retryable=True
            ) from exc
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
            raise AIError(
                "ai_unreachable", "Claude API unreachable or timed out.", retryable=True
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise AIError("ai_auth_failed", "Claude API rejected the API key.") from exc
        except anthropic.BadRequestError as exc:
            raise AIError(
                "ai_bad_request", f"Claude API rejected the request: {exc.message[:200]}"
            ) from exc
        except anthropic.APIStatusError as exc:
            raise AIError(
                "ai_provider_error",
                f"Claude API error {exc.status_code}.",
                retryable=exc.status_code >= 500,
            ) from exc
        text = "".join(str(getattr(b, "text", "")) for b in response.content if b.type == "text")
        usage = response.usage
        return Completion(
            text=text,
            model=response.model,
            input_tokens=int(usage.input_tokens or 0)
            + int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            output_tokens=int(usage.output_tokens or 0),
            stop_reason=response.stop_reason,
            request_id=getattr(response, "_request_id", None),
        )


class MockBriefModel:
    """Builds a valid, conservative brief from the provided facts. No network, no cost."""

    name = "mock-brief-model-1"
    is_mock = True

    def __init__(self, scripted: list[str] | None = None) -> None:
        self.scripted = list(scripted or [])  # tests can script raw outputs
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        self.calls.append((system, user))
        if self.scripted:
            return Completion(self.scripted.pop(0), self.name, len(user) // 4, 500, "end_turn")
        ctx = json.loads(
            user.split("<untrusted_context>", 1)[1].split("</untrusted_context>", 1)[0]
        )
        facts = {f["id"]: f for f in ctx["facts"]}
        name_id = next((i for i, f in facts.items() if f["field"] == "business_name"), None)
        industry = ctx.get("industry") or "local business"
        label = ctx.get("suggested_trust_label", "How We Work")
        findings = [f["title"] for f in ctx.get("audit_findings", [])][:3]

        def section(
            block: str,
            kind: str,
            heading: str,
            body: str,
            ids: list[str] | None = None,
            cta: str = "",
            items: list[dict[str, str]] | None = None,
        ) -> dict[str, Any]:
            return {"block": block, "content_kind": kind, "heading": heading, "body": body,
                    "items": items or [], "cta_label": cta, "fact_ids": ids or []}  # fmt: skip

        name_section = [name_id] if name_id else []
        pages = [
            {
                "slug": "home",
                "title": "Home",
                "goal": "Explain what the business offers and invite a first enquiry.",
                "sections": [
                    section(
                        "hero",
                        "verified_fact" if name_id else "proposed_copy",
                        "Welcome",
                        "A clear, mobile-friendly introduction to the business and its services.",
                        name_section,
                        "Make an enquiry",
                    ),
                    section(
                        "feature_grid",
                        "proposed_copy",
                        "Why visit us",
                        "Simple reasons to get in touch, to be confirmed by the business.",
                        items=[
                            {
                                "title": "Easy to reach",
                                "text": "Clear contact options on every page.",
                            },
                            {
                                "title": "Clear information",
                                "text": "Services explained in plain language.",
                            },
                        ],
                    ),
                ],
            },
            {
                "slug": "services",
                "title": "Services",
                "goal": "Present the offering without inventing prices or availability.",
                "sections": [
                    section(
                        "service_cards",
                        "assumption",
                        "What we offer",
                        f"Typical {industry} services; the business confirms the final list.",
                        items=[
                            {
                                "title": "Service one",
                                "text": "Description to be confirmed by the business.",
                            }
                        ],
                    )
                ],
            },
            {
                "slug": "about",
                "title": "About",
                "goal": "Introduce the business using verified information only.",
                "sections": [
                    section(
                        "text",
                        "verified_fact" if name_id else "assumption",
                        "About the business",
                        "Information below comes from the business's own website.",
                        name_section,
                    )
                ],
            },
            {
                "slug": "trust",
                "title": label,
                "goal": "Explain the process step by step.",
                "sections": [
                    section(
                        "process_steps",
                        "proposed_copy",
                        label,
                        "A simple outline of what to expect.",
                        items=[
                            {"title": "Get in touch", "text": "Send an enquiry."},
                            {
                                "title": "Discuss your needs",
                                "text": "The business replies to arrange next steps.",
                            },
                        ],
                    )
                ],
            },
            {
                "slug": "inquiry",
                "title": "Make an Inquiry",
                "goal": "Show a non-submitting inquiry form (demo only).",
                "sections": [
                    section(
                        "inquiry_demo",
                        "proposed_copy",
                        "Send an enquiry",
                        "This demo form does not send or store anything.",
                        cta="Send enquiry",
                    )
                ],
            },
            {
                "slug": "contact",
                "title": "Contact",
                "goal": "Show verified contact options only.",
                "sections": [
                    section(
                        "contact_panel",
                        "assumption",
                        "Contact",
                        "Verified contact details will be added after the business confirms them.",
                    )
                ],
            },
        ]
        brief = {
            "schema_version": SCHEMA_VERSION,
            "business_summary": f"A {industry} business with an official website. Current-site observations: " + ("; ".join(findings) if findings else "none recorded") + ".",
            "facts_used": list(facts)[:30],
            "assumptions": [{"statement": "Service list and contact details must be confirmed by the business.", "needs_owner_review": True}],
            "audience_hypotheses": [f"Local people looking for {industry} services on their phones (hypothesis)."],
            "design_direction": {"positioning": "Clear, credible and easy to use on a phone.", "tone": "Warm and professional",
                                 "visual_principles": ["strong hierarchy", "generous spacing", "mobile first"]},
            "palette": {"primary": "#1F4E79", "secondary": "#2E7D6B", "accent": "#C2410C", "background": "#FFFFFF",
                        "surface": "#F4F6F8", "text": "#1A1A1A", "muted_text": "#4B5563"},
            "typography": {"heading": "humanist-sans", "body": "system-sans"},
            "trust_page_label": label,
            "pages": pages,
            "image_briefs": [{"page": "home", "description": "Abstract, original illustration in brand colours (no photos of real people).", "alt_text": "Decorative illustration"}],
            "accessibility": ["Text contrast at least 4.5:1", "Visible focus states", "Tap targets at least 44px"],
        }  # fmt: skip
        text = json.dumps(brief)
        return Completion(text, self.name, len(system + user) // 4, len(text) // 4, "end_turn")


def build_model(settings: Settings) -> BriefModel:
    if settings.ai_provider.value == "mock":
        if settings.is_production:
            raise AIError("ai_not_configured", "The mock AI provider cannot be used in production.")
        return MockBriefModel()
    return AnthropicBriefModel(settings)
