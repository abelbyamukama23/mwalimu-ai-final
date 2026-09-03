# Mwalimu — Institutional Console Capability Audit
## Phase 0: Institutional Control Plane Architectural Audit

---

## 1. Executive Summary

This document presents a comprehensive, empirical architectural audit of the **Mwalimu Platform repository** (`platform_api`, `agent_service`, `frontend`, and data layers) to determine readiness for designing and implementing the **Institutional Console** (the institutional management workspace/control plane).

### Key Architectural Findings:

1. **Substantial Backend Foundations Already Exist**:
   The Platform API is not a greenfield prototype. It already possesses a robust multi-tenant core:
   - `Institution` tenant boundary with lifecycle states (`active`, `suspended`, `archived`).
   - `Membership` with 4 distinct roles (`administrator`, `teacher`, `student`, `librarian`) and 4 lifecycle states (`pending`, `active`, `inactive`, `suspended`).
   - `Library` with dual scoping (`personal` vs `institution`), lifecycle states, and visibility modes (`discoverable` vs `restricted`).
   - `LibraryAccessPolicy` providing granular, per-library RBAC (`administrator`, `teacher`, `student`).
   - `Resource` lifecycle and asynchronous document processing pipeline (`ProcessingRun`, `DocumentStructureNode`, `BookIndexEntry`, `DocumentPageMap`, `DocumentChunk`, `ChunkEmbedding`).
   - `Connector`, `Connection`, and `ConnectionSyncJob` for institutional external knowledge ingestion (Web crawler, Notion, Google Drive, Amazon S3) with credential encryption and remote directory browsing.
   - `InstitutionContextRegion` for configuring geographic catchment areas and localized pedagogical relevance.
   - `AgentSession` and `AgentRunRecord` capturing durable audit records of user interactions, steps, and prompt/completion/total token usage tied to `institution`.

2. **The Missing Layer is Primarily the Console UI and Administrative Lifecycles**:
   Approximately **65%** of the core domain models and backend endpoints required for a functional Institutional Console already exist in the Platform API. However, they lack:
   - Dedicated Institutional Console frontend screens (the Next.js frontend currently contains only a stubbed shell at `/console/dashboard`).
   - Administrative member invitation and onboarding lifecycle (`Invitation` model / API).
   - Institution-scoped aggregation/analytics endpoints (aggregating `AgentRunRecord` tokens and active users).
   - Dedicated "Academic Structure" hierarchy (classes, courses, departments, streams).

3. **Strict Domain & Service Boundaries Must Be Enforced**:
   - The **Institutional Console** is a **Control Plane**, not an experience plane (learner/teacher chat) and not the Platform Operator Admin (Django superadmin).
   - Access governance is **server-authoritative**. The console must never rely on client-side role assertions or introduce a coarse "admin = can do everything" bypass.

---

## 2. Current Platform Architecture Relevant to Institutions

Mwalimu strictly enforces a tri-plane architectural separation:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             EXPERIENCE PLANE                                │
│   Learner & Teacher Chat, Lesson Planning, Interactive Problem Solving     │
│   Surface: app.ai-mwalimu.com (Next.js App Router: /(app)/...)              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Consumes
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                              CONTROL PLANE                                  │
│             Institutional Console (Workspace for Governance)                │
│   People, Libraries, Resources, Policies, Context, Connections, Analytics   │
│   Surface: console.ai-mwalimu.com (Next.js App Router: /(console)/...)      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Governs & Enforces
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                             KNOWLEDGE FABRIC                                │
│                  Platform API (Django REST Framework)                       │
│    Tenancy • Memberships • Libraries • Policies • Processing • Connectors   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Dispatches Run Records
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                         AGENT EXECUTION RUNTIME                             │
│                  Agent Service (FastAPI + OpenAI Agents SDK)                │
│    Stateless execution • MCP Tools • Prompt Hydration • Tool Streaming      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Institutional Tenancy Invariant
- An `Institution` is a logical governance and security boundary.
- A user can belong to multiple institutions (or none) via `Membership`.
- A user's active administrative privileges are evaluated on a per-institution basis via `Membership.objects.filter(user=user, institution=inst, role=MembershipRole.ADMINISTRATOR, status=MembershipStatus.ACTIVE)`.
- All institutional resources, libraries, connections, and context regions are strictly partitioned by `institution_id`.

---

## 3. Existing Institutional Capabilities

The audit verified the following active capabilities across the backend apps:

| App | Entity / Capability | Description & Institutional Scope |
|---|---|---|
| `institutions` | `Institution` | Institutional tenant entity (`id`, `name`, `slug`, `status`). First user to create an institution automatically becomes its first active `ADMINISTRATOR`. |
| `memberships` | `Membership` | Connects `User` to `Institution` with role (`administrator`, `teacher`, `student`, `librarian`) and lifecycle status (`pending`, `active`, `inactive`, `suspended`). Enforces at most one active membership per (user, institution). |
| `libraries` | `Library` | Scoped knowledge container. Supports `scope_type="institution"`. Governed by visibility (`discoverable` for institution members vs `restricted`). |
| `libraries` | `LibraryAccessPolicy` | Explicit per-library RBAC grant (`administrator`, `teacher`, `student`) for a specific user. |
| `resources` | `Resource` | Document metadata linked to a `Library`. Tracks binary in S3 storage, size, checksum, and status (`pending`, `uploading`, `ready`, `failed`, `archived`). |
| `processing` | Ingestion Pipeline | Celery-backed extractors (PDF, DOCX, TXT), hierarchical TOC parser (`DocumentStructureNode`), back-of-book indexer (`BookIndexEntry`), printed page mapper (`DocumentPageMap`), and vector embedding generation (`ChunkEmbedding`). |
| `connectors` | External Connections | Institutional integrations for Google Drive, Notion, S3, and Web Crawler. Supports credential encryption, connection status, asynchronous Celery sync jobs, and remote directory browsing. |
| `context` | `InstitutionContextRegion` | Configures geographic focus units (`GeographicUnit`) for an institution with priority rankings to steer culturally-grounded pedagogical examples. |
| `agents` | `AgentSession` & `AgentRunRecord` | Durable ledger of conversational sessions and runs. Scoped to `user` and `institution`. Tracks tokens (`prompt_tokens`, `completion_tokens`, `total_tokens`), step counts, execution timeouts, error codes, and citations. |

---

## 4. Existing API Inventory

All endpoints currently registered in `platform_api` that are relevant to institutional governance:

