# Mwalimu — Institutional Console: Phase 1 Specification
## Institution Model, Self-Service Onboarding & Application Boundary Architecture

---

## 1. Executive Summary

This architectural specification defines the foundation for the **Mwalimu Institutional Console** — a dedicated, web-based control plane for managing organizational learning workspaces.

### Core Architectural Conclusions:
1. **Separation of Concerns (Experience Plane vs. Control Plane)**:
   The Institutional Console (`console.ai-mwalimu.com`) must be a dedicated application boundary, completely separate from the learner/teacher chat experience (`app.ai-mwalimu.com`). The console governs members, libraries, documents, context, and integrations; the learner application consumes knowledge for pedagogical interactions. Both consume the **Platform API** (`backend.ai-mwalimu.com`) as the single system of record.
2. **Domain Decoupling: `Institution.type` vs. `Membership.role`**:
   An Institution is an **organizational learning workspace**, not strictly a traditional school. It represents entities ranging from a `FAMILY` (parents managing learning for children) to a `SCHOOL`, `COLLEGE`, `UNIVERSITY`, `TRAINING_CENTER`, or `EDUCATION_ORGANIZATION`.
   - **Institution Type** describes *what the organization is*.
   - **Membership Role** describes *what a person does within that organization* (`ADMINISTRATOR`, `TEACHER`, `STUDENT`, `LIBRARIAN`).
3. **Single Identity, Shared Token Session, Multi-Tenant Context**:
   Identity remains centralized in the Platform API (`users_user`). A user logs in once with their primary credentials. The Institutional Console operates under an explicit, server-verified active institution context (`institution_id`), switching between workspaces without duplicating identity tables.
4. **Immediate Reuse of Core Infrastructure**:
   The Platform API already provides ~70% of the backend domain models and endpoints (`institutions`, `memberships`, `libraries`, `resources`, `processing`, `connectors`, `context`, `agents`). 
5. **Phase 1 Backend Evolution**:
   To make self-service onboarding secure, robust, and type-aware:
   - Add `institution_type` (Django `TextChoices`) to `Institution` model via a safe, backward-compatible migration.
   - Introduce an atomic, transactional self-registration endpoint (`POST /api/v1/institutions/register/`) or evolve `InstitutionViewSet.perform_create` with type validation and explicit owner tracking.
   - Establish the dedicated Next.js application workspace for the Institutional Console.

---

## 2. Current Architecture Relevant to Institutions

Mwalimu’s system architecture is composed of distinct services with rigid boundaries:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             CLIENT SURFACES                                 │
│                                                                             │
│   Learner / Teacher App               Institutional Console                 │
│   (app.ai-mwalimu.com)                (console.ai-mwalimu.com)              │
│   • Chat & Reasoning Sessions         • People & Membership Directory       │
│   • Real-time Agent Streaming         • Knowledge Libraries & Documents     │
│   • Pedagogical Interaction           • Access Policies & RBAC Matrix       │
│                                       • Connectors & Context Catchment      │
└───────────────────────┬─────────────────────────────┬───────────────────────┘
                        │                             │
                        │ JSON / HTTPS                │ JSON / HTTPS
                        │ Bearer JWT + CSRF           │ Bearer JWT + CSRF
                        ▼                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CONTROL PLANE / SYSTEM OF RECORD                      │
│                    Platform API (Django REST Framework)                     │
│                                                                             │
│   • Identity & Auth (`users`)          • Knowledge Boundary (`libraries`)   │
│   • Institutional Tenancy (`inst`)     • Resource Management (`resources`)  │
│   • Memberships & Roles (`members`)    • External Connectors (`connectors`) │
│   • Pedagogical Context (`context`)    • Document Pipeline (`processing`)   │
│   • Durable Audit Logs (`agents.run`)  • Retrieval Engine (`knowledge`)     │
└───────────────────────┬─────────────────────────────┬───────────────────────┘
                        │                             │
        Dispatches Run  │                             │ Asynchronous Celery Tasks
        Requests (HTTP) │                             ▼
                        │                   ┌───────────────────┐
                        ▼                   │   Celery Workers  │
