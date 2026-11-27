# Data Source Compliance Review — Internal Pilot

Date: 2026-11-27. Scope: Google Places API (New), official websites, owner-provided data, prospect provenance.
This is an engineering review, **not legal advice**. Items marked **COUNSEL** need a qualified lawyer's answer
before the related feature is used with real data.

## 1. Sources read for this review

| Document | Version seen | How read |
|---|---|---|
| Google Maps Platform Terms of Service (cloud.google.com/maps-platform/terms) | "Last modified August 26, 2026" | Fetched as HTML and read as extracted text |
| Google Maps Platform Service Specific Terms (cloud.google.com/maps-platform/terms/maps-service-terms) | "Last modified November 24, 2026" | Fetched as HTML and read as extracted text |
| Places API (New) policies and attribution page | read 2026-11-26 | `docs/compliance/source-policies.md` |
| Place IDs page | read 2026-11-26 | `docs/compliance/source-policies.md` |

The terms were read from automated fetches. The owner should read the live pages directly before enabling the
source: a terms change after these dates is not covered here.

## 2. What the terms require, and what the code does

| Requirement (quote or paraphrase) | Where | Implementation | Evidence | Status |
|---|---|---|---|---|
| No scraping: do not "copy and save business names, addresses, or user reviews" | ToS §3.2.3(a)(iii) | Only the Place ID is persisted (`external_place_identifiers` holds provider, Place ID, status, timestamps). `displayName` and `websiteUri` are used in memory for the current request only. Reviews and addresses are never requested (fixed field masks, `sources/places_fields.py`). | `place_ids_only` audit check; `test_sources_api.py`; live audit 14/14 | Compliant |
| No caching except as the Service Specific Terms permit | ToS §3.2.3(b) | `TransientStore` caches a field only if the source registry allows it, encrypted, with a TTL cap and a purge job. Google: only `location`, maximum 30 days. The app requests no location field today. | `transient_cache_*` audit checks; `test_provenance_transient.py` | Compliant |
| Place IDs may be cached indefinitely | SST §3 and the Places policies page | Stored without expiry. | — | Compliant |
| Refresh Place IDs older than 12 months (recommendation) | Place ID page | `refresh-place-ids` CLI (id-only Details request); `place_ids_refreshed` audit check | `test_cli_sources.py`, audit | Compliant |
| Latitude/longitude may be cached for up to 30 consecutive calendar days | SST §15.3 | Registry cap of 2,592,000 s; the audit flags any value allowed to live longer. | `transient_cache_within_30_days` | Compliant |
| Places may be used without a Google map, but not with a non-Google map | SST §15.1–15.2 | No map of any kind is shown. | UI review | Compliant |
| Attribution: the Google Maps logo, or the text "Google Maps" | Policies page | `PlacesAttribution` on Places search results | `sources.test.tsx`, E2E step 12 | Compliant |
| No use of Maps Content to train, test, validate or fine-tune ML/AI models | ToS §3.2.3(c)(vii) | AI briefs use only independent facts (`brief_facts_exist` audit check). Maps Content never reaches the AI provider. Briefs are not model training. | `test_briefs.py`, audit | Compliant (see COUNSEL-2) |
| No use "in a listings or directory service or to create or augment an advertising product" | ToS §3.2.3(d)(iii) | Places finds candidate businesses for a private, single-user sales pipeline. No list is published or resold. | — | **COUNSEL-1** |
| No pre-fetching, indexing or storing of Maps Content outside the services | ToS §3.2.3(a)(i) | Only Place IDs are kept. A website URL is kept only after the business's own site confirmed it (see §3). | migration 0010, audit | Compliant on storage; **COUNSEL-1** on the purpose |

## 3. Finding fixed during this review

**Unverified website URLs from Google were being retained.** A website check that started from Google's
`websiteUri` stored the candidate URL, final URL, domain and evidence even when the check did not verify
(HOLD or REJECTED). That URL is Maps Content, and keeping it is not a permitted exception.

