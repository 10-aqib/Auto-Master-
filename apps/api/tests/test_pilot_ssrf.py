"""Internal pilot: extra SSRF encodings an attacker-controlled website URL could use."""

from __future__ import annotations

import pytest

from webforge_api.net.safe_fetch import (
    FetchBlockedError,
    FetchFailedError,
    FetchPolicy,
    SafeFetcher,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433/",  # decimal 127.0.0.1
        "http://0x7f000001/",  # hex
        "http://017700000001/",  # octal
        "http://0177.0.0.1/",  # octal dotted
        "http://127.1/",  # short form
        "http://0/",  # 0.0.0.0
        "http://[0:0:0:0:0:ffff:7f00:1]/",  # IPv4-mapped, long form
        "http://[::ffff:a9fe:a9fe]/",  # metadata, mapped hex
        "http://[fe80::1%25eth0]/",  # link-local with zone id
        "http://localhost./",  # trailing dot
        "http://LOCALHOST/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://169.254.169.254.nip.io.invalid/",  # unresolvable rebinding-style name
        "http://example.com@127.0.0.1/",  # userinfo confusion
        "http://127.0.0.1:80\\@example.com/",  # backslash confusion
        "http://example.com:0/",
        "http://example.com:65536/",
    ],
)
def test_encoded_internal_targets_are_never_fetched(url: str) -> None:
    with pytest.raises((FetchBlockedError, FetchFailedError)) as info:
        SafeFetcher(FetchPolicy(total_timeout=3, read_timeout=3)).get(url)
    if isinstance(info.value, FetchFailedError):
        assert info.value.code in ("dns_failed", "invalid_url", "unresolvable"), info.value.code
