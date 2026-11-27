"""Outreach message template (outreach-1) and truthfulness checks. One initial message only; no follow-ups."""

from __future__ import annotations

import re
from dataclasses import dataclass

TEMPLATE_VERSION = "outreach-1"
PREVIEW_SLOT = "{{PREVIEW_URL}}"
UNSUBSCRIBE_SLOT = "{{UNSUBSCRIBE_URL}}"

# Deceptive or pressure patterns (subject and body). Matched case-insensitively.
FORBIDDEN = [
    (re.compile(r"^\s*(re|fwd?)\s*:", re.I), "fake_reply_prefix"),
    (re.compile(r"\b(urgent|act now|last chance|limited time|expires today|final notice)\b", re.I), "false_urgency"),
    (re.compile(r"\b(as (we )?discussed|following up|per our (call|conversation)|you requested|thanks for your interest)\b", re.I), "fake_familiarity"),
    (re.compile(r"\b(guarantee[ds]?|#1|number one|double your|10x|increase (your )?(sales|revenue|traffic) by)\b", re.I), "unsupported_claim"),
    (re.compile(r"\b(official website of|on behalf of|authori[sz]ed by)\b", re.I), "implied_endorsement"),
]  # fmt: skip


@dataclass
class Draft:
    subject: str
    text: str  # contains PREVIEW_SLOT and UNSUBSCRIBE_SLOT until send time


def render(*, business: str, domain: str, observed_on: str, observation: str, from_name: str, author_title: str,
           author_url: str, physical_address: str, source_domain: str, preview_expires_on: str, contact_name: str | None) -> Draft:  # fmt: skip
    greeting = f"Hello {contact_name}," if contact_name else "Hello,"
    lines = [
        greeting,
        "",
        f"I'm {from_name}, a {author_title.lower()}. On {observed_on} I looked at {domain} and noticed one thing that may be worth a look: {observation.rstrip('.')}.",
        "",
        f"I prepared an independent redesign concept to show one possible direction. It is not affiliated with {business} and was not requested by you:",
        PREVIEW_SLOT,
        f"(The link stops working on {preview_expires_on}. A PDF summary is on the same page.)",
        "",
        "If it is useful, just reply to this email. If not, no action is needed and I will not send further messages.",
        "",
        f"{from_name}, {author_title}",
        author_url,
    ]
    if physical_address:
        lines.append(physical_address)
    lines += [
        "",
        f"You are receiving this one-time message because this address is published on {source_domain}. "
        f"To opt out of any further messages: {UNSUBSCRIBE_SLOT}",
    ]
    return Draft(subject=f"Website redesign concept for {business}"[:150], text="\n".join(lines))


def check(
    draft: Draft, *, from_name: str, physical_address_required: bool, physical_address: str
) -> list[str]:
    """Return reason codes for content problems (empty = passes)."""
    problems: list[str] = []
    for pattern, code in FORBIDDEN:
        if pattern.search(draft.subject) or (
            code != "fake_reply_prefix" and pattern.search(draft.text)
        ):
            problems.append(f"content_{code}")
    if from_name not in draft.text:
        problems.append("content_sender_identity_missing")
    if "independent redesign concept" not in draft.text or "not affiliated with" not in draft.text:
        problems.append("content_concept_notice_missing")
    if PREVIEW_SLOT not in draft.text and "/p/" not in draft.text:
        problems.append("content_preview_missing")
    if UNSUBSCRIBE_SLOT not in draft.text and "/u/" not in draft.text:
        problems.append("content_unsubscribe_missing")
    if not re.search(r"\b\d{1,2} \w+ \d{4}\b", draft.text):
        problems.append("content_observation_date_missing")
    if physical_address_required and (not physical_address or physical_address not in draft.text):
        problems.append("content_physical_address_missing")
    return sorted(set(problems))
