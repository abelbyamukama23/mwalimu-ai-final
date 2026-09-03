# Mwalimu — Institutional Console: Phase 4 Architecture & Capability Audit
## Institutional Intelligence, Usage Analytics, Audit Governance & Connectors

---

## 1. Executive Summary

This document establishes the architectural reconnaissance, capability audit, and engineering blueprint for **Phase 4** of the **Mwalimu Institutional Console**.

The Institutional Console is an independent Next.js 16 application and independent Git repository located at `Desktop/mwalimu-console/`. The authoritative backend system of record remains `Desktop/mwalimu_final/platform_api`. 

In Phase 3, the core operational workspaces (**People**, **Libraries**, **Resources**, and **Access**) were delivered and verified with 43 passing backend tests and clean Next.js production builds.

The objective of **Phase 4** is to equip institutional leaders with:
1. **Institutional Overview & Intelligence**: Server-aggregated real-time health, resource volume, active member demographics, and activity streams.
2. **AI Usage & Token Telemetry**: Operational token accounting (prompt, completion, total), run frequency, active AI users, and trends over time derived from `AgentRunRecord`.
3. **Administrative Audit Governance**: An immutable, server-authoritative audit ledger capturing security-relevant mutations (role changes, access policy grants/revocations, resource deletions, connector modifications).
4. **External Knowledge Connectors**: Surfacing the backend's existing connector infrastructure (`Google Drive`, `Notion`, `Amazon S3`, `Web Crawler`) into a dedicated control-plane management workspace with zero secret exposure.
5. **Institutional Focus & Context Regions**: Exposing the existing `InstitutionContextRegion` and `GeographicUnit` domain in Organization Settings for pedagogical catchment localization.

In strict adherence to engineering principles, **no production code, migrations, or frontend pages are created in this phase**. This document forms the complete, vetted technical foundation required before Phase 4 implementation begins.

---

## 2. Existing Backend Capability Inventory

A systematic audit of all apps in `platform_api/src/platform_api/apps/` revealed the following capabilities:

### A. `agents` App (`platform_api/src/platform_api/apps/agents/`)
* **`AgentSession`**: Represents a conversational thread.
  - Linked to `institution` via ForeignKey `institution_id` with composite database index `Index(fields=["institution", "-updated_at"])`.
  - Linked to `user` (ForeignKey), `primary_library` (ForeignKey, null=True), and lifecycle status (`active`, `archived`).
* **`AgentRunRecord`**: Durable system-of-record execution ledger.
  - Linked to `session` (ForeignKey to `AgentSession`), allowing tenant resolution via `session__institution_id`.
  - Linked to `user` (ForeignKey to `User`).
  - Stores execution metrics: `prompt_tokens` (PositiveIntegerField), `completion_tokens` (PositiveIntegerField), `total_tokens` (PositiveIntegerField), `step_count` (PositiveIntegerField).
  - Stores timing and lifecycle: `created_at`, `queued_at`, `started_at`, `finished_at`, `updated_at`.
  - Stores status: `created`, `queued`, `running`, `awaiting_input`, `completed`, `failed`, `cancelled`, `timed_out`.
  - Stores error reporting: `error_code` (max 100), `error_message` (TextField).
  - Stores reasoning artifacts: `prompt`, `answer`, `citations` (JSON list of 14-field citation evidence objects).
* **Current API Endpoints**:
  - `GET /api/v1/sessions/`, `POST /api/v1/sessions/`
  - `GET /api/v1/sessions/{id}/`, `POST /api/v1/sessions/{id}/runs/`
  - `GET /api/v1/runs/{id}/`, `POST /api/v1/runs/{id}/cancel/`
  - `POST /api/v1/internal/runs/{id}/completion/`
* **Status**: **PARTIAL**. Telemetry data exists in the database with strict institution linkage, but there is **no aggregate usage endpoint** for institutional administrators.