- Fix: `services/places.py::_store_verification` now stores `(not retained: Maps content)` and clears the URL,
  domain and evidence unless the check is VERIFIED. A VERIFIED URL is kept because the business's own website
  independently confirmed it (provenance `OFFICIAL_WEBSITE`, not Google).
- Existing data: migration `0010_redact_unverified_maps_urls` redacts old rows. It is data-only and irreversible
  by design. Round-trip tested: the HOLD row was redacted, and the VERIFIED and owner rows were kept.
- Test: `test_unverified_maps_website_is_not_retained`. A full dump of every table contains neither the URL
  nor the business name or address that Google supplied.

## 4. Independent provenance verification

`python -m webforge_api.provenance_audit` is a new read-only audit (exit 1 on any violation). It checks the
stored data directly with SQL, without reusing the code that wrote it.

| Check | Meaning |
|---|---|
| `fact_source_allowed` | Every fact is OFFICIAL_WEBSITE, REGISTRY, LICENSED_PROVIDER or OWNER_PROVIDED and independent |
| `fact_has_evidence` | Every fact has a value or hash, a retrieval time, a method, and a confidence in [0, 1] |
| `official_site_on_verified_domain` | Official-website facts were read on that prospect's verified domain |
| `prospect_{business_name,website_url,verified_domain,industry}_backed` | Each displayed prospect field matches a recorded fact |
| `place_ids_only` | The Place ID table has no columns beyond the permitted ones |
| `place_ids_refreshed` | No Place ID is older than 12 months without a refresh |
| `maps_urls_not_retained` | No unverified Google-supplied URL is stored |
| `transient_cache_expired_purged`, `transient_cache_within_30_days` | Cache lifetime rules |
| `contacts_from_official_sources` | Email contacts were published on the official site or given by the business |
| `brief_facts_exist` | Every fact cited by an AI brief exists in its snapshot |

Results:
- Automated: it passes after a real Places search and verification flow, and detects all six kinds of
  violation injected by the test.
- Live stack after the 30-step E2E run: **14/14 checks passed** (1 prospect, 4 facts, 3 Place IDs, 4 domain checks).
- The first live run failed 3 checks. The cause was the E2E fixture, which inserted a prospect with SQL and
  recorded only its name as a fact. The audit was right. The fixture now records all four facts, as the real
  flow does.
- Re-run after the recovery drill: passed.

Run it before and during the pilot (for example weekly, and before any export):
`docker compose exec -T api python -m webforge_api.provenance_audit`.

## 5. Open legal questions (COUNSEL)

- **COUNSEL-1. Using Places to build a prospect list.** The ToS forbids using the core services "in a listings
  or directory service" and forbids pre-fetching or indexing Maps Content. WEBFORGE stores only Place IDs plus
  facts independently confirmed from the business's own website. Whether finding sales prospects through Places
  is a permitted use is a legal question that code cannot answer.
  **Recommendation for the pilot: keep `google_places` DISABLED (the default) and add prospects from URLs the
  owner already has (owner-provided URL → official website verification). Enable Places only after counsel
  confirms in writing.**
- **COUNSEL-2.** Counsel should confirm that sending independently sourced facts to the AI provider for
  per-prospect briefs is acceptable under the AI provider's terms and the target countries' data protection law.
- **COUNSEL-3.** Before email, every target country needs a reviewed policy and a legal basis per recipient
  type. All seeded country policies are inactive DRAFTs. See `docs/compliance/qualification.md`.
- **COUNSEL-4.** Retention periods (`docs/compliance/retention.md`) need sign-off for Pakistan (PECA 2016 and
  the draft data protection bill) and for each international market.

## 6. Other sources

| Source | Status for the pilot |
|---|---|
| Official websites (robots-aware, SSRF-safe fetch) | Allowed. Facts recorded as OFFICIAL_WEBSITE with URL and time |
| Owner-provided data | Allowed. Recorded as OWNER_PROVIDED with the owner as the actor |
| Business registries / licensed data providers | Not connected. Need a documented licence before use |
| Maps UI scraping, other directories, social networks | Not implemented and not allowed |
