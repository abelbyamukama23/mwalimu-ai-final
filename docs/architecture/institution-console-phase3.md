# Mwalimu — Institutional Console: Phase 3 Architecture & Implementation
## Core Institutional Management Workspaces (People, Libraries, Resources, Access)

---

## 1. Executive Summary

In **Phase 3**, the placeholder workspaces of the **Mwalimu Institutional Console** (`Desktop/mwalimu-console/`) were transformed into a fully operational, institutional administration control plane communicating with the authoritative Platform API (`Desktop/mwalimu_final/platform_api`).

The four primary operational workspaces implemented are:
1. **People & Members Directory (`/people`)**: Listing institutional members, modifying roles (`administrator`, `teacher`, `student`, `librarian`), modifying status (`active`, `pending`, `inactive`, `suspended`), safe member removal with confirmation, and strict adherence to the backend's anti-lockout safeguard preventing removal/demotion of the sole active administrator.
2. **Knowledge Libraries Catalog (`/libraries`)**: Institutional library container catalog, creation wizard with discovery visibility controls (`discoverable` vs. `restricted`), slug auto-generation, metadata configuration, and safe deletion.
3. **Document Repository & Ingestion (`/resources`)**: Multi-library document management, file upload dropzone supporting PDF, DOCX, and TXT, multipart uploads via the Platform API (with zero direct S3 exposure to the browser), processing run inspector with stage stepper (`extract` $\rightarrow$ `normalize` $\rightarrow$ `chunk` $\rightarrow$ `embed` $\rightarrow$ `index` $\rightarrow$ `finalize`), error telemetry display, binary download streaming, and re-indexing triggers.
4. **Library Access / RBAC (`/access`)**: Per-library member access policy management matrix, granting roles (`student`, `teacher`, `administrator`) to enrolled active institution members, inline role updates, and access revocation with confirmation.

All 43 backend tests across `test_institutions_phase3.py`, `test_institutions_phase2.py`, `test_institutions.py`, `test_memberships.py`, and `test_authorization.py` passed with 100% success. The frontend console passed strict TypeScript validation (`pnpm typecheck`) and built all 13 Next.js routes successfully (`pnpm build`).

---

## 2. System Boundaries & Control-Plane Architecture

```text
Browser
   │
   ▼
mwalimu-console (console.ai-mwalimu.com) [Next.js 16 + React 19 + Tailwind CSS v4]
   ├── Centralized Client: src/lib/api/client.ts
   ├── Multi-tenant Context: X-Institution-Id header + SessionProvider + InstitutionProvider
   ├── Workspaces:
   │     ├── /people        (Directory, role/status mutations, safe member removal)
   │     ├── /libraries     (Catalog, creation wizard, visibility toggles)
   │     ├── /resources     (Dropzone, ingestion stepper, error inspector, download)
   │     └── /access        (RBAC matrix, member role grants, access revocation)
   │
   │ HTTPS REST / Bearer JWT / X-Institution-Id
   ▼
mwalimu_final / platform_api (backend.ai-mwalimu.com) [Django + DRF System of Record]
   ├── /api/v1/memberships/
   │     ├── GET ?institution_id=<uuid>
   │     ├── PATCH /<id>/ (role & status update with orphan protection)
   │     └── DELETE /<id>/ (orphan protection guard)
   ├── /api/v1/libraries/
   │     ├── GET ?institution_id=<uuid>
   │     ├── POST / (scope_type="institution", institution_id=<uuid>)
   │     ├── PATCH /<id>/
   │     └── DELETE /<id>/
   ├── /api/v1/libraries/<id>/resources/
   │     ├── GET /
   │     ├── POST / (multipart file upload streamed to S3 via storage backend)
   │     ├── DELETE /<resource_id>/ (storage object and db cleanup)
   │     ├── GET /<resource_id>/download/ (authorized stream)
   │     ├── GET /<resource_id>/processing-status/ (stage telemetry & error reporting)
   │     └── POST /<resource_id>/processing-status/ (trigger re-processing & indexing)
   └── /api/v1/libraries/<id>/access-policies/
         ├── GET /
         ├── POST / (grant role to active institution member)
         ├── PATCH /<policy_id>/ (modify role)
         └── DELETE /<policy_id>/ (revoke grant)
```

---

## 3. Authoritative Platform API Endpoints Consumed