### B. `connectors` App (`platform_api/src/platform_api/apps/connectors/`)
* **`Connector`**: Global catalog definition of external knowledge sources. Zero credentials stored.
  - Types: `web_crawler`, `google_drive`, `notion`, `s3`, `file_system`, `custom`.
  - Auth types: `none`, `api_key`, `oauth2`, `basic_auth`, `bearer_token`.
  - Validates `config_schema` and `auth_schema` using JSON Schema definitions.
* **`Connection`**: Instantiated link scoped to a specific `Library`.
  - Linked to `library` (ForeignKey), `connector` (ForeignKey), `created_by` (ForeignKey).
  - Stores credentials using AES-GCM envelope encryption (`encrypted_credentials` text column, decrypted via `connectors/crypto.py`).
  - Operational fields: `status` (`active`, `inactive`, `error`, `syncing`), `sync_frequency` (`manual`, `hourly`, `daily`, `weekly`), `last_synced_at`, `last_sync_status` (`success`, `partial`, `failed`), `last_sync_error`.
  - Serializer protection: `ConnectionListSerializer` and `ConnectionDetailSerializer` strictly return `has_credentials: bool`. Raw or encrypted credentials are **never** serialized.
* **`ConnectionSyncJob`**: Execution and observability run record.
  - Fields: `status` (`queued`, `running`, `completed`, `failed`, `cancelled`), `celery_task_id`, `resources_discovered`, `resources_created`, `resources_updated`, `resources_deleted`, `error_code`, `error_message`, `started_at`, `finished_at`.
* **Current API Endpoints**:
  - `GET /api/v1/connectors/`, `GET /api/v1/connectors/{id}/`
  - `GET /api/v1/libraries/{library_id}/connections/`, `POST /api/v1/libraries/{library_id}/connections/`
  - `GET /api/v1/libraries/{library_id}/connections/{id}/`, `PATCH ...`, `DELETE ...`
  - `POST /api/v1/libraries/{library_id}/connections/{id}/sync/`
  - `GET /api/v1/libraries/{library_id}/connections/{id}/sync-jobs/`
  - `GET /api/v1/libraries/{library_id}/connections/{id}/browse/`
* **Status**: **EXISTS**. Completely functional backend and Celery task execution, but currently lacks an institution-level cross-library list endpoint and has no console UI.

### C. `context` App (`platform_api/src/platform_api/apps/context/`)
* **`InstitutionContextRegion`**: Configured geographic priority regions for an institution.
  - Fields: `institution` (ForeignKey), `geographic_unit` (ForeignKey to `GeographicUnit`), `priority` (rank starting at 1).
* **`GeographicUnit`**: Reference hierarchy (e.g. Uganda $\rightarrow$ Central $\rightarrow$ Wakiso $\rightarrow$ Entebbe).
* **Current API Endpoints**:
  - `GET/POST /api/v1/institutions/{institution_id}/context-regions/`
  - `DELETE /api/v1/institutions/{institution_id}/context-regions/{pk}/`
  - `PUT /api/v1/institutions/{institution_id}/context-regions/reorder/`
  - `GET /api/v1/context/geographic-units/`
* **Status**: **EXISTS**. Fully implemented and tested in the Platform API, but not yet exposed in the Institutional Console Settings workspace.

### D. `processing` App (`platform_api/src/platform_api/apps/processing/`)
* **`ProcessingRun`**: Execution record of resource ingestion.
  - Fields: `status` (`queued`, `processing`, `ready`, `failed`), `current_stage` (`extract`, `normalize`, `chunk`, `embed`, `index`, `finalize`), `error_code`, `error_message`, `attempt_count`, `is_active`.
* **`DocumentChunk`**: Vectorized chunks with pgvector embeddings (`ChunkEmbedding`).
* **Status**: **EXISTS**. Direct inspection available via `/api/v1/libraries/{lib_id}/resources/{id}/processing-status/`.

