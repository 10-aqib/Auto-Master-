"use client";

import { JsonForm, Select, TextArea } from "@/components/json-form";
import { Field } from "@/components/ui";
import { RULES_TEMPLATE } from "@/lib/outreach";

const TYPES = ["CORPORATE", "ROLE_ACCOUNT", "SOLE_TRADER", "INDIVIDUAL"];

export function PolicyDraftForm() {
  return (
    <JsonForm
      path="/compliance/policies"
      submitLabel="Save draft"
      className="mt-3 grid gap-3 sm:grid-cols-2"
      transform={(b) => ({
        country_code: b.country_code.toUpperCase(),
        recipient_type: b.recipient_type,
        message_category: "commercial_initial",
        version: b.version,
        rules: JSON.parse(b.rules),
        source_references: b.source_references.split(/\s+/).filter(Boolean),
      })}
    >
      <Field id="pol-country" name="country_code" label="Country (ISO code)" maxLength={2} />
      <Select
        label="Recipient type"
        name="recipient_type"
        options={TYPES.map((t) => ({ value: t, label: t.toLowerCase().replaceAll("_", " ") }))}
      />
      <Field id="pol-version" name="version" label="Version" />
      <TextArea label="Official source URLs (one per line)" name="source_references" rows={3} />
      <div className="sm:col-span-2">
        <TextArea
          label="Rules (JSON, as advised by counsel)"
          name="rules"
          rows={10}
          defaultValue={JSON.stringify(RULES_TEMPLATE, null, 2)}
        />
      </div>
    </JsonForm>
  );
}

export function CountryPauseForm() {
  return (
    <JsonForm
      path="/controls"
      pathFrom={(b) => `/controls/country_pause:${b.country.toUpperCase()}`}
      method="PUT"
      submitLabel="Pause country"
      transform={(b) => {
        if (!/^[A-Za-z]{2}$/.test(b.country)) throw new Error("Use a two-letter country code.");
        return { enabled: true, reason: b.reason };
      }}
      className="grid gap-3 sm:grid-cols-3 sm:items-end"
    >
      <Field id="cp-country" name="country" label="Country (ISO code)" maxLength={2} />
      <Field id="cp-reason" name="reason" label="Reason" />
    </JsonForm>
  );
}