┌───────────────────────────────┐           │   + Redis Broker  │
│     Agent Service (FastAPI)   │           │   (Ingestion &    │
│  Stateless runtime & OpenAI   │           │    Embeddings)    │
│  Agents SDK loop              │           └───────────────────┘
└───────────────────────────────┘
```

---

## 3. Existing Institution Domain

### Model: `platform_api.apps.institutions.models.Institution`
- **Table**: `institutions_institution`
- **Fields**:
  - `id`: `UUIDField(primary_key=True, default=uuid.uuid4)`
  - `name`: `CharField(max_length=255)`
  - `slug`: `SlugField(max_length=255, unique=True, db_index=True)`
  - `status`: `CharField(max_length=20, choices=InstitutionStatus.choices, default=ACTIVE)`
    - Statuses: `active`, `suspended`, `archived`
  - `created_at`: `DateTimeField(default=timezone.now)`
  - `updated_at`: `DateTimeField(auto_now=True)`
- **Key Missing Field**: **`institution_type` is completely absent.** The current model has no field to distinguish whether an institution is a university, primary school, family, or corporate training facility.

### API: `platform_api.apps.institutions.views.InstitutionViewSet`
- **Endpoints**:
  - `GET /api/v1/institutions/`: Lists all institutions (discoverable by any authenticated user).
  - `POST /api/v1/institutions/`: Creates a new institution.
  - `GET /api/v1/institutions/{id}/`: Retrieves details for an institution.
  - `PATCH /api/v1/institutions/{id}/`: Updates an institution (restricted to active `ADMINISTRATOR`s).
  - `DELETE /api/v1/institutions/{id}/`: Deletes an institution (restricted to active `ADMINISTRATOR`s).
- **Critical Existing Behavior**: In `perform_create`, the platform **already automatically assigns the creator as an active `ADMINISTRATOR`**:
  ```python
  def perform_create(self, serializer):
      institution = serializer.save()
      user = self.request.user
      if isinstance(user, User):
          Membership.objects.create(
              user=user,
              institution=institution,
              role=MembershipRole.ADMINISTRATOR,
              status=MembershipStatus.ACTIVE,
          )
  ```

---

## 4. Existing Authentication Architecture

Authentication is owned authoritatively by the **Platform API** using `rest_framework_simplejwt` and custom cryptographic OTP verification:

1. **User Identity (`users_user`)**:
   - Primary key: `UUIDField`
   - Identifier: `email` (case-insensitive normalized, unique)
   - Password: Argon2 / PBKDF2 hash
   - Status: `is_active` (boolean), `is_email_verified` (boolean), `email_verified_at` (datetime)
   - Social: `google_sub` (unique string for Google OAuth2 / OpenID Connect)
2. **Authentication Protocol**:
   - Access tokens: Short-lived HMAC-SHA256 JWTs passed in `Authorization: Bearer <token>` headers.
   - Refresh tokens: Long-lived JWTs stored in an `HttpOnly`, `SameSite=Lax` cookie (`mwalimu_refresh`), with double-submit CSRF protection (`csrftoken` header).
3. **Registration Flow**:
   - `POST /api/v1/auth/register/`: Takes `email`, `password`, `password_confirm`. Rejects duplicates, creates unverified user (`is_email_verified=False`), generates a cryptographically hashed 6-digit OTP (`EmailOTP`), and emails the code.
   - `POST /api/v1/auth/verify-email/`: Validates OTP within 15-minute expiration, marks `is_email_verified=True`, creates default `UserProfile`, returns access JWT, and sets refresh cookie.
   - `POST /api/v1/auth/login/`: Validates credentials, returns access JWT, sets refresh cookie.
   - `GET /api/v1/auth/me/`: Returns authenticated user profile and identity.

---

## 5. Existing Membership Architecture

### Model: `platform_api.apps.memberships.models.Membership`
- **Table**: `memberships_membership`
- **Fields**:
  - `id`: `UUIDField(primary_key=True)`
  - `user`: `ForeignKey(User, on_delete=CASCADE, related_name="memberships")`
  - `institution`: `ForeignKey(Institution, on_delete=CASCADE, related_name="memberships")`
  - `role`: `CharField(max_length=20, choices=MembershipRole.choices, default=STUDENT)`
    - Available Roles: `ADMINISTRATOR`, `TEACHER`, `STUDENT`, `LIBRARIAN`
  - `status`: `CharField(max_length=20, choices=MembershipStatus.choices, default=ACTIVE)`
    - Available Statuses: `PENDING`, `ACTIVE`, `INACTIVE`, `SUSPENDED`
- **Database Constraint**:
  ```python
  UniqueConstraint(
      fields=["user", "institution"],
      condition=Q(status="active"),
      name="memberships_membership_one_active_per_institution"
  )
  ```
  Guarantees that a user can hold at most **one active membership per institution**, while allowing historical inactive/suspended rows.

### Existing Membership API (`MembershipViewSet`):
- `GET /api/v1/memberships/`: Scoped dynamically. Regular users see only their own memberships. Institution administrators see all memberships across all institutions where they are active administrators.
- `POST /api/v1/memberships/`: Self-service join request. Enforces `role=STUDENT` and `status=PENDING`. Authenticated users cannot self-assign administrative roles.
- `PATCH /api/v1/memberships/{id}/`: Admin-only update. Allows an administrator to approve pending requests (`status="active"`), promote members (`role="teacher"`, `role="administrator"`), or suspend members (`status="suspended"`).
- `DELETE /api/v1/memberships/{id}/`: Admin-only removal of members.

---

## 6. Existing Authorization Architecture

Mwalimu’s authorization is strictly **server-authoritative** and rejects client-asserted permissions:

```text
Identity (`request.user`)
    │
    ▼