### E. Audit Ledger
* **Current State**: **MISSING**. There are currently no audit log models, event tables, or activity tracking mechanisms in the backend. Administrative mutations are executed directly in ViewSets without durable event recording.

---

## 3. Existing Console Capability Inventory

An audit of `mwalimu-console/src/` established the following operational baseline:
* **Shell & Layout**: Responsive administrative layout with top-bar institution switcher, mobile drawer, user session controls, and navigation.
* **Navigation Items**:
  - Overview (`/dashboard`): Contains metadata summary, but metrics cards currently display empty placeholders (`—`).
  - People (`/people`): Fully operational directory, role modification, status lifecycle, search/filter, and anti-lockout protection.
  - Libraries (`/libraries`): Fully operational catalog, creation wizard, visibility toggles, and metadata editor.
  - Resources (`/resources`): Fully operational document repository, drag-and-drop file uploader (PDF/DOCX/TXT), pipeline inspector stepper, error display, and streaming binary download.
  - Access (`/access`): Fully operational per-library RBAC matrix with member role grants and revocations.
  - Settings (`/settings`): Basic institution name update and archive danger zone.
* **Missing in Console**:
  - AI Usage / Token telemetry workspace.
  - Administrative Audit Activity log workspace.
  - Knowledge Connectors workspace.
  - Geographic Focus Regions configuration in Settings.
  - Live aggregated intelligence on the Overview dashboard.

---

## 4. Phase 4 Capability Matrix

| Capability Area | Backend Status | Backend Endpoint | Backend Model | Frontend Status | Phase 4 Action |
|---|---|---|---|---|---|
| **Institutional Overview** | PARTIAL | Missing aggregate endpoint | Queries existing models | Empty cards (`—`) | **ADD** API endpoint & **REUSE** in Dashboard |
| **Token Accounting** | EXISTS | Missing aggregate endpoint | `AgentRunRecord` | None | **ADD** usage endpoint & **ADD** `/usage` UI |
| **AI User Analytics** | EXISTS | Missing aggregate endpoint | `AgentRunRecord.user` | None | **ADD** in `/usage` endpoint & UI |
| **Audit Ledger** | MISSING | Missing | None | None | **ADD** model, service & **ADD** `/activity` UI |
| **Connector Catalog** | EXISTS | `GET /connectors/` | `Connector` | None | **REUSE** API in `/connectors` |
| **Connection CRUD** | EXISTS | `GET/POST /libraries/{id}/connections/` | `Connection` | None | **REUSE** API & **ADD** institution list |
| **Connection Sync** | EXISTS | `POST .../sync/` | `ConnectionSyncJob` | None | **REUSE** API in `/connectors` |
| **Remote File Browsing** | EXISTS | `GET .../browse/` | `RemoteBrowserView` | None | **REUSE** API in `/connectors` |
| **Operational Health** | PARTIAL | Split across models | `ProcessingRun`, `Connection` | None | **ADD** in Overview & **REUSE** in UI |
| **Context Regions** | EXISTS | `GET/POST .../context-regions/` | `InstitutionContextRegion` | None | **REUSE** API in `/settings` |
| **Billing / Subscriptions** | MISSING | None | None | None | **DEFER** to Phase 5 |
| **Custom Roles** | MISSING | None | None | None | **DEFER** (fixed enum sufficient) |

---

## 5. AI Usage & Token Telemetry Analysis

### A. Data Availability in `AgentRunRecord`
`AgentRunRecord` stores comprehensive telemetry per execution:
* `prompt_tokens`: Exact integer count of input tokens.
* `completion_tokens`: Exact integer count of output tokens generated by the LLM.
* `total_tokens`: Sum of prompt and completion tokens.
* `step_count`: Number of reasoning steps taken by the agent runtime.
* `status`: Terminal state (`completed`, `failed`, `cancelled`, `timed_out`).
* `started_at` & `finished_at`: Execution timing enabling duration calculation.
* `user`: Link to the initiating user.
* `session__institution`: Link to the tenant institution.

