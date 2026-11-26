# Qualification Rubric v1

A qualification score is evidence that a redesign concept could be useful. It is **not** buying intent and
**never** permission to email. Code: `apps/api/src/webforge_api/services/qualification.py`.

| Component | Weight | Evidence | Unknown when |
|---|---|---|---|
| Website presence | 10 | Latest website check VERIFIED | No verified site |
| Mobile experience | 20 | Audit `mobile_usability` score (opportunity = weight × (1 − score/100)) | Not audited / not testable |
| Visual hierarchy | 15 | Audit `visual_structure` | same |
| Navigation clarity | 15 | Audit `navigation` | same |
| Conversion path | 15 | Audit `conversion` | same |
| Business fit | 15 | Industry from the site's own schema.org type vs campaign industries (match 15, mismatch 0) | Campaign has no industries, or site states none |
| Source quality | 10 | 10 × best confidence of the independent business-name evidence | No independent evidence |

- Score = earned points / points with evidence × 100. Coverage = evidence weight / 100.
- Outcomes: do-not-contact or owner-rejected → REJECTED; industry mismatch → REJECTED; possible duplicate →
  MANUAL_REVIEW; coverage < 50% → INVESTIGATE (`awaiting_audit_evidence` before an audit); otherwise bands
  STRONG ≥ 75, POTENTIAL 60–74, INVESTIGATE 40–59, REJECTED (low priority) < 40.
- Every run is stored in `qualification_results` with each component's reason and evidence.