Institution Membership (`Membership.status == ACTIVE`)
    │
    ▼
Institution Role (`Membership.role == ADMINISTRATOR`) ──► Full Institutional Control
    │
    ▼
Library Visibility & Policy (`Library.scope_type`, `LibraryAccessPolicy`)
    ├── Personal: Owner only (`library.owner_id == user.id`)
    ├── Discoverable: Active member of institution can READ
    └── Restricted: User must hold explicit `LibraryAccessPolicy` row (Admin, Teacher, Student)
    │
    ▼
Effective Retrieval Scope (`frozenset(authorized_library_ids)`)
    │
    ▼
Query execution on Postgres / pgvector
```

---

## 7. Existing Institutional Capabilities

| Domain Area | Existing Model(s) | Existing Endpoints | Maturity |
|---|---|---|---|
| **Institution Tenant** | `Institution` | `GET/POST /api/v1/institutions/`<br>`GET/PATCH/DELETE /api/v1/institutions/{id}/` | **COMPLETE** |
| **People Management** | `Membership`, `User`, `UserProfile` | `GET/POST/PATCH/DELETE /api/v1/memberships/` | **COMPLETE** (UI missing) |
| **Institutional Libraries** | `Library` | `GET/POST/PATCH/DELETE /api/v1/libraries/` | **COMPLETE** (UI missing) |
| **Library RBAC Grants** | `LibraryAccessPolicy` | `GET/POST/PATCH/DELETE /api/v1/libraries/{id}/access-policies/` | **COMPLETE** (UI missing) |
| **Document Ingestion** | `Resource`, `ProcessingRun` | `GET/POST/DELETE /api/v1/libraries/{id}/resources/`<br>`GET/POST /.../processing-status/` | **COMPLETE** (UI missing) |
| **Knowledge Hierarchy** | `DocumentStructureNode`, `BookIndexEntry`, `DocumentPageMap` | Read via Knowledge Gateway & Processing Status | **COMPLETE** |
| **External Connectors** | `Connector`, `Connection`, `ConnectionSyncJob` | `/api/v1/connectors/`<br>`/api/v1/libraries/{id}/connections/`<br>`/.../browse/`, `.../sync/` | **COMPLETE** (UI missing) |
| **Geographic Context** | `InstitutionContextRegion`, `GeographicUnit` | `/api/v1/institutions/{id}/context-regions/`<br>`/.../reorder/` | **COMPLETE** (UI missing) |
| **AI Token Telemetry** | `AgentRunRecord` (tokens, steps, duration, institution) | Database persistence on every run | **PARTIAL** (API missing) |

---

## 8. Capability Gap Matrix

| Capability | Current State | Missing Element | Resolution in Phase 1 / 2 |
|---|---|---|---|
| **Institution Type** | Absent from `Institution` model | Model field, serializer support, filtering | Add `institution_type` enum field to `Institution` |
| **Self-Service Onboarding** | Requires existing verified user to call `POST /institutions/` | Unified registration wizard / composite endpoint | Provide unified self-service onboarding flow |
| **Creator / Owner Tracking** | First admin created via `perform_create`; no explicit owner field | Creator provenance field on `Institution` | Add `created_by` FK on `Institution` |
| **Direct Invitations** | Non-existent; users must self-request | Email invitation dispatch with pre-assigned role | Introduce `InstitutionInvitation` model (Phase 2) |
| **Console Dashboard Summary** | No single summary API | Aggregate stats endpoint for dashboard cards | Create `GET /api/v1/institutions/{id}/overview/` (Phase 2) |
| **Academic Hierarchy** | Flat roles; no classes/grades/subjects | Hierarchy models (Class, Subject, Stream) | Defer to Phase 4 (Academic Structure) |
| **Console Frontend Surface** | Stubbed shell at `frontend/src/app/(console)` | Dedicated Next.js application workspace | Create standalone console app |

---

## 9. Institution Type Model

### Architectural Axiom: Decouple Type from Role
An institution is a **workspace**, not a role. A `FAMILY` workspace has administrators (parents) and students (children). A `SCHOOL` workspace has administrators (headteachers/principals), teachers, librarians, and students. A `UNIVERSITY` has deans/admins, lecturers/professors, and scholars.

### Model Representation
Add `institution_type` directly to `platform_api.apps.institutions.models.Institution` as a standard Django `TextChoices` field:

```python
class InstitutionType(models.TextChoices):
    """Classification of organizational learning workspaces."""

    FAMILY = "family", "Family"
    SCHOOL = "school", "School (K-12)"
    COLLEGE = "college", "College / Vocational Institute"
    UNIVERSITY = "university", "University / Higher Education"
    TRAINING_CENTER = "training_center", "Training Center / Professional Academy"
    EDUCATION_ORGANIZATION = "education_organization", "Educational NGO / Foundation"
    OTHER = "other", "Other Organization"