| Workspace | HTTP Method | Endpoint | Description |
|-----------|-------------|----------|-------------|
| **People** | `GET` | `/api/v1/memberships/?institution_id={id}` | Scoped member listing for active institution |
| **People** | `PATCH` | `/api/v1/memberships/{id}/` | Update membership role or status |
| **People** | `DELETE` | `/api/v1/memberships/{id}/` | Remove member from institution |
| **Libraries** | `GET` | `/api/v1/libraries/?institution_id={id}` | Scoped institutional library listing |
| **Libraries** | `POST` | `/api/v1/libraries/` | Create institutional library |
| **Libraries** | `PATCH` | `/api/v1/libraries/{id}/` | Update library metadata & visibility |
| **Libraries** | `DELETE` | `/api/v1/libraries/{id}/` | Delete / archive library |
| **Resources** | `GET` | `/api/v1/libraries/{lib_id}/resources/` | List resources in library |
| **Resources** | `POST` | `/api/v1/libraries/{lib_id}/resources/` | Multipart upload (PDF/DOCX/TXT) |
| **Resources** | `DELETE` | `/api/v1/libraries/{lib_id}/resources/{id}/` | Delete resource and object binary |
| **Resources** | `GET` | `/api/v1/libraries/{lib_id}/resources/{id}/download/` | Stream original binary |
| **Resources** | `GET` | `/api/v1/libraries/{lib_id}/resources/{id}/processing-status/` | Inspect stage, chunks, errors |
| **Resources** | `POST` | `/api/v1/libraries/{lib_id}/resources/{id}/processing-status/` | Re-enqueue ingestion & indexing |
| **Access** | `GET` | `/api/v1/libraries/{lib_id}/access-policies/` | List access policies on library |
| **Access** | `POST` | `/api/v1/libraries/{lib_id}/access-policies/` | Grant access policy to member |
| **Access** | `PATCH` | `/api/v1/libraries/{lib_id}/access-policies/{id}/` | Update granted role |
| **Access** | `DELETE` | `/api/v1/libraries/{lib_id}/access-policies/{id}/` | Revoke access policy |

---

## 4. Backend Additive Enhancements Made

To support clean control-plane consumption without regressions:
1. **`LibraryViewSet.get_queryset` Scoping**:
   - Added support for `?institution_id=<uuid>` and `X-Institution-Id` header.
   - If specified and caller is an active administrator: returns all active institutional libraries belonging to that institution.
   - If specified and caller is a member: returns discoverable or granted libraries in that institution.
   - If caller is not a member: returns an empty queryset (strict tenant isolation).
   - If omitted: preserves backwards-compatible query combining personal libraries and all authorized institutional libraries.
2. **`ResourceViewSet.processing_status` Error Telemetry**:
   - Added `error_code` and `error_message` fields to the JSON response so the control-plane UI can surface human-readable failure diagnostics when an ingestion or chunking task fails.

---

## 5. Security & Authorization Guarantees

1. **Zero Direct Database Connection**: The Next.js console connects only via HTTPS to the Platform API.
2. **Zero Direct S3 Credentials**: File uploads are streamed via multipart form data to the Platform API, which validates the file and uploads to object storage. File downloads are authenticated through the Platform API's streaming endpoint. No S3 access keys or presigned direct URLs are exposed to the browser.
3. **Anti-Lockout Invariant**: The Platform API strictly validates that the final active administrator cannot be removed, demoted, deactivated, or suspended. When attempted from the UI, the console catches the validation error and surfaces a clear explanation.
4. **Tenant Context Isolation**: When an administrator switches institutions in the top bar switcher, the `X-Institution-Id` header updates immediately, and all workspace querysets re-fetch data for the new tenant. Stale data from previous institutions is wiped on switch.

---

## 6. Verification Results

### Backend Automated Test Suite (`uv run pytest`)
```text
tests/test_institutions_phase3.py ...                                    [100%]
tests/test_institutions_phase2.py ..........                             [100%]
tests/test_institutions.py ........                                      [100%]
tests/test_memberships.py ...............                                [100%]
tests/test_authorization.py .......                                      [100%]

Total: 43 passed, 0 failed in 68.87s
```

### Frontend TypeScript & Production Build (`mwalimu-console`)
```text
> mwalimu-console@0.1.0 typecheck
> tsc --noEmit
(0 errors)

> mwalimu-console@0.1.0 build
▲ Next.js 16.3.2 (Turbopack)
✓ Compiled successfully in 3.1s
Finished TypeScript in 5.1s
Generating static pages (13/13) in 623ms
✓ 13/13 routes built successfully:
  /
  /_not-found
  /access
  /dashboard
  /libraries
  /login
  /onboarding
  /people
  /register
  /resources
  /settings
  /verify-email
```

---

## 7. Known Boundaries & Deferred Capabilities
* **Billing, Subscriptions, API Keys**: Not implemented in Phase 3 (deferred to subsequent phases).
* **Connectors (Google Drive, Notion, Web Crawlers)**: Deferred to dedicated connector management phase.
* **Academic Classroom Gradebooks / Curriculums**: Belongs to academic management layer.