### B. What Can Be Accurately Computed
With database-level aggregation on `AgentRunRecord`, the backend can deterministically provide:
1. **Aggregated Token Totals**: `Sum('prompt_tokens')`, `Sum('completion_tokens')`, `Sum('total_tokens')`.
2. **Run Volumes**: Total executions, completed runs, failed runs, and failure rate.
3. **Active AI User Count**: `Count('user', distinct=True)`.
4. **Usage Timeline**: Daily token and run consumption grouped by `TruncDate('created_at')`.
5. **Top Consumer Breakdown**: Top users by token volume within the institution (`values('user__email').annotate(tokens=Sum('total_tokens'))`).
6. **Average Latency**: Average run duration (`Avg(finished_at - started_at)`).

### C. What is NOT Available (and Must NOT Be Fabricated)
* **Model Breakdown**: `AgentRunRecord` does not have a `model` column. The runtime delegates model selection to provider-neutral routing. Model names must not be hardcoded or fabricated in the UI.
* **Dollar Costing**: There is no billing ledger or price-per-token table. Phase 4 surfaces raw operational tokens, not speculative currency values.

### D. Recommended Endpoint
```http
GET /api/v1/institutions/{institution_id}/usage/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```
* **Authorization**: Active `ADMINISTRATOR` of `institution_id`.
* **Default Window**: Past 30 days.
* **Response Payload**:
```json
{
  "institution_id": "uuid",
  "start_date": "2026-08-04",
  "end_date": "2026-09-03",
  "summary": {
    "total_tokens": 1450200,
    "prompt_tokens": 1120000,
    "completion_tokens": 330200,
    "total_runs": 842,
    "completed_runs": 819,
    "failed_runs": 23,
    "active_users": 18,
    "average_latency_seconds": 3.4
  },
  "timeline": [
    { "date": "2026-09-01", "tokens": 48200, "runs": 31 },
    { "date": "2026-09-02", "tokens": 52100, "runs": 35 }
  ],
  "top_users": [
    { "user_id": "uuid", "email": "teacher.grace@mwalimu.test", "total_tokens": 340000, "runs": 180 }
  ]
}
```

---

## 6. Institutional Overview Aggregation Analysis

### A. Current Problem
The `/dashboard` overview screen currently displays `—` for active members, libraries, resources, and usage. If the frontend attempted to populate these via individual requests, it would require:
1. `GET /api/v1/memberships/?institution_id={id}` (to count members)
2. `GET /api/v1/libraries/?institution_id={id}` (to count libraries)
3. For each library, `GET /api/v1/libraries/{lib_id}/resources/` ($N$ requests)
4. Separate connector and context queries

This represents an $N+1$ client-side fanout that scales poorly and risks exposing partial state.

### B. Recommended Single Aggregation Endpoint
Add a dedicated overview action to `InstitutionViewSet`:
```http
GET /api/v1/institutions/{institution_id}/overview/
```
* **Authorization**: Active `ADMINISTRATOR` or member of `institution_id`.
* **Execution**: Single consolidated SQL query leveraging Django's database aggregation.
* **Response Payload**:
```json
{
  "institution_id": "uuid",
  "name": "St. Jude High School",
  "slug": "st-jude-high",
  "institution_type": "school",
  "status": "active",
  "members": {
    "total_active": 45,
    "pending": 2,
    "by_role": {
      "administrator": 2,
      "teacher": 8,
      "librarian": 1,
      "student": 34
    }
  },
  "knowledge": {
    "total_libraries": 6,
    "discoverable_libraries": 4,
    "restricted_libraries": 2,
    "total_resources": 28,
    "resources_by_status": {
      "ready": 26,
      "processing": 1,
      "failed": 1
    }
  },
  "integrations": {
    "total_connections": 2,
    "active_connections": 2,
    "error_connections": 0
  },
  "ai_telemetry_30d": {
    "total_tokens": 1450200,
    "total_runs": 842,
    "active_users": 18
  },
  "health": {
    "status": "healthy",
    "stuck_processing_count": 0,
    "failed_ingestion_count": 1,
    "failed_sync_count": 0
  }
}
```

