import { Alert } from "@/components/ui";
import { reasonText, type Verification } from "@/lib/sources";

export function VerificationResult({ v, prospectId }: { v: Verification; prospectId: string | null }) {
  const tone = v.status === "VERIFIED" ? "success" : v.status === "HOLD" ? "info" : "error";
  const heading = {
    VERIFIED: "Verified from the business's own website",
    HOLD: "On hold — needs review",
    REJECTED: "Rejected",
  }[v.status];
  return (
    <Alert tone={tone}>
      <p className="font-medium">{heading}</p>
      {v.final_url && <p className="mt-1 break-all text-xs">Checked: {v.final_url}</p>}
      {v.reason_codes.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs">
          {v.reason_codes.map((c) => (
            <li key={c}>{reasonText(c)}</li>
          ))}
        </ul>
      )}
      {v.status === "VERIFIED" && (
        <p className="mt-1 text-xs">
          Matched “{String(v.evidence.excerpt ?? "")}” ({String(v.evidence.matched_signal ?? "")}), confidence{" "}
          {v.confidence?.toFixed(2)}.{" "}
          {prospectId && <span>Recorded as a verified prospect with field-level provenance.</span>}
        </p>
      )}
      {v.status !== "VERIFIED" && v.candidate_origin && (
        <p className="mt-1 text-xs text-muted">Nothing was stored except this verification record.</p>
      )}
    </Alert>
  );
}
