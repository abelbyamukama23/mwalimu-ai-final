# Platform Communication Architecture, Institutional Branding & Library Invitations

This document specifies the architectural model for Phase 3: the platform-wide communication layer, institutional branding, and secure library invitations across `platform_api` and `mwalimu-console`.

---

## 1. Architectural Principles & Service Separation

Prior to Phase 3, emails and notifications were scattered or tightly coupled to individual auth/user views. Phase 3 establishes a clean, decoupled communication architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                    Domain Applications                      │
│   (institutions, libraries, resources, memberships, auth)   │
└──────────────────────────────┬──────────────────────────────┘
                               │ dispatch_intent(intent, context, ...)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     Communications App                      │
│                                                             │
│   Intent Registry: Category, Channel Routing, Templates     │
├──────────────────────────────┬──────────────────────────────┤
│ In-App Delivery              │ External Outbox              │
│ ┌────────────────────────┐   │ ┌──────────────────────────┐ │
│ │  Notification (Table)  │   │ │   OutboxMessage (Table)  │ │
│ │  - is_read, payload    │   │ │   - idempotency_key      │ │
│ │  - unread_count        │   │ │   - status, attempts     │ │
│ └───────────┬────────────┘   │ └────────────┬─────────────┘ │
└─────────────┼────────────────┴──────────────┼───────────────┘
              │                               │ transaction.on_commit
              │ HTTP GET/POST                 ▼
              ▼                       ┌───────────────────────┐
┌───────────────────────────┐         │     Celery Worker     │
│   Institutional Console   │         │ deliver_outbox_message│
│   - Notification Bell     │         └───────────┬───────────┘
│   - Today / Earlier Feed  │                     │ Resend / SMTP
│   - Inline Action Buttons │                     ▼
└───────────────────────────┘         ┌───────────────────────┐
                                      │   User Email Inbox    │
                                      └───────────────────────┘
```

### 1.1 Intent vs Channel Decoupling
Domain apps do not compose raw HTML or send emails directly. They declare **what happened** using `dispatch_intent(...)`:
- **Intents**: Canonical business occurrences (`account.otp_requested`, `library.invitation_existing_user`, `library.invitation_new_user`, `library.invitation_accepted`, `library.invitation_revoked`).
- **Categories**: Stable functional areas (`system`, `account_security`, `institution_membership`, `library_access`, `resource_processing`, `connector_sync`, `audit_alert`).
- **Channels**: `in_app`, `email`, `sms`, `webhook`.
- **Templates**: Centralized brand-consistent HTML and plaintext renderers.

### 1.2 Transactional Outbox Pattern
External communications (emails) are persisted inside the active database transaction into `OutboxMessage`. A Celery task (`deliver_outbox_message`) is enqueued only upon successful transaction commit (`transaction.on_commit`). If the database transaction rolls back, no email is sent. If external delivery fails (e.g. SMTP/Resend network failure), Celery retries with exponential backoff without losing domain state.

---

## 2. Institutional Branding Architecture

### 2.1 Storage & Data Model
- `Institution` fields:
  - `logo_object_key` (e.g., `institutions/<uuid>/branding/<uuid>.png`)
  - `logo_content_type` (e.g., `image/png`, `image/webp`, `image/svg+xml`)
  - `logo_updated_at` (timestamp)
- Images are stored via the platform's `ObjectStorage` abstraction (`S3ObjectStorage` / `FakeStorage`).
- Allowed MIME types: PNG, JPEG, WebP, SVG.
- Maximum size: 2MB.

### 2.2 Endpoints & Access Control
- `POST /api/v1/institutions/{id}/branding/`: Administrator-only upload/replacement.
- `DELETE /api/v1/institutions/{id}/branding/`: Administrator-only removal.
- `GET /api/v1/institutions/{id}/badge/`: Public streaming endpoint returning `FileResponse` with `Cache-Control: public, max-age=3600`.
- Audit logs: Emits `AuditAction.BRANDING_UPDATED` with metadata (`badge_uploaded`, `badge_removed`, file size, MIME type).

---

## 3. First-Class Library Invitations

### 3.1 Domain Model & Lifecycle
`LibraryInvitation` acts as an authoritative bridge between an email address and library access:
- **Fields**: `id`, `library`, `institution`, `inviter`, `recipient_email`, `recipient_user` (nullable), `intended_access` (`administrator` | `teacher` | `student`), `status`, `token`, `expires_at`, `accepted_at`, `declined_at`, `revoked_at`.
- **Statuses**: `PENDING -> ACCEPTED | DECLINED | EXPIRED | REVOKED`.
- **Token**: 32-byte URL-safe cryptographically secure token (`secrets.token_urlsafe(32)`).
- **Expiration**: 7-day standard TTL.
- **Uniqueness**: Constraint prevents multiple concurrent `PENDING` invitations to the same email address for the same library.

### 3.2 Four Key Architectural Invariants
1. **Audit Event Separation**:
   - `library.invitation_created` is emitted upon invitation issuance.
   - `library.invitation_accepted` and `access.granted` (`LibraryAccessPolicy`) are emitted **only upon explicit acceptance**.
2. **Strict Email Binding**:
   - Only the verified user whose email strictly matches `invitation.recipient_email` may accept the invitation (`verified_user.email == invitation.recipient_email`).
   - If an account with a different email is authenticated, the platform rejects acceptance with HTTP 403.
3. **Anti-Enumeration on Resolution**:
   - `GET /api/v1/invitations/{token}/` is public but returns masked email (`j***@school.edu`) and never reveals whether the recipient email already holds a registered account.
4. **Reusing the Existing Authorization Model**:
   - Acceptance transactionally creates or updates `LibraryAccessPolicy` and ensures an active institution `Membership`. No redundant access structures are created.

### 3.3 Unregistered User Continuation Flow
```
1. Librarian invites "teacher@external.org"
2. Platform dispatches LIBRARY_INVITATION_NEW_USER intent
3. User receives email with link: /invite/<token>
4. User visits /invite/<token> -> clicks "Create Account"
5. Registration preserves return target: /register?next=/invite/<token>
6. User registers and verifies OTP -> verification completes
7. Verification automatically redirects to: /invite/<token>
8. Authenticated user matches recipient email -> user clicks "Accept"
9. Platform transactionally creates LibraryAccessPolicy and Membership
10. User enters library workspace
```

---

## 4. Frontend Console Experience

1. **Sidebar & Top Header**:
   - Institution badge streams live from `/api/v1/institutions/{id}/badge/` (falls back to `Building2`).
   - Top Header bar contains the **Notification Center** bell trigger with real-time unread counter.
2. **Notification Center Popover**:
   - DeepSeek-inspired minimalist design with "Today" and "Earlier" grouping.
   - Inline interactive "Accept" and "Decline" action buttons for pending library invitations.
   - One-click "Mark all as read".
3. **Settings**:
   - "Institutional Branding" management card for uploading, previewing, replacing, and removing logos.
4. **People**:
   - "Invite Member" modal for issuing invitations to specific libraries.
   - "Pending Invitations" tab displaying recipient, library, intended role, expiration countdown, and "Revoke" action.
5. **Library Workspace**:
   - Level 1 tabs: "Knowledge Shelves" and "Members & Invitations".
   - Shows active member roster alongside pending library invitations with instant revocation.
6. **Invitation Landing Page (`/invite/[token]`)**:
   - Resolves secure tokens without leaking identity.
   - Handles unauthenticated, unverified, matched, and mismatched account states gracefully.