```

```python
institution_type = models.CharField(
    max_length=30,
    choices=InstitutionType.choices,
    default=InstitutionType.SCHOOL,
    db_index=True,
    help_text="The organizational classification of this learning workspace.",
)
```

### Why a Single Table with Type Discriminator?
1. **YAGNI & KISS**: Avoid premature table inheritance (`FamilyInstitution`, `SchoolInstitution`). All workspaces share identical knowledge boundaries, resources, memberships, access policies, and connector requirements.
2. **Future Extensibility**: New workspace types can be introduced by appending to `InstitutionType` without structural database refactoring.
3. **Database Performance**: Indexed single-column discriminator enables fast filtering without table joins.

---

## 10. Self-Service Registration Model

### The Onboarding Journey
A new institutional creator (e.g., a parent, school principal, university administrator) must be able to establish an operational workspace in a predictable, secure flow:

```text
Step 1: Account Creation
Caller provides: email, password, display_name
     │
     ▼
Step 2: Email Identity Verification (OTP)
Platform dispatches 6-digit cryptographic code; caller verifies email
Caller obtains active JWT session (Identity established)
     │
     ▼
Step 3: Workspace Provisioning
Caller provides: institution_name, institution_type, slug
Server executes atomic transaction:
  1. Validates slug uniqueness & type choice
  2. Inserts Institution (name, slug, institution_type, created_by=caller)
  3. Inserts Membership (user=caller, institution=inst, role=ADMINISTRATOR, status=ACTIVE)
  4. Optionally seeds a default "General Library"
     │
     ▼
