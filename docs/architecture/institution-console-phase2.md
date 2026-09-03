# Mwalimu — Institutional Console: Phase 2 Architecture & Implementation
## Independent Application, Repository Foundation & Backend Verification

---

## 1. Executive Summary

In Phase 2, the **Institutional Console** was established as an independent application and Git repository located at `Desktop/mwalimu-console/`, completely decoupled from the main platform repository `Desktop/mwalimu_final/`.

The Platform API (`mwalimu_final/platform_api`) remains the single system of record and was extended with core institutional tenancy primitives:
1. **`InstitutionType` classification**: Single-table discriminator supporting `family`, `school`, `college`, `university`, `training_center`, `education_organization`, and `other`.
2. **`created_by` provenance**: Explicit foreign key to `User` tracking the original creator of an institution.
3. **Atomic Administrator Appointment**: Automatically creating an active `ADMINISTRATOR` membership for the creator upon institution creation within an atomic database transaction.
4. **Orphan Prevention Safeguard**: Enforcing at model, serializer, and view levels that the final active administrator of an institution cannot be deleted, demoted, deactivated, or suspended.
5. **Scoped Membership Retrieval**: Supporting explicit `?institution_id=<uuid>` query parameter and `X-Institution-Id` header to scope membership lists strictly to the target institution.

All 64 backend tests across `test_institutions_phase2.py`, `test_institutions.py`, `test_memberships.py`, `test_authorization.py`, `test_auth.py`, and `test_users.py` pass with 100% success. The frontend console builds cleanly with zero TypeScript errors.

---

## 2. Repository Boundaries & Architecture

```text
Desktop/
├── mwalimu_final/                          # Git Repository 1 (Platform Core)
│   ├── platform_api/                       # Django + DRF System of Record (Port 8000)
│   ├── agent_service/                      # FastAPI Agent Runtime (Port 8001)
│   ├── frontend/                           # Learner / Teacher App (app.ai-mwalimu.com)
│   └── docs/                               # System Architecture Specifications
│
└── mwalimu-console/                        # Git Repository 2 (Control Plane)
    ├── .git/                               # Independent version history
    ├── src/
    │   ├── app/                            # App Router routes (login, register, onboarding, dashboard)
    │   ├── components/layout/              # ConsoleShell, Navigation, Switcher
    │   ├── lib/api/                        # Centralized typed Platform API client
    │   ├── lib/auth/                       # SessionProvider & Token Store
    │   ├── lib/institution/                # InstitutionProvider & Switcher
    │   └── types/                          # Shared domain TypeScript types
    ├── package.json                        # mwalimu-console (Port 3001)
    ├── next.config.ts
    └── README.md
```

`git rev-parse --show-toplevel` returns:
* In `mwalimu-console`: `C:/Users/user/Desktop/mwalimu-console`
* In `mwalimu_final`: `C:/Users/user/Desktop/mwalimu_final`

The two applications maintain completely independent Git version histories and dependency graphs.

---

## 3. Backend Phase 2 Extensions

### Model: `Institution` (`institutions/models.py`)
```python
class InstitutionType(models.TextChoices):
    FAMILY = "family", "Family"
    SCHOOL = "school", "School (K-12)"
    COLLEGE = "college", "College / Vocational Institute"
    UNIVERSITY = "university", "University / Higher Education"
    TRAINING_CENTER = "training_center", "Training Center / Academy"
    EDUCATION_ORGANIZATION = "education_organization", "Educational Organization / NGO"
    OTHER = "other", "Other Organization"

class Institution(models.Model):
    ...
    institution_type = models.CharField(
        max_length=30,
        choices=InstitutionType.choices,
        default=InstitutionType.SCHOOL,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_institutions",
    )
```

### Serializer: `InstitutionSerializer` (`institutions/serializers.py`)
Exposes `institution_type` with choice validation, and `created_by_id` as read-only.

### Atomic Workspace Creation: `InstitutionViewSet` (`institutions/views.py`)
```python
@transaction.atomic
def perform_create(self, serializer):
    user = self.request.user
    created_by_user = user if isinstance(user, User) else None
    institution = serializer.save(created_by=created_by_user)
    if isinstance(user, User):
        Membership.objects.create(
            user=user,
            institution=institution,
            role=MembershipRole.ADMINISTRATOR,
            status=MembershipStatus.ACTIVE,
        )
```

