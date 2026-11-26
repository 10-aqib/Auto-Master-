"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Button, Field } from "@/components/ui";
import { api } from "@/lib/api-client";
import type { Campaign } from "@/lib/discovery";

function list(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function CampaignForm({
  industries,
  existing,
}: {
  industries: Record<string, string>;
  existing?: Campaign;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    setFieldErrors({});
    const body = {
      name: String(form.get("name") ?? ""),
      description: String(form.get("description") ?? "") || null,
      target_countries: list(form.get("target_countries")).map((c) => c.toUpperCase()),
      target_regions: list(form.get("target_regions")),
      industries: form.getAll("industries").map(String),
      queries: list(form.get("queries")),
      source_key: String(form.get("source_key")),
      region_code: String(form.get("region_code") ?? "").toUpperCase() || null,
      candidate_cap: Number(form.get("candidate_cap")),
      daily_budget_minor: Math.round(Number(form.get("daily_budget")) * 100),
      monthly_budget_minor: Math.round(Number(form.get("monthly_budget")) * 100),
    };
    const r = existing
      ? await api<Campaign>(`/campaigns/${existing.id}`, "PUT", body)
      : await api<Campaign>("/campaigns", "POST", body);
    setBusy(false);
    if (!r.ok) {
      setError(r.error.message);
      setFieldErrors(r.error.field_errors);
      return;
    }
    router.push(`/campaigns/${r.data.id}`);
    router.refresh();
  }

  const f = existing?.filters ?? {};
  return (
    <form onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
      {error && (
        <div className="sm:col-span-2">
          <Alert>{error}</Alert>
        </div>
      )}
      <Field
        id="name"
        name="name"
        label="Campaign name"
        defaultValue={existing?.name}
        error={fieldErrors.name}
        required
      />
      <Field
        id="target_countries"
        name="target_countries"
        label="Target countries (ISO codes, comma-separated)"
        placeholder="PK"
        defaultValue={existing?.target_countries.join(", ")}
        error={fieldErrors.target_countries}
        required
      />
      <div className="grid gap-1.5 sm:col-span-2">
        <label htmlFor="queries" className="text-sm font-medium">
          Discovery searches (one per line)
        </label>
        <textarea
          id="queries"
          name="queries"
          rows={3}
          defaultValue={f.queries?.join("\n")}
          placeholder="dental clinics in Lahore"
          className="rounded-lg border border-line bg-background px-3 py-2 text-sm"
        />
        {fieldErrors.queries && (
          <p className="text-xs text-rose-700 dark:text-rose-300">{fieldErrors.queries}</p>
        )}
      </div>
      <fieldset className="grid gap-2 sm:col-span-2">
        <legend className="text-sm font-medium">Industries (used for business fit)</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {Object.entries(industries).map(([key, label]) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="industries"
                value={key}
                defaultChecked={existing?.industries.includes(key)}
              />
              {label}
            </label>
          ))}
        </div>
        {fieldErrors.industries && (
          <p className="text-xs text-rose-700 dark:text-rose-300">{fieldErrors.industries}</p>
        )}
      </fieldset>
      <div className="grid gap-1.5">
        <label htmlFor="source_key" className="text-sm font-medium">
          Discovery source
        </label>
        <select
          id="source_key"
          name="source_key"
          defaultValue={f.source_key ?? "mock_places"}
          className="min-h-10 rounded-lg border border-line bg-background px-3 text-sm"
        >
          <option value="mock_places">Mock places (testing)</option>
          <option value="google_places">Google Places API</option>
        </select>
      </div>
      <Field
        id="region_code"
        name="region_code"
        label="Search region code (optional)"
        maxLength={2}
        defaultValue={f.region_code ?? ""}
        error={fieldErrors.region_code}
      />
      <Field
        id="target_regions"
        name="target_regions"
        label="Regions or cities (optional)"
        defaultValue={existing?.target_regions.join(", ")}
      />
      <Field
        id="candidate_cap"
        name="candidate_cap"
        type="number"
        min={1}
        max={1000}
        label="Candidate cap"
        defaultValue={existing?.candidate_cap ?? 20}
        required
      />
      <Field
        id="daily_budget"
        name="daily_budget"
        type="number"
        min={0}
        step="0.01"
        label="Daily budget (USD)"
        defaultValue={(existing?.daily_budget_minor ?? 0) / 100}
        required
      />
      <Field
        id="monthly_budget"
        name="monthly_budget"
        type="number"
        min={0}
        step="0.01"
        label="Monthly budget (USD)"
        defaultValue={(existing?.monthly_budget_minor ?? 0) / 100}
        required
      />
      <div className="grid gap-1.5 sm:col-span-2">
        <label htmlFor="description" className="text-sm font-medium">
          Notes (optional)
        </label>
        <textarea
          id="description"
          name="description"
          rows={2}
          defaultValue={existing?.description ?? ""}
          className="rounded-lg border border-line bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="sm:col-span-2">
        <Button type="submit" busy={busy}>
          {existing ? "Save changes" : "Create campaign"}
        </Button>
      </div>
    </form>
  );
}