| Method | Endpoint | Domain | Purpose | Institution Scope | Permission / Auth | Console Consumer | Status |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/v1/institutions/` | Institution | List discoverable institutions | Public / All | Authenticated | Organization Switcher | COMPLETE |
| `POST` | `/api/v1/institutions/` | Institution | Create institution (caller becomes Admin) | Platform | Authenticated | Organization Setup | COMPLETE |
| `GET` | `/api/v1/institutions/{id}/` | Institution | Retrieve institution details | Single Institution | Authenticated | Organization Profile | COMPLETE |
| `PATCH` | `/api/v1/institutions/{id}/` | Institution | Update name/slug/status | Single Institution | Institution Admin | Organization Settings | COMPLETE |
| `DELETE` | `/api/v1/institutions/{id}/` | Institution | Delete institution | Single Institution | Institution Admin | Danger Zone | COMPLETE |
| `GET` | `/api/v1/memberships/` | Membership | List memberships (caller's or admin's inst) | Scoped to caller/admin | Authenticated | People Directory | COMPLETE |
| `POST` | `/api/v1/memberships/` | Membership | Self-request membership (forces student/pending) | Self | Authenticated | Join Institution | COMPLETE |
| `GET` | `/api/v1/memberships/{id}/` | Membership | Retrieve membership record | Caller or Inst Admin | Authenticated | Member Profile | COMPLETE |
| `PATCH` | `/api/v1/memberships/{id}/` | Membership | Update role or status (approve, suspend, promote) | Single Institution | Institution Admin | Member Actions | COMPLETE |
| `DELETE` | `/api/v1/memberships/{id}/` | Membership | Remove member from institution | Single Institution | Institution Admin | Member Removal | COMPLETE |
| `GET` | `/api/v1/libraries/` | Library | List libraries visible to user (personal + inst) | Multi-library | Authenticated | Knowledge Overview | COMPLETE |
| `POST` | `/api/v1/libraries/` | Library | Create institutional or personal library | Scoped by payload | Authenticated (Inst Admin if inst) | Create Library | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/` | Library | Retrieve library metadata | Single Library | Caller has access | Library Detail | COMPLETE |
| `PATCH` | `/api/v1/libraries/{id}/` | Library | Update library name, description, visibility | Single Library | Library / Inst Admin | Edit Library | COMPLETE |
| `DELETE` | `/api/v1/libraries/{id}/` | Library | Delete / archive library | Single Library | Library / Inst Admin | Delete Library | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/access-policies/` | Access Policy | List explicit user grants on library | Single Library | Library / Inst Admin | Access Governance | COMPLETE |
| `POST` | `/api/v1/libraries/{id}/access-policies/` | Access Policy | Grant library role to member | Single Library | Library / Inst Admin | Grant Access | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/access-policies/{pid}/` | Access Policy | Retrieve single policy grant | Single Library | Library / Inst Admin | Policy Inspector | COMPLETE |
| `PATCH` | `/api/v1/libraries/{id}/access-policies/{pid}/` | Access Policy | Update policy role (e.g. Student -> Teacher) | Single Library | Library / Inst Admin | Modify Grant | COMPLETE |
| `DELETE` | `/api/v1/libraries/{id}/access-policies/{pid}/` | Access Policy | Revoke member access grant | Single Library | Library / Inst Admin | Revoke Access | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/resources/` | Resources | List uploaded resources in library | Single Library | Caller has access | Resource Explorer | COMPLETE |
| `POST` | `/api/v1/libraries/{id}/resources/` | Resources | Upload and ingest document into library | Single Library | Library / Inst Admin | Upload Resource | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/resources/{rid}/` | Resources | Retrieve resource metadata | Single Library | Caller has access | Resource Detail | COMPLETE |
| `PATCH` | `/api/v1/libraries/{id}/resources/{rid}/` | Resources | Rename or update resource metadata | Single Library | Library / Inst Admin | Edit Resource | COMPLETE |
| `DELETE` | `/api/v1/libraries/{id}/resources/{rid}/` | Resources | Delete resource and trigger vector cleanup | Single Library | Library / Inst Admin | Delete Resource | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/resources/{rid}/download/` | Resources | Get signed URL / stream original binary | Single Library | Caller has access | Document Viewer | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/resources/{rid}/processing-status/` | Resources | Inspect processing runs & extraction status | Single Library | Caller has access | Pipeline Inspector | COMPLETE |
| `POST` | `/api/v1/libraries/{id}/resources/{rid}/processing-status/` | Resources | Trigger manual re-indexing / re-processing | Single Library | Library / Inst Admin | Reprocess Trigger | COMPLETE |
| `GET` | `/api/v1/connectors/` | Connectors | List global connector catalog | Global Catalog | Authenticated | Connection Catalog | COMPLETE |
| `GET` | `/api/v1/connectors/{id}/` | Connectors | Retrieve connector schema & auth requirements | Global Catalog | Authenticated | Connection Wizard | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/connections/` | Connectors | List external connections configured in library | Single Library | Library / Inst Admin | Connections List | COMPLETE |
| `POST` | `/api/v1/libraries/{id}/connections/` | Connectors | Create & authenticate external connection | Single Library | Library / Inst Admin | Add Connection | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/connections/{cid}/` | Connectors | Inspect connection status & credentials state | Single Library | Library / Inst Admin | Connection Detail | COMPLETE |
| `PATCH` | `/api/v1/libraries/{id}/connections/{cid}/` | Connectors | Update connection config / sync frequency | Single Library | Library / Inst Admin | Edit Connection | COMPLETE |
| `DELETE` | `/api/v1/libraries/{id}/connections/{cid}/` | Connectors | Remove external connection | Single Library | Library / Inst Admin | Delete Connection | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/connections/{cid}/browse/` | Connectors | Browse remote folder hierarchy (Drive/S3) | Single Library | Library / Inst Admin | Remote Tree Browser | COMPLETE |
| `POST` | `/api/v1/libraries/{id}/connections/{cid}/sync/` | Connectors | Trigger asynchronous Celery sync job | Single Library | Library / Inst Admin | Manual Sync Now | COMPLETE |
| `GET` | `/api/v1/libraries/{id}/connections/{cid}/sync-jobs/` | Connectors | List historical sync runs and error details | Single Library | Library / Inst Admin | Sync History Log | COMPLETE |
| `GET` | `/api/v1/institutions/{id}/context-regions/` | Context | List priority geographic catchment units | Single Institution | Authenticated Member | Context Settings | COMPLETE |
| `POST` | `/api/v1/institutions/{id}/context-regions/` | Context | Assign geographic unit to institution focus | Single Institution | Institution Admin | Add Focus Region | COMPLETE |
| `DELETE` | `/api/v1/institutions/{id}/context-regions/{pk}/` | Context | Remove geographic unit from focus | Single Institution | Institution Admin | Remove Focus Region | COMPLETE |
| `PUT` | `/api/v1/institutions/{id}/context-regions/reorder/` | Context | Reorder priority hierarchy of context regions | Single Institution | Institution Admin | Rank Focus Regions | COMPLETE |
| `POST` | `/api/v1/knowledge/search/` | Knowledge | Search authorized knowledge with full Stage 10 pipeline | Server-Authoritative Scope | Authenticated | Knowledge Testbed | COMPLETE |

---

## 5. Existing Authorization Model

Mwalimu’s authorization architecture is **multi-layered, deterministic, and server-authoritative**:

```text
                                  User Request
                                       │
                                       ▼
                       [1. Bearer Token Authentication]
                                       │
                                       ▼
                       [2. Institution Membership Check]
              Is caller an active member of target institution?
                                ├── NO  ──► HTTP 403 / 404 (Fail Closed)
                                └── YES
                                       ▼
                         [3. Institution Role Check]
                     Is caller an active ADMINISTRATOR?
                                ├── YES ──► Grant Full Institutional Management
                                └── NO
                                       ▼
                          [4. Library Boundary Check]
                           Is library personal or inst?
                                       │
                                       ▼
                          [5. Visibility & Policy Grant]
            • Personal: owner_id == user.id
            • Discoverable: Active member of institution can READ
            • Restricted: Must have row in LibraryAccessPolicy (Admin, Teacher, Student)
                                       │
                                       ▼
                          [6. Effective Retrieval Scope]
      frozenset(authorized_library_ids) + frozenset(authorized_resource_ids)
                                       │
                                       ▼
                          [7. Database Query Execution]