---

## 7. Audit Governance Analysis

### A. Necessity of an Institutional Audit Ledger
In multi-tenant institutional environments (schools, universities, training centers), accountability is a core compliance and governance requirement. Administrators must know:
- Who elevated a student or teacher to an administrator.
- Who removed a member from the institution.
- Who created or deleted a knowledge library.
- Who granted or revoked access to restricted curricular resources.
- When an external data connector was modified or synchronized.

### B. Proposed Data Model: `InstitutionalAuditEvent`
Located in `platform_api/src/platform_api/apps/institutions/models.py`:
```python
class AuditAction(models.TextChoices):
    # Memberships
    MEMBER_ROLE_CHANGED = "member.role_changed", "Member Role Changed"
    MEMBER_STATUS_CHANGED = "member.status_changed", "Member Status Changed"
    MEMBER_REMOVED = "member.removed", "Member Removed"
    
    # Libraries
    LIBRARY_CREATED = "library.created", "Library Created"
    LIBRARY_UPDATED = "library.updated", "Library Updated"
    LIBRARY_DELETED = "library.deleted", "Library Deleted"
    
    # Access Policies
    ACCESS_GRANTED = "access.granted", "Access Policy Granted"
    ACCESS_UPDATED = "access.updated", "Access Policy Updated"
    ACCESS_REVOKED = "access.revoked", "Access Policy Revoked"
    
    # Resources
    RESOURCE_UPLOADED = "resource.uploaded", "Resource Uploaded"
    RESOURCE_DELETED = "resource.deleted", "Resource Deleted"
    RESOURCE_REINDEXED = "resource.reindexed", "Resource Reindexed"
    
    # Connections
    CONNECTION_CREATED = "connection.created", "Connection Created"
    CONNECTION_UPDATED = "connection.updated", "Connection Updated"
    CONNECTION_DELETED = "connection.deleted", "Connection Deleted"
    CONNECTION_SYNC_TRIGGERED = "connection.sync_triggered", "Sync Triggered"
    
    # Institution
    INSTITUTION_UPDATED = "institution.updated", "Institution Settings Updated"


class InstitutionalAuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="audit_events",
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_actions",
    )
    action = models.CharField(max_length=50, choices=AuditAction.choices, db_index=True)
    target_type = models.CharField(max_length=50, db_index=True)
    target_id = models.CharField(max_length=255, blank=True, default="")
    target_repr = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        db_table = "institutions_audit_event"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["institution", "-created_at"]),
            models.Index(fields=["institution", "action"]),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Audit events are strictly immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events cannot be deleted.")
```

### C. Immutability & Safety Guarantees
1. **Append-Only**: `.save()` rejects updates if the record already exists in the database.
2. **Undeletable**: `.delete()` raises a hard validation error.
3. **No Secret Leakage**: Metadata is sanitised at the service level to prevent writing credentials, passwords, or tokens.
4. **Read-Only API**:
   ```http
   GET /api/v1/institutions/{institution_id}/audit-logs/?action=&target_type=&search=&page=
   ```
   Exposes only `GET`. No `POST`, `PUT`, `PATCH`, or `DELETE` endpoints will exist for audit records.

---

## 8. External Knowledge Connectors Analysis

### A. Current Backend State
The `connectors` app is already implemented with adapters for:
1. `Google Drive`: Authenticates via OAuth2 / Service Account, browses folders, downloads files.
2. `Notion`: Authenticates via Internal Integration Token, queries database pages.
3. `Amazon S3`: Authenticates via AWS Access Key / Secret, lists prefix keys, downloads objects.
4. `Web Crawler`: Authenticates via API Key / none, crawls domains to configured depth.

