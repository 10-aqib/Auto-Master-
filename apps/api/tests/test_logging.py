from __future__ import annotations

import json

import pytest
import structlog

from webforge_api.logging_config import REDACTED, configure_logging, redact_text, redact_value


@pytest.mark.parametrize(
    ("raw", "leaked"),
    [
        ("postgresql://webforge:hunter2pw@db:5432/x", "hunter2pw"),
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("key sk-ant-api03-ABCDEFGHIJKLMNOPQRST", "ABCDEFGHIJKLMNOPQRST"),
        ("google AIzaSyA1234567890abcdefghijk", "AIzaSyA1234567890abcdefghijk"),
        ("contact owner@business.test now", "owner@business.test"),
    ],
)
def test_redact_text(raw: str, leaked: str) -> None:
    assert leaked not in redact_text(raw)


def test_sensitive_keys_redacted_recursively() -> None:
    out = redact_value(
        None,
        {"password": "x", "nested": {"api_key": "y", "ok": "fine"}, "items": [{"token": "z"}]},
    )
    assert out == {
        "password": REDACTED,
        "nested": {"api_key": REDACTED, "ok": "fine"},
        "items": [{"token": REDACTED}],
    }


def test_logger_output_is_json_and_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_output=True)
    structlog.get_logger("t").info(
        "user_event dsn=postgresql://a:b@h/x", email="person@example.test", count=3
    )
    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["email"] == REDACTED
    assert record["count"] == 3
    assert ":b@" not in record["event"]
    assert record["level"] == "info"
    assert record["timestamp"].endswith("Z")


@pytest.mark.parametrize(
    "key", ["email", "contact_email", "phone", "postal_address", "api_key", "session_token"]
)
def test_sensitive_keys(key: str) -> None:
    assert redact_value(key, "value") == REDACTED


@pytest.mark.parametrize("key", ["email_pause", "email_sending_enabled", "session_id", "count"])
def test_operational_keys_not_redacted(key: str) -> None:
    assert redact_value(key, "value") == "value"
