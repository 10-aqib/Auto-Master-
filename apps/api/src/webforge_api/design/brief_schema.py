"""Versioned, strict design-brief schema (brief-1).

The AI must return exactly this shape (unknown fields rejected). Every piece of copy is labelled
as a verified fact (with fact IDs), proposed copy, or an assumption. Content-integrity rules that
JSON Schema cannot express live in `design/integrity.py`.
"""

from __future__ import annotations

import copy
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "brief-1"
PAGE_SLUGS = ("home", "services", "about", "trust", "inquiry", "contact")
BLOCKS = (
    "hero", "feature_grid", "service_cards", "process_steps", "faq", "text",
    "cta_band", "inquiry_demo", "contact_panel", "gallery_placeholder",
)  # fmt: skip
# Licensed/system font stacks the renderer can use without loading third-party fonts.
FONT_STACKS = (
    "system-sans",
    "system-serif",
    "humanist-sans",
    "geometric-sans",
    "classic-serif",
    "mono-accent",
)

Hex = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
Short = Annotated[str, Field(min_length=1, max_length=120)]
Para = Annotated[str, Field(min_length=1, max_length=700)]
FactId = Annotated[str, Field(pattern=r"^F[0-9]{1,3}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Assumption(Strict):
    statement: Para
    needs_owner_review: bool


class DesignDirection(Strict):
    positioning: Para
    tone: Short
    visual_principles: Annotated[list[Short], Field(min_length=2, max_length=6)]


class Palette(Strict):
    primary: Hex
    secondary: Hex
    accent: Hex
    background: Hex
    surface: Hex
    text: Hex
    muted_text: Hex


class Typography(Strict):
    heading: Literal[FONT_STACKS]  # type: ignore[valid-type]
    body: Literal[FONT_STACKS]  # type: ignore[valid-type]


class Item(Strict):
    title: Short
    text: Para


class Section(Strict):
    block: Literal[BLOCKS]  # type: ignore[valid-type]
    content_kind: Literal["verified_fact", "proposed_copy", "assumption"]
    heading: Short
    body: Annotated[str, Field(max_length=700)]
    items: Annotated[list[Item], Field(max_length=8)]
    cta_label: Annotated[str, Field(max_length=40)]
    fact_ids: Annotated[list[FactId], Field(max_length=10)]


class PagePlan(Strict):
    slug: Literal[PAGE_SLUGS]  # type: ignore[valid-type]
    title: Short
    goal: Para
    sections: Annotated[list[Section], Field(min_length=1, max_length=8)]


class ImageBrief(Strict):
    page: Literal[PAGE_SLUGS]  # type: ignore[valid-type]
    description: Para
    alt_text: Short


class DesignBrief(Strict):
    schema_version: Literal["brief-1"]
    business_summary: Para
    facts_used: Annotated[list[FactId], Field(max_length=30)]
    assumptions: Annotated[list[Assumption], Field(max_length=10)]
    audience_hypotheses: Annotated[list[Para], Field(min_length=1, max_length=4)]
    design_direction: DesignDirection
    palette: Palette
    typography: Typography
    trust_page_label: Short
    pages: Annotated[list[PagePlan], Field(min_length=6, max_length=6)]
    image_briefs: Annotated[list[ImageBrief], Field(max_length=12)]
    accessibility: Annotated[list[Short], Field(min_length=2, max_length=8)]


_UNSUPPORTED = {"minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                "multipleOf", "minItems", "maxItems", "pattern", "default", "title"}  # fmt: skip


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in node.items() if k not in _UNSUPPORTED}
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def api_json_schema() -> dict[str, Any]:
    """JSON Schema for `output_config.format`: constraints the API does not support are removed
    here and enforced by Pydantic validation after the response arrives."""
    schema = _strip(copy.deepcopy(DesignBrief.model_json_schema()))
    assert isinstance(schema, dict)  # noqa: S101 - model_json_schema always returns an object
    return schema