### B. Missing Institution-Level Listing
Connections currently belong to a `Library` (`Connection.library_id`). In the console, administrators need to see all active connections across their institution.
* **Proposed Enhancement**:
  Update `LibraryConnectionListCreateView` or add `InstitutionConnectionListView`:
  ```http
  GET /api/v1/institutions/{institution_id}/connections/
  ```
  Returns all connections across all libraries belonging to `institution_id`.

### C. Security Validation
* The serializer `ConnectionDetailSerializer` strictly excludes `encrypted_credentials`.
* When updating a connection, credentials are `write_only`.
* The browser never receives decrypted keys or OAuth secrets.

---

## 9. Operational Health Analysis

Rather than creating a bloated DevOps monitoring dashboard, institutional health focuses on **educational content readiness and service availability**:
1. **Ingestion Failures**: Count and list of resources whose `ProcessingRun.status == 'failed'`. Allows one-click re-indexing.
2. **Stuck Ingestions**: Resources with `status == 'processing'` whose `created_at` exceeds 2 hours.
3. **Sync Health**: Connections whose `last_sync_status == 'failed'`.
4. **AI Error Rate**: Percentage of `AgentRunRecord` failures in the past 7 days.

This is exposed directly in the `overview` payload and surfaced with clear status badges on the `/dashboard` screen.

---

## 10. Institution Settings & Context Regions Review

### A. Existing Settings Screen
Currently in `mwalimu-console/src/app/(console)/settings/page.tsx`:
- Institution Name update.
- Slug display.
- Institution Type display.
- Archive danger zone.

### B. Proposed Enhancement: Focus Context Regions
The backend already supports `InstitutionContextRegion` via:
- `GET /api/v1/institutions/{id}/context-regions/`
- `POST /api/v1/institutions/{id}/context-regions/`
- `DELETE /api/v1/institutions/{id}/context-regions/{pk}/`
- `PUT /api/v1/institutions/{id}/context-regions/reorder/`

In Phase 4, the Settings workspace will be extended with an **Institutional Focus Regions** panel, allowing administrators to configure regional catchment areas (e.g. Uganda $\rightarrow$ Central $\rightarrow$ Wakiso District) with priority ranks. This directly powers the pedagogical localization of AI explanations.

---

## 11. Security & Tenant Isolation Analysis

Every Phase 4 endpoint must satisfy these strict security criteria:

1. **Authentication & Authorization**:
   - All endpoints require `IsAuthenticated`.
   - All institutional management and intelligence endpoints require `is_institution_admin(request.user, institution)`.
2. **Strict Server-Side Institution Resolution**:
   - The institution UUID in `/institutions/{id}/...` is verified against the caller's active memberships.
   - Supplying an arbitrary UUID in `X-Institution-Id` or URL path immediately yields `403 Forbidden` if the caller lacks active admin status.
3. **Cross-Tenant Aggregation Isolation**:
   - SQL queries must explicitly filter `institution_id=target_id` or `session__institution_id=target_id`.
   - Aggregations must never run against global querysets.
4. **Secret Protection**:
   - Zero decrypted credentials returned in connection APIs.
   - Audit event metadata sanitized against credentials and tokens.
5. **Immutability of Audit Records**:
   - Database and model-level constraints prevent modification or erasure of audit logs.

---

## 12. Performance & Query Analysis

### A. Aggregation Strategy: Database vs. Python
* **Rule**: Aggregations for Overview and AI Usage **must be executed in PostgreSQL**, never by loading thousands of rows into Python memory.
* **Implementation**:
  ```python
  # Efficient single-query execution
  stats = AgentRunRecord.objects.filter(
      session__institution_id=institution_id,
      created_at__gte=start_date,
  ).aggregate(
      total_tokens=Coalesce(Sum("total_tokens"), 0),
      prompt_tokens=Coalesce(Sum("prompt_tokens"), 0),
      completion_tokens=Coalesce(Sum("completion_tokens"), 0),
      total_runs=Count("id"),
      active_users=Count("user", distinct=True),
  )
  ```