```

### Critical Security Properties:
1. **Never Trust User IDs in Payloads**: In `MembershipViewSet` and `LibraryViewSet`, caller identity is derived strictly from `request.user`. Passing arbitrary `user_id` or `institution_id` in creation payloads cannot hijack identities.
2. **Strict Cross-Tenant Isolation**: An administrator of Institution A receives `HTTP 404 Not Found` when attempting to access or modify records belonging to Institution B.
3. **Fail-Closed Retrieval**: The Knowledge Gateway (`EffectiveRetrievalScope`) denies all vector and lexical retrieval if a user does not have an active policy or discoverable membership for the library.

---

## 6. Existing Knowledge / Library Capabilities

The Knowledge Fabric was fortified across Stages 1–10 and is completely accessible for institutional governance:

1. **Hierarchical Document Outlines**:
   - `DocumentStructureNode` stores hierarchical TOC structures (chapters, sections, subsections, sequence numbers, page bounds).
   - Institutional admins can inspect structural navigation trees for uploaded textbooks.
2. **Back-of-Book Subject Index**:
   - `BookIndexEntry` stores parsed textbook indices, child terms, and physical/printed page references.
3. **Printed-to-Physical Page Mapping**:
   - `DocumentPageMap` maps physical PDF pages to printed roman/arabic numerals (`p. 36`, `pp. 38–39`), eliminating front-matter page drift.
4. **Adaptive Context & Evidence Quality**:
   - Chunks are evaluated for factual directness, definition completeness, and procedural step coherence.
   - High-quality answer-ready clusters are dynamically identified.
5. **Sentence-Level Citation Assembly**:
   - Extractive answer spans pinpoint exact sentence character offsets (`char_start`, `char_end`) and semantic roles.

---

## 7. Institutional Capability Matrix

| Domain | Capability | Existing Model | Existing API | Authorization | Tests | Maturity | Console Need | Gap | Priority |
|---|---|---|---|---|---|---|---|---|---|
| **A. Identity & Institution** | Institution Profile & Lifecycle | `Institution` | `/api/v1/institutions/{id}/` | Inst Admin update/delete | Yes (`test_institutions.py`) | **COMPLETE** | Workspace header, org settings | None | **P0** |
| **A. Identity & Institution** | Multi-Institution Switcher | `Institution`, `Membership` | `/api/v1/institutions/`, `/api/v1/memberships/` | Authenticated | Yes | **BACKEND_EXISTS_UI_MISSING** | Top-nav tenant switcher dropdown | UI component only | **P0** |
| **B. People & Membership** | Member Directory Listing | `Membership`, `User`, `UserProfile` | `/api/v1/memberships/` | Inst Admin sees all members | Yes (`test_memberships.py`) | **COMPLETE** | Member table with search/filter | Filter query params | **P0** |
| **B. People & Membership** | Member Role Modification | `Membership` | `PATCH /api/v1/memberships/{id}/` | Inst Admin only | Yes | **COMPLETE** | Role dropdown in member row | None | **P0** |
| **B. People & Membership** | Member Suspension / Activation | `Membership` | `PATCH /api/v1/memberships/{id}/` | Inst Admin only | Yes | **COMPLETE** | Status toggle action button | None | **P0** |
| **B. People & Membership** | Member Removal | `Membership` | `DELETE /api/v1/memberships/{id}/` | Inst Admin only | Yes | **COMPLETE** | "Remove from institution" modal | None | **P0** |
| **B. People & Membership** | Direct Member Invitation | *None* | *None* | *None* | No | **DOMAIN_MISSING** | "Invite Member" modal by email | `Invitation` model + email dispatch | **P0** |
| **B. People & Membership** | Bulk CSV Member Import | *None* | *None* | *None* | No | **DOMAIN_MISSING** | CSV upload modal | Batch user/member creation task | **P1** |
| **C. Roles & Capabilities** | Static Institutional RBAC | `MembershipRole` (4 roles) | `/api/v1/memberships/` | Server-authoritative | Yes | **COMPLETE** | Role badges & permissions matrix | None | **P0** |
| **C. Roles & Capabilities** | Custom Roles & Granular Perms | *None* | *None* | *None* | No | **FUTURE** | Custom role editor | Granular permission registry | **P3** |
| **D. Academic Structure** | Academic Hierarchy (Classes, Courses) | *None* | *None* | *None* | No | **DOMAIN_MISSING** | Classes/Subjects workspace | `AcademicYear`, `Course`, `ClassRoom` | **P2** |
| **E. Knowledge & Libraries** | Institutional Library Management | `Library` | `/api/v1/libraries/` | Inst Admin create/edit/delete | Yes (`test_libraries.py`) | **COMPLETE** | Libraries list, creation wizard | UI views only | **P0** |
| **E. Knowledge & Libraries** | Library Visibility Governance | `Library.visibility` | `PATCH /api/v1/libraries/{id}/` | Inst Admin | Yes | **COMPLETE** | Discoverable/Restricted radio switch | None | **P0** |
| **F. Resources & Ingestion** | Resource Repository Explorer | `Resource` | `/api/v1/libraries/{id}/resources/` | Caller has library access | Yes (`test_resources.py`) | **COMPLETE** | Resource table with status badges | UI views only | **P0** |
| **F. Resources & Ingestion** | Document Upload & Extraction | `Resource`, `ProcessingRun` | `POST /api/v1/libraries/{id}/resources/` | Library / Inst Admin | Yes | **COMPLETE** | Drag-and-drop file uploader | UI views only | **P0** |
| **F. Resources & Ingestion** | Ingestion & Processing Inspector | `ProcessingRun`, `DocumentStructureNode` | `GET /.../processing-status/` | Caller has access | Yes | **COMPLETE** | Pipeline stepper / run logs modal | UI view only | **P0** |
| **F. Resources & Ingestion** | Reprocess Document Trigger | `ProcessingRun` | `POST /.../processing-status/` | Library / Inst Admin | Yes | **COMPLETE** | "Reprocess / Re-index" button | None | **P1** |
| **G. Access Governance** | Library Access Grants | `LibraryAccessPolicy` | `/api/v1/libraries/{id}/access-policies/` | Library / Inst Admin | Yes (`test_libraries.py`) | **COMPLETE** | Library policy table & grant modal | UI views only | **P0** |
| **G. Access Governance** | User Access Requests | `Membership` (`status="pending"`) | `/api/v1/memberships/` | Inst Admin approves via PATCH | Yes | **PARTIAL** | "Pending Requests" badge & table | Self-request exists; dedicated review UI needed | **P0** |
| **H. External Connections** | External Knowledge Connectors | `Connector`, `Connection` | `/api/v1/libraries/{id}/connections/` | Library / Inst Admin | Yes (`test_connector_api.py`) | **COMPLETE** | Connections tab under library | UI views only | **P1** |
| **H. External Connections** | Connection Sync & History | `ConnectionSyncJob` | `/.../sync/`, `/.../sync-jobs/` | Library / Inst Admin | Yes | **COMPLETE** | "Sync Now" button + job history table | None | **P1** |
| **H. External Connections** | Remote Directory Browser | `RemoteBrowserView` | `/.../connections/{id}/browse/` | Library / Inst Admin | Yes (`test_remote_browser_api.py`) | **COMPLETE** | Drive / S3 folder tree picker | UI tree component | **P1** |
| **I. AI Usage & Telemetry** | Token & Step Accounting | `AgentRunRecord` | Database model only | Model exists; API missing | Yes (`test_agent_models.py`) | **API_MISSING** | Usage overview cards & charts | Institutional aggregation API needed | **P1** |
| **I. AI Usage & Telemetry** | Institutional Quotas & Limits | *None* | *None* | *None* | No | **DOMAIN_MISSING** | Quota gauges & alert thresholds | `InstitutionQuota` model + middleware | **P2** |
| **J. Analytics & Reporting** | Active Users & Question Metrics | `AgentRunRecord`, `Membership` | Database models only | Models exist; API missing | Yes | **API_MISSING** | Console dashboard stat cards | Analytics aggregate endpoint needed | **P1** |
| **K. Security & Audit** | Audit Logging | *None* | *None* | *None* | No | **DOMAIN_MISSING** | Audit log table | `AuditEvent` model + logging hook | **P2** |
| **L. Billing & Subscriptions** | Institutional Plans & Invoicing | *None* | *None* | *None* | No | **FUTURE** | Billing & invoices workspace | Payment gateway integration | **P3** |
| **M. API / Developer Management** | Institutional API Keys | *None* | *None* | *None* | No | **FUTURE** | API Keys manager | `InstitutionApiKey` model + auth | **P3** |
| **N. Context & Localization** | Institution Context Regions | `InstitutionContextRegion` | `/api/v1/institutions/{id}/context-regions/` | Inst Admin | Yes (`test_context_api.py`) | **COMPLETE** | Geographic focus region manager | UI views only | **P1** |

---

## 8. Console Workspace Mapping

This table maps the proposed Institutional Console workspaces to existing platform capabilities and highlights specific frontend/backend tasks:

| Console Workspace | Institutional Activity | Existing Backend Capability | Existing Endpoint(s) | Missing Backend Capability | Frontend UI Needed | Priority |
|---|---|---|---|---|---|---|
| **Overview / Dashboard** | High-level health, user counts, knowledge assets, token usage | `Membership`, `Library`, `Resource`, `AgentRunRecord` | None (raw lists exist) | Dedicated `/api/v1/institutions/{id}/overview/` metric endpoint | Metric cards, quick actions, recent activity list | **P0** |
| **Organization Settings** | Manage name, slug, status, logo, metadata | `Institution` model | `GET/PATCH /api/v1/institutions/{id}/` | None | Organization profile form, slug validator, danger zone (archive/delete) | **P0** |
| **People & Memberships** | View members, approve requests, change roles, deactivate users | `Membership` model & ViewSet | `GET/PATCH/DELETE /api/v1/memberships/` | Invitation endpoint (`POST /api/v1/institutions/{id}/invitations/`) | Member data-table, role selector, status badge, invite modal | **P0** |
| **Libraries & Knowledge** | Create institutional libraries, configure discovery, archive | `Library` model & ViewSet | `GET/POST/PATCH/DELETE /api/v1/libraries/` | None (supports `scope_type="institution"`) | Library card grid, creation modal, visibility toggles | **P0** |
| **Access Policies** | Grant per-library roles (Admin, Teacher, Student) to members | `LibraryAccessPolicy` ViewSet | `GET/POST/PATCH/DELETE /api/v1/libraries/{id}/access-policies/` | None | Per-library access matrix, member picker, role editor | **P0** |
| **Resources & Documents** | Upload PDFs/DOCX, inspect processing runs, trigger re-index | `Resource` ViewSet & processing pipeline | `/api/v1/libraries/{id}/resources/`, `.../processing-status/` | None | File upload dropzone, processing status stepper, document preview | **P0** |
| **External Connections** | Link Google Drive, Notion, S3, Web Crawlers, trigger sync | `connectors` app ViewSets | `/api/v1/libraries/{id}/connections/`, `.../sync/`, `.../browse/` | None | Connector catalog cards, connection config form, sync history drawer | **P1** |
| **Context & Localization** | Manage geographic catchment regions for pedagogical relevance | `context` app ViewSets | `/api/v1/institutions/{id}/context-regions/` | None | Geographic region list, country/district autocomplete, priority drag-handle | **P1** |
| **Usage & Analytics** | View token consumption, questions asked, top active libraries | `AgentRunRecord` model | None (model only) | Aggregated endpoint: `/api/v1/institutions/{id}/analytics/usage/` | Token usage line chart, cost/quota progress bars, top queried topics | **P1** |
| **Academic Hierarchy** | Manage classes, streams, subjects, teacher-student pairings | None | None | New `academic` app (`AcademicYear`, `Course`, `ClassRoom`) | Classes tree, course assignment matrix | **P2** |
| **Audit Logs** | Track administrator actions, policy changes, membership edits | None | None | `AuditEvent` model + DRF view | Timestamped immutable activity log with actor/diff | **P2** |
| **Billing & Subscriptions** | Manage institutional tiers, seats, invoices, payment methods | None | None | External billing gateway (Stripe/Flutterwave) | Subscription card, invoice download table | **P3** |

---

## 9. Missing Capabilities (Gaps to Close)

The following capabilities are completely absent from the backend:

1. **Direct Member Invitation (`Invitation`)**:
   - *Current State*: Users must already have an account and call `POST /api/v1/memberships/` to request access, which an admin then approves via `PATCH`.
   - *Missing*: An institution admin cannot currently enter an email address (e.g. `teacher@school.edu`) to invite them with a pre-assigned role (`TEACHER`).
   - *Impact*: Onboarding institutional staff currently requires out-of-band communication.

2. **Institution Overview & Aggregated Analytics API**:
   - *Current State*: `AgentRunRecord` records tokens, steps, and timestamps per run with `session__institution_id`. `Membership` records users.
   - *Missing*: An API endpoint that aggregates these records (`total_tokens_this_month`, `active_members_count`, `queries_today`, `tokens_by_day`).
   - *Impact*: The console dashboard cards currently have to render "—" because there is no summary endpoint.

3. **Academic Structure Models**:
   - *Current State*: Roles are flat (`teacher`, `student`). There is no concept of Grade 10, Form 4, Stream A, Chemistry 101, or Course Sections.
   - *Missing*: Models for `AcademicYear`, `GradeLevel`, `ClassRoom`, `Course`, and `Enrollment`.
   - *Impact*: Teaching assignments cannot be modeled directly yet.

4. **Security Audit Log (`AuditEvent`)**:
   - *Current State*: Model updates alter `updated_at`, but historical mutation records (who changed a member's role from Student to Admin, who deleted a library, who revoked an access policy) are not captured in an immutable audit ledger.

---

## 10. Partial Capabilities

1. **Membership Lifecycle**:
   - Self-request (`PENDING`), approval (`ACTIVE`), suspension (`SUSPENDED`), and deletion are implemented.
   - *Gap*: Lacks email notifications on approval/rejection and tokenized invitation acceptance.

2. **AI Telemetry & Usage**:
   - Every agent execution dispatched through the Platform API persists an `AgentRunRecord` containing `prompt_tokens`, `completion_tokens`, `total_tokens`, `step_count`, `timeout_seconds`, and `status`.
   - *Gap*: No quota bounding (no monthly token ceiling or alert threshold per institution).

---

## 11. Backend-Exists / UI-Missing Capabilities

The following capabilities are **100% complete and tested in the backend**, needing **only frontend UI implementation** in the Institutional Console:

1. **Institution Settings & Metadata**:
   - `GET /api/v1/institutions/{id}/`, `PATCH /api/v1/institutions/{id}/`, `DELETE /api/v1/institutions/{id}/`.
2. **Member Management**:
   - `GET /api/v1/memberships/` (filtered by admin's institution), `PATCH /api/v1/memberships/{id}/` (role/status), `DELETE /api/v1/memberships/{id}/`.
3. **Institutional Libraries**:
   - `GET /api/v1/libraries/` (supports `scope_type=institution`), `POST /api/v1/libraries/`, `PATCH /api/v1/libraries/{id}/`, `DELETE /api/v1/libraries/{id}/`.
4. **Library Access Policies (RBAC)**:
   - `GET /api/v1/libraries/{id}/access-policies/`, `POST /api/v1/libraries/{id}/access-policies/`, `PATCH /.../{pid}/`, `DELETE /.../{pid}/`.
5. **Resource Management & Ingestion**:
   - `GET /api/v1/libraries/{id}/resources/`, `POST /.../resources/` (multipart upload), `DELETE /.../resources/{id}/`, `GET /.../download/`, `GET /.../processing-status/`, `POST /.../processing-status/` (reprocess).
6. **External Connectors & Synchronization**:
   - `GET /api/v1/libraries/{id}/connections/`, `POST /.../connections/`, `GET /.../browse/`, `POST /.../sync/`, `GET /.../sync-jobs/`.
7. **Institutional Context Catchment Regions**:
   - `GET /api/v1/institutions/{id}/context-regions/`, `POST /.../context-regions/`, `DELETE /.../context-regions/{pk}/`, `PUT /.../context-regions/reorder/`.

---

## 12. Security & Governance Gaps

1. **Explicit Institution Scope in Console Requests**:
   - *Observation*: Currently, `MembershipViewSet.get_queryset()` returns memberships for *all* institutions where the caller is an admin.
   - *Recommendation*: In the Institutional Console, the UI must operate under an explicit active institution context (`X-Institution-Id` header or query parameter `?institution_id=<uuid>`), verified server-side against caller's active memberships.

2. **Cross-Tenant Leakage Prevention**:
   - *Verification*: Existing tests in `test_institutions.py` (`test_admin_of_other_institution_cannot_modify_institution`) and `test_memberships.py` (`test_admin_cannot_manage_other_institution_memberships`) confirm that admins cannot read or mutate entities outside their own institution. This fail-closed invariant must be maintained.

---

## 13. AI Usage & Analytics Readiness

### What Telemetry Already Exists:
In `platform_api/src/platform_api/apps/agents/models.py`:
- `AgentRunRecord`:
  - `user`: Foreign key to `User`.
  - `session__institution`: Foreign key to `Institution`.
  - `prompt_tokens`: Positive integer.
  - `completion_tokens`: Positive integer.
  - `total_tokens`: Positive integer.
  - `step_count`: Positive integer.
  - `created_at`, `queued_at`, `started_at`, `completed_at`.
  - `status`: `AgentRunStatus` (`COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`).

### What Is Missing:
- Aggregated endpoints to answer:
  - "How many tokens did our institution consume this billing period?"
  - "Which libraries or users are driving the highest AI usage?"
  - "What is our daily query volume trend over the last 30 days?"
- Quota definition (`monthly_token_budget`, `hard_limit_action`).

---

## 14. API Key & Developer Console Readiness

- **Current Status**: **FUTURE / NOT IMPLEMENTED**.
- There are no models for institutional API keys or service accounts. The only API keys currently in the repository are outbound keys for external LLM/embedding providers and third-party connector credentials.
- **Verdict**: Defer to a future Developer Platform phase. The Institutional Console V1 should focus on human institutional administrators, not programmatic API key distribution.

---

## 15. Billing & Subscription Readiness

- **Current Status**: **FUTURE / NOT IMPLEMENTED**.
- No models exist for plans, subscriptions, seats, or payment gateways.
- **Verdict**: Defer billing integrations. Institutional provisioning for V1 should operate under an "Enterprise / Institutional Pilot" posture where institutions are provisioned directly by platform administrators.

---

## 16. Recommended Institutional Console V1

Based on what is **already implemented and tested in the backend**, Institutional Console V1 should focus on providing an institutional control plane across **6 core workspaces**:

```text
INSTITUTIONAL CONSOLE V1
├── 1. Overview / Dashboard
│      └── Key stats (Members count, Library count, Resource count), quick actions
├── 2. People & Members
│      ├── Member Directory (Search, filter by Role & Status)
│      ├── Pending Access Requests (Review & Approve/Reject)
│      └── Role Management (Promote to Teacher/Admin, Deactivate, Remove)
├── 3. Libraries & Knowledge
│      ├── Institutional Libraries (Create, configure visibility discoverable/restricted)
│      └── Library Access Policies (Grant per-library access to members)
├── 4. Resources & Documents
│      ├── Upload & Ingestion (Drag-and-drop PDF/DOCX, progress indicator)
│      ├── Processing Inspector (View TOC nodes, index terms, page maps)
│      └── Document Lifecycle (Download original, re-index, delete)
├── 5. External Connections
│      ├── Connectors Catalog (Google Drive, Notion, S3, Web Crawler)
│      ├── Active Connections (Configure, trigger manual sync, view job history)
│      └── Remote File Browser (Browse external folders directly)
└── 6. Institution Settings
       ├── Profile (Name, Slug, Status)
       └── Context Catchment (Configure localized geographic priority units)