Step 4: Console Workspace Redirection
User enters console.ai-mwalimu.com as active Administrator
```

### Two-Step vs. Atomic Composite Registration
- **Option A (Two-Step, Recommended for Clean Identity Separation)**:
  1. User registers and verifies identity via existing `/api/v1/auth/register/` and `/api/v1/auth/verify-email/`.
  2. Authenticated user creates workspace via `POST /api/v1/institutions/` with `institution_type`.
  - *Advantages*: Zero duplicate user registration code; identity verification is guaranteed before workspace creation; adheres to existing SRP boundaries.
- **Option B (Composite Endpoint for Streamlined UI)**:
  `POST /api/v1/institutions/register/`: Takes `{ email, password, institution_name, institution_type }` in one payload, creates unverified user and pending institution, dispatches OTP. Upon verification, activates both.
  - *Trade-off*: More complex state machine and rollback requirements.

**Recommendation**: **Option A** for core architecture, backed by a polished multi-step onboarding wizard in the frontend console.

---

## 11. Institution Creator & Owner Model

### Governance Rules
1. **The Creator Is the First Administrator**:
   When an institution is created, the authenticated creator is immediately inserted as:
   `Membership(user=user, institution=institution, role=ADMINISTRATOR, status=ACTIVE)`.
2. **Explicit Creator Provenance**:
   Add `created_by` foreign key to `Institution`:
   ```python
   created_by = models.ForeignKey(
       settings.AUTH_USER_MODEL,
       on_delete=models.SET_NULL,
       null=True,
       blank=True,
       related_name="created_institutions",
   )
   ```
3. **Multiple Administrators**:
   An institution can have multiple active administrators. Any administrator can invite or promote other members to administrator.
4. **Guaranteed Administrator Invariant (Prevent Lockout)**:
   An administrator cannot delete or deactivate themselves if they are the **sole remaining active administrator** of the institution:
   ```python
   if membership.role == MembershipRole.ADMINISTRATOR:
       active_admins = Membership.objects.filter(
           institution=membership.institution,
           role=MembershipRole.ADMINISTRATOR,
           status=MembershipStatus.ACTIVE,
       ).exclude(pk=membership.pk).count()
       if active_admins == 0:
           raise ValidationError("An institution must have at least one active administrator.")
   ```
5. **No Separate "Owner" Model Needed**:
   Ownership is cleanly represented by `created_by` plus `MembershipRole.ADMINISTRATOR`. Introducing a separate `Owner` entity violates YAGNI without operational benefit.

---

## 12. Authentication & Session Architecture

### Single Authoritative Identity System
- There is **one user identity database** (`users_user`).
- A user authenticated on `app.ai-mwalimu.com` has the exact same identity on `console.ai-mwalimu.com`.
- **JWT Tokens**:
  - The JWT access token proves *who the user is* (`sub=user_id`).
  - The JWT does **not** bake in a static `role` claim, because a user can have different roles in different institutions (e.g. Teacher in School A, Parent in Family B).
- **Active Institution Context**:
  - The Institutional Console sets the active workspace context via the request header:
    `X-Institution-Id: <uuid>`
    or route parameter `/institutions/<uuid>/...`.
  - The Platform API evaluates permissions dynamically:
    ```python
    def has_permission(self, request, view):
        institution_id = request.headers.get("X-Institution-Id")
        return Membership.objects.filter(
            user=request.user,
            institution_id=institution_id,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        ).exists()
    ```
- **Learner Protection**:
  A regular student attempting to access the console with their credentials will authenticate successfully, but all control-plane requests will return `HTTP 403 Forbidden` because they have no active `ADMINISTRATOR` membership.

---

## 13. Institutional Console Application Boundary

### Why a Dedicated Application Boundary?

| Dimension | Learner/Teacher App (`app.ai-mwalimu.com`) | Institutional Console (`console.ai-mwalimu.com`) |
|---|---|---|
| **Primary Audience** | Students, Pupils, Children, Classroom Teachers | School Principals, Deans, IT Admins, Parents, Librarians |
| **Core Persona** | Learner / Inquirer | Operator / Governor |
| **Primary Workflows** | Multi-turn chat, problem-solving, math rendering, voice | User directory, access grants, document uploads, sync jobs |
| **Bundle & Dependencies** | KaTeX math, Markdown, Chat virtualizers, Streaming buffers | TanStack Table, charts, complex forms, CSV parsers, drag-and-drop |
| **Security Surface** | Ephemeral chat tokens, sandbox frames | Administrative credentials, tenant settings, connector secrets |
| **Failure Isolation** | A crash or heavy render in chat does not affect governance | Administrative operations do not degrade student latency |

---

## 14. Proposed Repository Structure

### Monorepo Analysis
The repository currently contains:
- `platform_api/` (Django + DRF backend)
- `agent_service/` (FastAPI agent runtime)
- `frontend/` (Next.js 16 learner app + stubbed `/console`)
- `docs/` (Architecture and documentation)

### Recommended Target Layout
Evolve the repository into a clean monorepo with explicit package directories:

```text
mwalimu_final/
├── platform_api/               # Django + DRF System of Record (Port 8000)
├── agent_service/              # FastAPI Agent Runtime (Port 8001)
├── apps/
│   ├── learner/                # Next.js Learner Experience (app.ai-mwalimu.com, Port 3000)
│   └── console/                # Next.js Institutional Console (console.ai-mwalimu.com, Port 3001)
├── packages/                   # (Optional Phase 2) Shared UI tokens / TypeScript types
├── docs/
│   └── architecture/
├── AGENTS.md
└── package.json (pnpm / npm root workspace)
```

*Note on Migration Path*: During Phase 1 specification, `frontend/` can continue serving the learner experience without disturbance. When console development commences, the dedicated console app is created in `apps/console/` (or `console/`).

---

## 15. Proposed API Boundary

### Schema & Endpoints for Institutional Control Plane

```text
/api/v1/
├── auth/
│   ├── register/                     (POST: create identity)
│   ├── verify-email/                 (POST: verify OTP & login)
│   ├── login/                        (POST: obtain JWT)
│   ├── refresh/                      (POST: rotate token)
│   └── me/                           (GET: caller profile)
│
├── institutions/
│   ├── register/                     (POST: atomic self-service workspace onboarding)
│   ├── {id}/                         (GET, PATCH, DELETE: institution profile & settings)
│   ├── {id}/overview/                (GET: dashboard summary aggregates)
│   ├── {id}/context-regions/         (GET, POST, DELETE, PUT/reorder: geographic catchment)
│   └── {id}/invitations/             (POST, GET: direct member invitations - Phase 2)
│
├── memberships/
│   ├──                               (GET: list members filtered by ?institution_id=)
│   └── {id}/                         (GET, PATCH: change role/status, DELETE: remove member)
│
└── libraries/
    ├──                               (GET: list institutional libraries, POST: create)
    └── {id}/
        ├──                           (GET, PATCH, DELETE: library metadata & visibility)
        ├── access-policies/          (GET, POST, PATCH, DELETE: per-library user RBAC)
        ├── resources/                (GET, POST: document upload, DELETE: resource deletion)
        │   └── {rid}/processing-status/ (GET: pipeline status, POST: re-indexing trigger)
        └── connections/              (GET, POST, DELETE: Google Drive, Notion, S3 connectors)
            ├── {cid}/browse/         (GET: remote folder hierarchy)
            ├── {cid}/sync/           (POST: manual sync trigger)
            └── {cid}/sync-jobs/      (GET: historical sync run logs)
