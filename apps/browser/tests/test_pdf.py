"""Offline proposal PDF rendering (Phase 08)."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from webforge_browser import app as app_module
from webforge_browser.pdf import render_pdf

PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201f5d5ed6d0000000049454e44ae426082"
    )
).decode()


def doc(body: str) -> str:
    return f"<!doctype html><html><head><style>section{{page-break-after:always}}</style></head><body>{body}</body></html>"


async def test_pdf_has_pages_and_blocks_network() -> None:
    html = doc(
        f'<section><h1>Cover</h1><img src="data:image/png;base64,{PNG_1PX}" alt="x"></section>'
        '<section><h1>Second</h1><img src="https://cdn.example.test/remote.png" alt="r"></section><section>Third</section>'
    )
    pdf, blocked = await render_pdf(html, "Independent redesign concept")
    assert pdf.startswith(b"%PDF-")
    assert (
        pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") + pdf.count(b"/Type/Page") >= 1
        or b"/Count 3" in pdf
    )
    assert any("cdn.example.test" in b for b in blocked)


def test_pdf_endpoint_validates_input() -> None:
    client = TestClient(app_module.app)
    assert client.post("/pdf", json={"html": "short", "footer_notice": "x"}).status_code == 422
    assert (
        client.post(
            "/pdf", json={"html": doc("x" * 30), "footer_notice": "x", "extra": 1}
        ).status_code
        == 422
    )


def test_pdf_endpoint_returns_pdf() -> None:
    client = TestClient(app_module.app)
    r = client.post("/pdf", json={"html": doc("<p>Hello proposal</p>"), "footer_notice": "Concept"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-") and r.headers["x-blocked-requests"] == "0"
