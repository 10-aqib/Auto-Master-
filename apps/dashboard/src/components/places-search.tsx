"use client";

import { useState, type FormEvent } from "react";

import { PlacesAttribution } from "@/components/attribution";
import { VerificationResult } from "@/components/verification-result";
import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { PlaceResult, SearchResponse, Source, VerifyResponse } from "@/lib/sources";

function ResultRow({ place, canVerify }: { place: PlaceResult; canVerify: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  return (
    <li className="grid gap-2 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{place.display_name ?? "(no name)"}</p>
          <p className="text-sm text-muted">{place.formatted_address}</p>
          <p className="text-xs text-muted">
            {place.business_status?.toLowerCase().replaceAll("_", " ")}
            {place.google_maps_uri && (
              <>
                {" · "}
                <a
                  href={place.google_maps_uri}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-accent hover:underline"
                >
                  View on Google Maps
                </a>
              </>
            )}
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          busy={busy}
          disabled={!canVerify}
          title={canVerify ? undefined : "Enable official-website verification on the Sources page."}
          onClick={async () => {
            setBusy(true);
            setError(null);
            const r = await api<VerifyResponse>(
              `/places/identifiers/${place.identifier_id}/verify-website`,
              "POST",
            );
            setBusy(false);
            if (r.ok) setResult(r.data);
            else setError(r.error.message);
          }}
        >
          Verify website
        </Button>
      </div>
      {error && <Alert>{error}</Alert>}
      {result && <VerificationResult v={result.verification} prospectId={result.prospect_id} />}
    </li>
  );
}

export function PlacesSearch({ sources, canVerify }: { sources: Source[]; canVerify: boolean }) {
  const usable = sources.filter((s) => s.usable);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const region = String(form.get("region_code") ?? "")
      .trim()
      .toUpperCase();
    setBusy(true);
    setError(null);
    const r = await api<SearchResponse>("/places/search", "POST", {
      source_key: String(form.get("source_key") ?? ""),
      text_query: String(form.get("text_query") ?? ""),
      region_code: region || null,
      page_size: Number(form.get("page_size") ?? 10),
    });
    setBusy(false);
    if (r.ok) setResult(r.data);
    else setError(r.error.message);
  }

  if (usable.length === 0) {
    return (
      <Alert tone="info">
        No Places source is usable yet. On the Sources page, enable “Mock places” for testing, or review and
        enable Google Places once its key, budget and prices are configured.
      </Alert>
    );
  }

  return (
    <div className="grid gap-6">
      <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-[1fr_2fr]" noValidate>
        <div className="grid gap-1.5">
          <label htmlFor="source_key" className="text-sm font-medium">
            Source
          </label>
          <select
            id="source_key"
            name="source_key"
            className="min-h-10 rounded-lg border border-line bg-background px-3 text-sm"
          >
            {usable.map((s) => (
              <option key={s.key} value={s.key}>
                {s.display_name}
              </option>
            ))}
          </select>
        </div>
        <Field
          id="text_query"
          name="text_query"
          label="Search"
          placeholder="e.g. dental clinics in Lahore"
          minLength={3}
          required
        />
        <Field
          id="region_code"
          name="region_code"
          label="Region code (optional)"
          placeholder="PK"
          maxLength={2}
        />
        <Field
          id="page_size"
          name="page_size"
          type="number"
          label="Results (1–20)"
          defaultValue={10}
          min={1}
          max={20}
        />
        <div className="sm:col-span-2">
          <Button type="submit" busy={busy}>
            Search
          </Button>
        </div>
      </form>
      {error && <Alert>{error}</Alert>}
      {result && (
        <section aria-labelledby="results" className="rounded-xl border border-line bg-surface p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="results" className="text-base font-semibold">
              {result.places.length} results
            </h2>
            <PlacesAttribution text={result.attribution.text} isMock={result.attribution.is_mock} />
          </div>
          <p className="mt-1 text-xs text-muted">
            Shown once and not stored. Saved: {result.stored_place_ids} Place IDs ({result.new_place_ids}{" "}
            new). Billed as {result.sku}.
          </p>
          <ul className="mt-2 divide-y divide-line">
            {result.places.map((p) => (
              <ResultRow key={p.place_id} place={p} canVerify={canVerify} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