```

---

## 16. Security Model

### Multi-Layered Enforcement Architecture
The client (browser) is **never** trusted to determine authorization.

```text
[Client Layer]
  • Renders UI based on user's active membership role
  • NEVER trusted for security decisions

[API Authentication Layer]
  • Validates JWT signature and expiration
  • Validates user account active status (`is_active=True`)

[Institution Permission Layer]
  • Validates caller holds an active Membership with role == ADMINISTRATOR
    for the specific target institution
  • Denies access with HTTP 403 / 404 if not authorized

[Service / Domain Layer]
  • Enforces business invariants:
    - At least one active administrator must remain
    - Unique constraints on slugs
    - Encrypted storage of connector credentials (Fernet / AES-256)

[Database Layer]
  • UniqueConstraint on (slug)
  • UniqueConstraint on (user, institution) where status == ACTIVE
  • Foreign key cascade rules protecting audit integrity
```

---

## 17. Tenant Isolation Model

### Invariant: Zero Cross-Tenant Leakage
1. **Scoped Querysets**:
   All database queries executed on behalf of an institution must be explicitly partitioned:
   ```python
   def get_queryset(self):
       institution_id = self.request.headers.get("X-Institution-Id")
       return Library.objects.filter(
           institution_id=institution_id,
           scope_type=LibraryScopeType.INSTITUTION
       )
   ```
2. **Fail Closed**:
   If an administrator of Institution A queries an object ID belonging to Institution B:
   - The API returns `HTTP 404 Not Found` (never revealing existence).
3. **Knowledge Retrieval Boundary**:
   The `EffectiveRetrievalScope` guarantees that vector similarity searches only compute dot products against `ChunkEmbedding` records linked to libraries authorized for that specific institution.

---

## 18. Initial Console Information Architecture

```text
Institutional Console (console.ai-mwalimu.com)
│
├── 1. Overview
│   ├── Quick Stats: Total Members, Libraries, Documents, Monthly Tokens
│   ├── Quick Actions: Add Document, Invite Member, Create Library
│   └── System Status: Pipeline health & connector sync states
│
├── 2. People
│   ├── Members Directory (Search, filter by Role & Status)
│   ├── Pending Join Requests (Review & Approve/Reject)
│   └── Role Assignment Modal (Admin, Teacher, Student, Librarian)
│
├── 3. Knowledge & Libraries
│   ├── Institutional Libraries Grid (Create, Edit Visibility)
│   └── Library Inspector:
│       ├── Document Repository (Upload, Inspect TOC / Index / Page Maps)
│       ├── Access Policies (Per-library user grants)
│       └── External Connections (Google Drive, Notion, S3 setup & sync)
│
├── 4. Context & Localization
│   └── Geographic Catchment Regions (Country, District, Priority Ranking)
│
├── 5. Usage & Analytics (Phase 3)
│   └── AI Token Consumption, Query Counts, Step Latencies
│
└── 6. Organization Settings
    ├── Institution Profile (Name, Slug, Type)
    ├── Administrator Management
    └── Danger Zone (Archive Workspace, Delete Institution)