```

---

## 17. Recommended Future Phases

* **Phase 1 (Immediate)**: Console V1 Implementation (Wiring existing backend APIs to dedicated Next.js console views).
* **Phase 2 (Onboarding Hardening)**: Direct Email Invitations (`Invitation` model) and Bulk CSV Member Import.
* **Phase 3 (Telemetry & Controls)**: Institutional Analytics API (Aggregating `AgentRunRecord`) and Quota Limits.
* **Phase 4 (Academic Structure)**: Academic Hierarchy (`AcademicYear`, `Course`, `ClassRoom`, `TeachingAssignment`).
* **Phase 5 (Enterprise Governance)**: Immutable Audit Log (`AuditEvent`), SSO / SAML integration, and API Keys.
* **Phase 6 (Monetization)**: Billing, Subscription tiers, Seat management, and Invoicing.

---

## 18. Domain / API Changes Required for V1

To make Console V1 completely seamless, only **two minor backend additions** are recommended:

1. **Institutional Overview Aggregation Endpoint** (`GET /api/v1/institutions/{id}/overview/`):
   - Returns counts of active members (broken down by role), institutional libraries, uploaded resources, and pending membership requests in a single round-trip.
2. **Member Filtering by Institution** on `/api/v1/memberships/`:
   - Ensure `?institution_id=<uuid>` explicitly scopes the member listing when an administrator manages multiple institutions.

No other backend domain modifications are necessary for V1; all other workflows are already supported by existing endpoints.

---

## 19. Proposed Console Information Architecture

```text
console.ai-mwalimu.com (or /console on frontend)
│
├── /console/dashboard                          (Overview metric cards & quick actions)
├── /console/people                             (Member directory & role management)
│   └── /console/people/requests                (Pending join requests queue)
├── /console/libraries                          (Institutional libraries grid)
│   ├── /console/libraries/new                  (Library creation modal)
│   └── /console/libraries/[id]                 (Library detail & tab navigation)
│       ├── /console/libraries/[id]/resources   (Uploaded documents & processing status)
│       ├── /console/libraries/[id]/access      (Library-specific access policies)
│       └── /console/libraries/[id]/connections (Google Drive / S3 external connections)
├── /console/context                            (Geographic catchment priority management)
└── /console/settings                           (Institution name, slug, danger zone)
```

---

## 20. Architectural Risks & Mitigations

| Risk | Impact | Mitigation Strategy |
|---|---|---|
| **Multi-Institution Admin Confusion** | Admin of School A accidentally mutates School B | Enforce explicit institution selection in Console UI; pass `institution_id` query parameter; verify server-side in DRF permission classes. |
| **Ingestion Bottleneck on Large Uploads** | Large textbook batch uploads exhaust Celery worker concurrency | Existing architecture already runs workers asynchronously with Redis queues; UI should show asynchronous processing status rather than blocking requests. |
| **Accidental Over-Privilege** | Granting institutional admin role grants full control | Keep `LibraryAccessPolicy` independent from `MembershipRole`. An institutional admin manages the institution; library admins manage specific libraries. Maintain this separation. |
| **Analytics Query Latency** | Computing `AgentRunRecord` token aggregates across millions of rows causes slow dashboard loads | Add composite index `(session__institution, created_at)` to `AgentRunRecord`; run aggregated counts via periodic Celery rollups or bounded date ranges. |

---

## 21. Recommended Implementation Order

1. **Step 1: Institutional Overview Summary Endpoint (Backend)**:
   Implement lightweight `/api/v1/institutions/{id}/overview/` endpoint to feed dashboard metrics.
2. **Step 2: Console Institution Shell & Multi-Tenant Switcher (Frontend)**:
   Replace placeholder institutional name in `institution-shell.tsx` with dynamic institution switcher populated from caller's active admin memberships.
3. **Step 3: People & Memberships Workspace (Frontend)**:
   Build member directory, role modifier dropdown, status toggle (active/suspended), and pending requests tab consuming `/api/v1/memberships/`.
4. **Step 4: Libraries & Resources Workspaces (Frontend)**:
   Build institutional libraries catalog, drag-and-drop resource uploader, and processing run inspector consuming `/api/v1/libraries/` and `/api/v1/libraries/{id}/resources/`.
5. **Step 5: Access Governance Workspace (Frontend)**:
   Build per-library RBAC matrix consuming `/api/v1/libraries/{id}/access-policies/`.
6. **Step 6: Context & Connections Workspaces (Frontend)**:
   Build context catchment manager consuming `/api/v1/institutions/{id}/context-regions/` and external connections manager consuming `/api/v1/libraries/{id}/connections/`.

---

## 22. Explicit "DO NOT BUILD YET" Items

To adhere strictly to YAGNI and prevent speculative complexity:

- **DO NOT build custom role builders** (stick to the 4 robust static roles: Administrator, Teacher, Student, Librarian).
- **DO NOT build billing / payment gateways** (operate under pilot/enterprise agreements).
- **DO NOT build developer API keys or webhook managers** (defer to Developer Platform phase).
- **DO NOT build complex course/gradebook academic structures** until core member and library management is field-tested.
- **DO NOT build chat or learner interfaces in the console** (the console is strictly a governance control plane).

---

## 23. Final Recommendation

> **Based on the repository audit, the next engineering stage should be:**
> 
> **"Implement Institutional Console V1 by constructing the frontend control plane screens against the existing Platform API endpoints, supplemented only by an institutional overview summary endpoint."**
> 
> - **What should be built first**: Overview dashboard, People management, Libraries catalog, and Resource ingestion inspector.
> - **What should be reused**: Existing `institutions`, `memberships`, `libraries`, `resources`, `processing`, `connectors`, and `context` models and APIs.
> - **What backend gaps must be closed**: A lightweight summary endpoint `GET /api/v1/institutions/{id}/overview/` to supply dashboard counts, followed in Phase 2 by an `Invitation` model.
> - **What should be deferred**: Billing, API keys, custom roles, and academic gradebooks.