### B. Indexing Requirements
* An index already exists on `AgentSession(institution, -updated_at)`.
* For `AgentRunRecord`, we should ensure efficient query execution when filtering by `session__institution` and `created_at`.
* For `InstitutionalAuditEvent`, composite indexes on `(institution, -created_at)` and `(institution, action)` are required.

### C. Caching Strategy
* Under **YAGNI**, caching should **not** be introduced prematurely. PostgreSQL can easily aggregate thousands of rows in < 15ms.
* If scale demands it in later phases, 60-second Redis caching can be layered additively.

---

## 13. Recommended Phase 4 Architecture

```text
mwalimu-console (console.ai-mwalimu.com)
│
├── INTELLIGENCE
│   ├── Overview (/dashboard)        ◄── GET /api/v1/institutions/{id}/overview/
│   ├── AI Usage (/usage)            ◄── GET /api/v1/institutions/{id}/usage/
│   └── Audit Activity (/activity)   ◄── GET /api/v1/institutions/{id}/audit-logs/
│
├── MANAGEMENT
│   ├── People (/people)             ◄── Existing Phase 3 API
│   ├── Libraries (/libraries)       ◄── Existing Phase 3 API
│   ├── Resources (/resources)       ◄── Existing Phase 3 API
│   └── Access (/access)             ◄── Existing Phase 3 API
│
├── INTEGRATIONS
│   └── Connectors (/connectors)     ◄── GET /api/v1/institutions/{id}/connections/
│                                    ◄── POST /api/v1/libraries/{id}/connections/
│                                    ◄── POST .../sync/ & GET .../sync-jobs/
│
└── CONFIGURATION
    └── Settings (/settings)         ◄── PATCH /api/v1/institutions/{id}/
                                     ◄── GET/POST /api/v1/institutions/{id}/context-regions/
```

---

## 14. Recommended API Additions

### Additive Platform API Endpoints
1. `GET /api/v1/institutions/{id}/overview/`: Consolidated institutional intelligence.
2. `GET /api/v1/institutions/{id}/usage/`: AI token accounting, run volumes, timeline, and top users.
3. `GET /api/v1/institutions/{id}/audit-logs/`: Read-only, paginated administrative audit ledger.
4. `GET /api/v1/institutions/{id}/connections/`: Cross-library connector listing for the institution.

---

## 15. Recommended Data Model Additions

### Additive Models
1. `InstitutionalAuditEvent`: Append-only, undeletable audit ledger in `platform_api/src/platform_api/apps/institutions/models.py`.
2. Migration: `0003_institution_audit_event.py`.

---

## 16. Recommended Console Navigation

```typescript
const NAV_GROUPS = [
  {
    title: "Intelligence",
    items: [
      { id: "overview", label: "Overview", href: "/dashboard", icon: Grid02Icon },
      { id: "usage", label: "AI Usage", href: "/usage", icon: CpuIcon },
      { id: "activity", label: "Audit Activity", href: "/activity", icon: SecurityCheckIcon },
    ],
  },
  {
    title: "Management",
    items: [
      { id: "people", label: "People & Members", href: "/people", icon: UserGroupIcon },
      { id: "libraries", label: "Knowledge Libraries", href: "/libraries", icon: Book02Icon },
      { id: "resources", label: "Documents & Files", href: "/resources", icon: File01Icon },
      { id: "access", label: "Access Policies", href: "/access", icon: LockKeyIcon },
    ],
  },
  {
    title: "Integrations",
    items: [
      { id: "connectors", label: "Knowledge Connectors", href: "/connectors", icon: LinkSquare01Icon },
    ],
  },
  {
    title: "Configuration",
    items: [
      { id: "settings", label: "Organization Settings", href: "/settings", icon: Settings01Icon },
    ],
  },
];
```

---