```

---

## 19. Implementation Phases

* **Phase 1 (Current)**: Architecture, Reconnaissance, and Specification *(Complete)*.
* **Phase 2 (Backend Foundation)**:
  1. Add `institution_type` and `created_by` to `Institution` via migration.
  2. Implement `GET /api/v1/institutions/{id}/overview/` metric endpoint.
  3. Ensure `?institution_id=` filter on `/api/v1/memberships/`.
* **Phase 3 (Console Application Setup)**:
  1. Initialize dedicated Next.js application for Institutional Console.
  2. Implement Multi-Tenant Workspace Switcher & Session Provider.
  3. Build Overview, People, Libraries, and Resource Workspaces against existing Platform API.
* **Phase 4 (Onboarding & Invitations)**:
  1. Implement `InstitutionInvitation` model and email token dispatch.
  2. Self-service onboarding wizard for Family, School, University creators.
* **Phase 5 (Academic Structure & Analytics)**:
  1. Academic hierarchy (Classes, Courses, Teacher Assignments).
  2. Token analytics and institutional quota monitoring.

---

## 20. Deferred Capabilities (Explicit "DO NOT BUILD YET")

To preserve engineering focus and adhere to YAGNI:
- **Billing, Invoicing, and Payment Gateways**: Defer. Institutions operate under administrative pilot provisioning.
- **Developer API Key Management & Public Webhooks**: Defer to a future developer platform phase.
- **Custom Dynamic Role Builders**: Defer. The 4 static roles (`Administrator`, `Teacher`, `Student`, `Librarian`) fully satisfy institutional operational needs.
- **Complex Gradebooks & Academic Grading Modules**: Defer until core knowledge management is established.

---

## 21. Risks & Architectural Questions

1. **Risk: Slug Collisions During Self-Registration**:
   - *Mitigation*: The frontend onboarding form must implement real-time debounce checks against `/api/v1/institutions/?slug=...` and suggest numerical suffixes (`greenwood-academy-2`) if taken.
2. **Risk: Orphaned Institutions**:
   - *Mitigation*: Database-enforced validation preventing an administrator from removing themselves if they are the sole remaining active administrator.
3. **Risk: Cross-Tenant Request Header Tampering**:
   - *Mitigation*: The `X-Institution-Id` header must always be validated server-side against the caller’s active memberships before executing any queryset filter.

---

## 22. Final Recommendation & Direct Answers

### Direct Answers to Key Questions:

1. **"Can we create the Institutional Console as a new Next.js application without duplicating the existing Platform API?"**
   **YES.** The Institutional Console should be a thin, pure control-plane client that makes standard REST API calls to the authoritative Platform API. Zero business logic or database queries need to be duplicated.
2. **"Can a parent, school, university or other organization self-register as an institution?"**
   **YES.** The existing architecture already supports user creation and makes an institution creator an active administrator. Adding `institution_type` enables tailored onboarding for Families, Schools, and Universities.
3. **"What must change in the backend before that is safe?"**
   - Add `institution_type` and `created_by` fields to `Institution` with migration.
   - Enforce the "minimum one active administrator" invariant on membership deletion.
   - Add explicit `institution_id` query filtering on `/api/v1/memberships/`.
4. **"What can be reused immediately?"**
   - User authentication, JWT tokens, OTP verification.
   - `Institution` and `Membership` models and ViewSets.
   - `Library` and `LibraryAccessPolicy` authorization.
   - `Resource` upload, S3 storage, and Celery document processing pipeline.
   - `Connector` and `Connection` external sync engine.
   - `InstitutionContextRegion` geographic settings.
5. **"What should be implemented first after this audit?"**
   - **Step 1**: Backend migration to add `institution_type` and `created_by` to `Institution`.
   - **Step 2**: Backend `overview` summary endpoint.
   - **Step 3**: Scaffold the dedicated Next.js Institutional Console application.

---

*End of Phase 1 Architectural Specification.*
