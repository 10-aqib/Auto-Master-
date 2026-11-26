# Source Policies and Data Governance (Phase 02)

Engineering notes, not legal advice. Re-check every source before enabling it, and record the review in
the dashboard (Sources → Record terms review). Qualified legal review is still required before production use.

## Google Places API (New) — checked 2026-11-26

| Page | URL |
|---|---|
| Policies and attribution | https://developers.google.com/maps/documentation/places/web-service/policies |
| Field masks | https://developers.google.com/maps/documentation/places/web-service/choose-fields |
| Data fields / SKUs | https://developers.google.com/maps/documentation/places/web-service/data-fields |
| Text Search (New) | https://developers.google.com/maps/documentation/places/web-service/text-search |
| Place Details (New) | https://developers.google.com/maps/documentation/places/web-service/place-details |
| Usage and billing | https://developers.google.com/maps/documentation/places/web-service/usage-and-billing |
| SKU details | https://developers.google.com/maps/billing-and-pricing/sku-details/places |
| Place IDs | https://developers.google.com/maps/documentation/places/web-service/place-id |
| Service Specific Terms | https://cloud.google.com/maps-platform/terms/maps-service-terms — **could not be read automatically; the owner must read it directly** |

### What the pages say (summarised; quotes from the policies page)

- "The place ID … is exempt from the caching restrictions. You can therefore store place ID values indefinitely."
- Latitude/longitude may be cached for up to 30 consecutive calendar days, then deleted.
- Otherwise: "Cache or store Google Maps Content only as expressly permitted"; do not "pre-fetch, index, store, or
  redistribute Google Maps Content", including "copy and save business names, addresses, or user reviews".
- Field mask is mandatory (`X-Goog-FieldMask`); "don't use the wildcard (*) response field mask in production".
- Requests are billed at the highest SKU among requested fields.
- Attribution without a Google map: the Google Maps logo, or the text "Google Maps" where space is limited
  (Roboto, 12–16sp, not wrapped/localised, #1F1F1F/#5E5E5E/white). Users must be able to reach the source via
  `googleMapsUri`. Photos/reviews require author attribution (we never request them).
- Place IDs older than 12 months should be refreshed with an IDs-only Place Details request; `NOT_FOUND` means obsolete.
- Whether IDs-only requests are free is stated inconsistently (one page says "no charge", the SKU page lists a
  billable event). We therefore require an explicit configured price for **every** SKU, including IDs-only.

### How the code complies

| Rule | Implementation |
|---|---|
| Store only Place IDs | `external_place_identifiers` has no content columns; `source_registrations.persistable_fields = ['place_id']`; a test scans every table after a search for the Google name/address/URL/status |
| Maps content can't become a "verified fact" | `prospect_sources.source_type` CHECK allows only OFFICIAL_WEBSITE, REGISTRY, LICENSED_PROVIDER, OWNER_PROVIDED; `record_fact` refuses MAPS_API/MOCK sources |
| Minimal field masks, no wildcard | `sources/places_fields.py`: per-endpoint allow-list; `*`, reviews, photos, phone, rating are refused |
| Cost control | Per-SKU prices, daily budget, daily request cap, per-campaign cap and per-minute rate limit; reservation before each call under a DB advisory lock; unpriced SKU or zero budget = refused |
| Caching | `transient_source_values` only for fields listed in the registry's `cache_rules` (Places: `location` ≤ 30 days); encrypted; `purge-transient` CLI |
| Place ID refresh | `refresh-place-ids` CLI (IDs-only mask, marks `OBSOLETE` on `NOT_FOUND`) |
| Attribution | `PlacesAttribution` component (self-hosted Roboto, `translate="no"`, no wrap) inside the results container; each result links to `googleMapsUri` |
| Key safety | Server-side only, sent in a header, never in URLs, logs, API responses or the dashboard; tests assert this |
| Disabled by default | Registry rows start `DISABLED`; enabling needs an owner terms review; Google also needs `GOOGLE_PLACES_API_ENABLED=true`, a key, a budget and a request cap |

### Open questions for legal review (flagged, not resolved)

1. **Using `websiteUri` and `displayName` to start independent verification.** We use these Maps fields only
   transiently, inside one request, to decide which website to check and to compare names. Nothing from them is
   stored; stored facts come from the business's own website. Confirm this transient use is within the Service
   Specific Terms for the intended commercial purpose.
2. **Storing Place IDs for candidates that never become prospects.** Policy permits storing IDs indefinitely; decide
   a retention period anyway (proposed: delete candidate IDs with no prospect after 12 months).
3. Whether the overall prospecting use case is acceptable under the current terms at all. If not, keep
   `google_places` disabled and rely on owner-provided and licensed sources.

## Business-owned official websites

Used as the independent source for persisted facts. The verifier:

- Uses only a URL supplied by a source or by the owner; it never derives a domain from a business name.
- Reads `robots.txt` first (RFC 9309: 4xx = allowed; 5xx = treat as disallowed), honouring the configured user agent.
- Fetches the homepage only, via the SSRF-safe fetcher: public IPs only (DNS pinned, every redirect re-checked),
  ports 80/443, size and time limits, no cookies, logins, forms or scripts.
- Holds off-site redirects, parked domains, structured data naming another site, and weak name matches.
- Records evidence (matched signal, score, short excerpt of the site's own text) in `domain_verifications`.
- Stores `business_name` (as the site states it), `website_url` and `verified_domain` with field-level provenance
  (source URL, time, terms version, confidence, method).

Owner review should confirm: public pages only, purpose limitation, and the user-agent text (consider adding a
contact URL you control in `WEBSITE_FETCH_USER_AGENT`).

## Mock places

Deterministic fake data (`*.example.test` domains) for development and CI. Cannot be enabled or seen in production.
Labelled "Mock data - not Google Maps" wherever shown.

## Other sources (not implemented)

Company registries, licensed data providers and owner CSV uploads are recognised source types but have no
connector yet. They will start disabled and need their own terms review.