## 17. Explicitly Reused Components
* `platform_api.apps.agents.models.AgentRunRecord`: Telemetry source.
* `platform_api.apps.connectors`: Complete connector adapters, encryption, and sync engines.
* `platform_api.apps.context.models.InstitutionContextRegion`: Catchment region storage.
* `mwalimu-console/src/lib/api/client.ts`: Centralized fetch client.
* `mwalimu-console/src/lib/institution/institution-context.tsx`: Active institution switcher.

---

## 18. Explicitly Deferred Components
* **Billing, Plans, Subscriptions, Invoices**: Deferred to Phase 5.
* **Dynamic Custom Roles**: Deferred (fixed 4-role hierarchy is complete and stable).
* **Direct S3 / Vector Database Client Access**: Strict architectural invariant; permanently denied.
* **Academic Timetables / Gradebooks / Classrooms**: Belongs to LMS / SIS integration layer.

---

## 19. Migration Requirements
* One single additive migration in `platform_api`:
  `platform_api/src/platform_api/apps/institutions/migrations/0003_institutional_audit_event.py`
* Zero destructive changes to existing tables or columns.

---

## 20. Test Requirements
1. **Backend Tests** (`platform_api/tests/test_institutions_phase4.py`):
   - Overview aggregation accuracy across members, libraries, and resources.
   - Usage aggregation accuracy for prompt, completion, and total tokens.
   - Tenant isolation: verifying that Institution B cannot access Institution A's usage or overview.
   - Immutability of `InstitutionalAuditEvent` (blocking updates and deletes).
   - Credential masking: verifying that `GET /institutions/{id}/connections/` never leaks credentials.
   - Context region CRUD and ordering.
2. **Frontend Verification**:
   - `pnpm typecheck` (strict TypeScript validation).
   - `pnpm build` (production Next.js compilation across all routes).

---

## 21. Implementation Sequence

When authorized, Phase 4 will be implemented in the following sequence:

1. **Step 1: Backend Audit Model & Migration**: Create `InstitutionalAuditEvent` and audit service helper.
2. **Step 2: Backend Aggregation Endpoints**: Implement `overview`, `usage`, `audit-logs`, and `connections` endpoints with admin authorization.
3. **Step 3: Backend Verification**: Run pytest suite to ensure 100% green tests.
4. **Step 4: Frontend Client & Types**: Extend `client.ts` and `types/index.ts`.
5. **Step 5: Frontend Intelligence Workspaces**:
   - Wire live aggregated metrics into `/dashboard`.
   - Build `/usage` workspace (token counters, trend cards, top users).
   - Build `/activity` workspace (audit event stream with filters).
6. **Step 6: Frontend Connectors Workspace**: Build `/connectors` (catalog, connections table, sync triggers, sync history).
7. **Step 7: Frontend Settings Extension**: Add Focus Context Regions panel to `/settings`.
8. **Step 8: Full Verification & Build**: `pnpm typecheck` and `pnpm build`.

---

## 22. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Aggregation over-fetching on large institutions | Slow API responses | Use database-level `aggregate()` and `TruncDate()` with indexes; enforce 30-day default window. |
| Connector credential leakage | Critical security compromise | Serializers strictly omit encrypted credentials; tested with explicit test assertions. |
| Audit log tampering | Compliance violation | Model enforces append-only `.save()` and raises `ValidationError` on `.delete()`. |
| Cross-tenant data leakage | Privacy violation | All aggregations explicitly join on `institution_id` and check admin membership. |

---

## 23. Acceptance Criteria

Phase 4 will be accepted only when:
* Overview dashboard displays real, live aggregated institutional statistics.
* AI Usage displays accurate token volumes, run metrics, and user breakdowns without fabricated numbers.
* Audit ledger records and displays immutable administrative events.
* Connectors workspace lists connected sources, enables triggering synchronization, and inspects sync runs without exposing secrets.
* Focus Context Regions can be configured and prioritized in Settings.
* All backend tests pass with 0 failures.
* Next.js production build and TypeScript check pass cleanly.
