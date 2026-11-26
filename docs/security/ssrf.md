# Fetching Untrusted URLs (SSRF Defences)

All outbound requests to prospect websites go through `webforge_api.net.safe_fetch.SafeFetcher`.

| Threat | Defence | Test |
|---|---|---|
| Non-HTTP schemes (`file:`, `gopher:`, `javascript:`) | Only `http`/`https` accepted after normalisation | `test_url_level_blocks` |
| Credentials in URL, odd ports | Rejected; ports limited to 80/443 | same |
| Private/loopback/link-local/CGNAT/multicast/reserved targets, cloud metadata (169.254.169.254, fd00:ec2::254) | Every resolved address must be public (`is_global` + explicit deny list) | `test_non_public_addresses_rejected` |
| IPv4-mapped / 6to4 / Teredo / IPv4-compatible IPv6 forms | Embedded IPv4 extracted and re-checked | same |
| Numeric/obfuscated hosts (`2130706433`, `0x7f.0.0.1`, `127.1`, `localhost`) | Resolved by the OS, then checked | `test_hosts_resolving_to_loopback_blocked_by_default_policy` |
| DNS rebinding | Resolve once per connection, refuse if ANY answer is internal, connect to the vetted IP (no second lookup) | `test_mixed_dns_answers_are_refused`, `test_rebinding_cannot_change_the_connected_address` |
| Redirect to internal address or other scheme | Redirects followed manually; each hop fully re-validated | `test_redirects_are_revalidated` |
| Redirect loops | Max 5 redirects | `test_redirect_loop_bounded` |
| Huge or slow responses | Byte cap (`BROWSER_MAX_RESPONSE_BYTES`), connect/read/total timeouts | `test_oversized_body_truncated`, `test_slow_response_times_out` |
| Proxy/env bypass | httpcore pool with the pinned backend; no proxy or environment configuration | design |
| TLS spoofing | Certificates verified against the original host name | `test_tls_certificates_are_verified` |

Network isolation (egress firewall, separate worker container without database/Redis access) is added with the
Phase 04 audit worker; until then the fetcher runs in the API process with these application-level controls.