### Orphan Protection Invariant (`memberships/`)
1. **`Membership.delete()`**:
   ```python
   if self.role == MembershipRole.ADMINISTRATOR and self.status == MembershipStatus.ACTIVE:
       active_admins = Membership.objects.filter(
           institution=self.institution,
           role=MembershipRole.ADMINISTRATOR,
           status=MembershipStatus.ACTIVE,
       ).exclude(pk=self.pk).count()
       if active_admins == 0:
           raise ValidationError("Cannot delete the final active administrator of an institution.")
   ```
2. **`MembershipSerializer.validate()`**:
   Blocks demoting or deactivating the final active administrator via API `PATCH` or `PUT`.
3. **`MembershipViewSet.destroy()`**:
   Blocks removing the final active administrator via API `DELETE`.

### Scoped Membership Retrieval (`MembershipViewSet.get_queryset`)
Supports `?institution_id=<uuid>` and `X-Institution-Id` header:
- If caller is an active administrator of that institution, returns all members of that institution.
- If caller is a member but not an admin, returns only the caller's membership.
- If caller is not a member, returns an empty queryset.
- If omitted, preserves default backward-compatible behavior.

---

## 4. Frontend Application Architecture

### Centralized Typed Platform API Client (`src/lib/api/client.ts`)
- Automatically applies `Authorization: Bearer <token>` from the local token store.
- Automatically applies `X-Institution-Id: <uuid>` from the active institution context.
- Handles HttpOnly cookie refresh token rotation on `401 Unauthorized`.
- Exposes typed methods for `auth`, `institutions`, and `memberships`.

### Onboarding Flow
1. **Registration** (`/register`): Creates user account with email and password.
2. **Verification** (`/verify-email`): Validates 6-digit cryptographic OTP, logs the user in, and receives JWT.
3. **Workspace Setup** (`/onboarding`): Prompts for organization name, slug, and classification type (`family`, `school`, `university`, etc.).
4. **Console Access** (`/dashboard`): Provisions workspace, selects active institution context, and renders the control plane shell.

### Console Shell & Navigation
- Deep slate administrative theme (`#0f172a`), distinct from the learner chat interface.
- Institution switcher dropdown supporting multi-institution users and seamless switching.
- Core navigation:
  - **Overview** (`/dashboard`): Workspace metadata, status badges, and management links.
  - **People** (`/people`): Phase 3 member directory placeholder.
  - **Libraries** (`/libraries`): Phase 3 knowledge libraries placeholder.
  - **Resources** (`/resources`): Phase 3 document repository placeholder.
  - **Access** (`/access`): Phase 3 access policies placeholder.
  - **Settings** (`/settings`): Workspace configuration, slug display, and danger zone.

---

## 5. Verification Results

### Backend Automated Test Suite
```text
tests/test_institutions_phase2.py .......... [10 passed]
tests/test_institutions.py ........          [8 passed]
tests/test_memberships.py ...............    [15 passed]
tests/test_authorization.py .......         [7 passed]
tests/test_auth.py ....................      [20 passed]
tests/test_users.py ....                     [4 passed]

Total: 64 passed, 0 failed in 110s
```

### Frontend TypeScript & Build Verification
```text
> mwalimu-console@0.1.0 build
▲ Next.js 16.3.2 (Turbopack)
✓ Compiled successfully in 8.9s
Finished TypeScript in 4.7s
Generating static pages (13/13) in 614ms
✓ 13/13 routes built successfully
```

---

## 6. Recommended Phase 3 Scope

With the independent application foundation, authentication, institution types, and context established, **Phase 3** should implement the core operational control-plane tables and actions:
1. **People & Members Directory Workspace**: Complete data table, role dropdown, active/suspended toggle, and member removal modal consuming `/api/v1/memberships/`.
2. **Institutional Libraries Catalog Workspace**: Creation wizard, visibility toggles (discoverable vs. restricted), and library configuration consuming `/api/v1/libraries/`.
3. **Resource Upload & Document Pipeline Workspace**: Drag-and-drop PDF/DOCX uploader, processing run status inspector (TOC, index terms, page maps), and re-indexing triggers consuming `/api/v1/libraries/{id}/resources/`.
4. **Access Policies (RBAC) Workspace**: Per-library member role assignment matrix consuming `/api/v1/libraries/{id}/access-policies/`.
