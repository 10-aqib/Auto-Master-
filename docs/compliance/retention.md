# Retention and Deletion (Phase 01 interfaces)

Engineering defaults pending qualified legal review. Code: `apps/api/src/webforge_api/services/retention.py`.

| Data | Default | Mechanism |
|---|---|---|
| Revoked/expired sessions | 30 days | `python -m webforge_api.cli purge-expired` (schedule daily from Phase 10) |
| Activity log | Kept; archival policy decided in Phase 11 | Append-only, cannot be deleted through the app |
| Suppressions | Kept while needed to prevent re-contact | Keyed hash only; no FK, survives contact/prospect deletion |
| Email contacts | Until deletion request or prospect erasure | `delete_email_contact` (also deletes consent records) |
| Prospects | Until erasure | `erase_prospect`: deletes sources, Place IDs, campaign links and contacts; **refused** while audit, design, proposal, compliance, outreach or reply history exists |
| Artifacts / previews | `ARTIFACT_RETENTION_DAYS` / `PREVIEW_RETENTION_DAYS` | Implemented with storage in Phases 04 and 08 |

Every deletion writes an activity-log entry. Deletion never removes a suppression record.
