# Admin Approval Workflow and User Management — Spec v1

**Ticket:** #5 [task] Implement admin approval workflow and user management
**Depends on:** #4 [prototype] (validated — Docker + FastAPI + WebSocket works)
**Date:** 2026-07-27
**Author:** Hermes
**Status:** Initial spec — pending review

---

## Summary

Build the user-facing signup flow and admin-facing approval workflow for ABIS Academy. Every kid goes through a multi-stage onboarding: signup → profile completion → access restriction configuration → admin approval → container creation. The admin dashboard is the central hub for managing all users, approvals, and containers.

---

## Context

- Architecture: Docker containers per kid, FastAPI + WebSocket ATA agents
- Database: SQLite (orchestrator state on pi-agent)
- Auth: Email + password for POC (OAuth deferred to Phase 2)
- Models: Cloud models via Ollama (gemma4:31b-cloud)
- Max users: 8 concurrent on Pi 5
- Container lifecycle: orchestrator manages create/start/stop/pause/resume

---

## Requirements

### FR-1: User Signup Form
- **Description:** New user (kid or parent on behalf of kid) submits signup request
- **Fields:**
  - Email (required, unique, validated format)
  - Name (required, first + last)
  - Age (required, integer, 10-18)
  - Intended use case (optional, textarea)
  - Parent/guardian email (required for minors)
- **Validation:**
  - Email must not already exist in database
  - Age must be between 10 and 18
  - Parent email required if age < 18
- **Output:** User record created with status `PENDING_PROFILE`

### FR-2: Profile Completion (Kid-facing)
- **Description:** After signup, kid completes their profile before admin sees them
- **Fields:**
  - Preferred display name (required, max 30 chars)
  - Profile avatar (optional, upload or select from defaults)
  - Interest tags (optional, multi-select: coding, math, science, art, etc.)
  - Preferred language (default: English, options: English, Cantonese)
- **State transition:** `PENDING_PROFILE` → `PENDING_RESTRICTIONS`
- **Gate:** Profile must be complete before admin can see the approve button

### FR-3: Access Restriction Configuration (Admin-facing, pre-approval)
- **Description:** Admin configures what the kid can do BEFORE approving
- **Configuration:**
  - Age group: 10-12 (chat + files only) or 15+ (chat + files + terminal + code)
  - Model selection: default `gemma4:31b-cloud` or admin-selected alternative
  - Daily token quota: default 10,000 tokens
  - Time window: allowed chat hours (default: 08:00-20:00 HKT)
  - File size limit: max 5MB per file
  - Content filters: strict/moderate/relaxed (keyword list selection)
- **State transition:** `PENDING_RESTRICTIONS` → `PENDING_APPROVAL`
- **Gate:** Restrictions must be configured before approve button is visible

### FR-4: Admin Dashboard — Pending Approvals
- **Description:** Admin sees a list of users awaiting approval
- **Columns:**
  - Display name
  - Age
  - Signup date
  - Profile status (complete/incomplete)
  - Restrictions status (configured/pending)
  - Approve button (disabled until restrictions configured)
  - Reject button (always available)
- **Filters:** All pending, profile incomplete, restrictions pending, ready to approve
- **Sorting:** By signup date (oldest first)

### FR-5: Admin Approve Action
- **Description:** Admin clicks "Approve" on a fully configured user
- **Effects:**
  1. User status: `PENDING_APPROVAL` → `APPROVED`
  2. Write `/var/abis/permissions/<user_id>.json` (read-only bind mount config)
  3. Trigger orchestrator: create Docker container for user
  4. Assign host port (sequential: 7884, 7885, ...)
  5. Start container
  6. User status: `APPROVED` → `CONTAINER_READY`
  7. Send notification to user (in-app notification for now, email deferred)
- **Error handling:** If container creation fails, log error, notify admin, keep user in `APPROVED` state (don't lose the approval decision)

### FR-6: Admin Reject Action
- **Description:** Admin clicks "Reject" on any pending user
- **Fields:**
  - Rejection reason (required, dropdown: age inappropriate, capacity full, safety concern, other)
  - Custom note (optional, textarea)
- **Effects:**
  1. User status: any → `REJECTED`
  2. No container created
  3. Send notification to user with reason
  4. User data retained for 30 days then soft-deleted (GDPR/PDPO compliance)

### FR-7: Admin Dashboard — Active Users
- **Description:** Admin sees all approved and active users
- **Columns:**
  - Display name + avatar
  - Age group
  - Container status (running / paused / stopped / error)
  - Last active timestamp
  - Token usage (today / this week)
  - Alert count (flagged messages)
  - Actions: Pause, Resume, Terminate, View Details
- **Filters:** Active, paused, all
- **Sorting:** Last active (most recent first)

### FR-8: Admin Suspend Action
- **Description:** Admin pauses a user's container immediately
- **Effects:**
  1. Orchestrator: `docker stop` the container
  2. User status: `CONTAINER_READY` → `SUSPENDED`
  3. Kid sees: "Your agent is paused. Contact your admin for help."
  4. Data persists on bind mount

### FR-9: Admin Resume Action
- **Description:** Admin restarts a suspended user's container
- **Effects:**
  1. Orchestrator: `docker start` the container
  2. User status: `SUSPENDED` → `CONTAINER_READY`
  3. Kid can chat again

### FR-10: Admin Terminate Action
- **Description:** Admin permanently removes a user and destroys their container
- **Effects:**
  1. Orchestrator: `docker rm -f` the container
  2. User status: `CONTAINER_READY` → `TERMINATED`
  3. User data archived to `/var/abis/archives/<user_id>/` (retain 90 days)
  4. After 90 days: delete archived data (PDPO compliance)
- **Confirmation:** Required — "Are you sure? This will delete [Name]'s agent and data."

### FR-11: Auto-Pause After 7 Days Inactivity
- **Description:** Orchestrator automatically pauses containers where kid hasn't sent a chat message in 7 days
- **Trigger:** WebSocket `last_message_timestamp` older than 7 days
- **Effect:** Same as FR-8 (Suspend), but auto-initiated
- **Recovery:** Kid logs in → orchestrator auto-resumes → status back to `CONTAINER_READY`

---

## Non-Functional Requirements

### NFR-1: Performance
- Signup form submission: < 500ms response time
- Admin dashboard load: < 1 second for 8 users
- Approve/reject action: < 2 seconds (includes container creation)
- Suspend/resume: < 1 second

### NFR-2: Security
- Passwords hashed with bcrypt (if storing passwords for POC)
- Admin endpoints require admin role check
- No kid can access admin endpoints (403 Forbidden)
- Permission JSON files are read-only from container perspective

### NFR-3: Reliability
- SQLite WAL mode for concurrent reads
- Container creation failures logged but don't crash the orchestrator
- State transitions are atomic (use transactions)

### NFR-4: Compliance
- PDPO: Data retention schedules documented (30 days for rejected, 90 days for terminated)
- No raw conversation logs exposed in admin dashboard (only metadata: token count, alert count)
- Admin can view conversation context only for flagged messages

---

## Database Schema

```sql
-- Users table
CREATE TABLE users (
    id TEXT PRIMARY KEY,           -- "kid-001" format
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    parent_email TEXT,
    display_name TEXT,
    avatar TEXT,                    -- URL or default identifier
    interests TEXT,                 -- JSON array
    preferred_language TEXT DEFAULT 'en',
    status TEXT DEFAULT 'PENDING_PROFILE',  -- enum: PENDING_PROFILE, PENDING_RESTRICTIONS, PENDING_APPROVAL, APPROVED, CONTAINER_READY, SUSPENDED, REJECTED, TERMINATED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,
    rejected_at TIMESTAMP,
    rejection_reason TEXT,
    rejection_note TEXT
);

-- Admin actions audit log
CREATE TABLE admin_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,           -- APPROVE, REJECT, SUSPEND, RESUME, TERMINATE, CONFIGURE_RESTRICTIONS
    details TEXT,                   -- JSON blob
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User restrictions (permission config)
CREATE TABLE user_restrictions (
    user_id TEXT PRIMARY KEY,
    age_group TEXT NOT NULL,        -- "10-12" or "15+"
    model TEXT DEFAULT 'gemma4:31b-cloud',
    daily_token_quota INTEGER DEFAULT 10000,
    chat_start_time TEXT DEFAULT '08:00',
    chat_end_time TEXT DEFAULT '20:00',
    file_size_limit_mb INTEGER DEFAULT 5,
    content_filter_level TEXT DEFAULT 'strict',  -- strict, moderate, relaxed
    permissions_json TEXT,          -- JSON blob matching permissions.json format
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Container tracking
CREATE TABLE containers (
    user_id TEXT PRIMARY KEY,
    status TEXT DEFAULT 'none',     -- none, creating, running, paused, stopped, error
    docker_container_id TEXT,
    host_port INTEGER,
    pid INTEGER,
    memory_mb INTEGER,
    cpu_percent REAL,
    last_message_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Endpoints

### Public (No Auth Required)
```
POST /api/signup
  Body: {email, name, age, parent_email, intended_use}
  Response: {user_id, status: "PENDING_PROFILE", message: "Please complete your profile"}

POST /api/login
  Body: {email, password}
  Response: {token, user: {id, name, status, ...}}

GET /api/health
  Response: {status: "ok"}
```

### User-facing (JWT Required)
```
POST /api/profile/complete
  Headers: Authorization: Bearer <token>
  Body: {display_name, avatar, interests, preferred_language}
  Response: {status: "PENDING_RESTRICTIONS", message: "Waiting for admin configuration"}

GET /api/me
  Headers: Authorization: Bearer <token>
  Response: {id, name, status, display_name, ...}

GET /api/me/status
  Headers: Authorization: Bearer <token>
  Response: {status, message, next_step}
```

### Admin-facing (JWT + Admin Role Required)
```
GET /api/admin/pending
  Response: [{user_id, name, age, signup_date, profile_status, restrictions_status, can_approve}]

GET /api/admin/users
  Query: ?status=active|paused|all
  Response: [{user_id, name, age, container_status, last_active, token_usage, alert_count}]

POST /api/admin/users/:id/restrictions
  Body: {age_group, model, daily_token_quota, chat_start_time, chat_end_time, file_size_limit_mb, content_filter_level}
  Response: {status: "configured", next: "ready_for_approval"}

POST /api/admin/users/:id/approve
  Response: {status: "APPROVED", container_status: "creating"}

POST /api/admin/users/:id/reject
  Body: {reason, note}
  Response: {status: "REJECTED"}

POST /api/admin/users/:id/suspend
  Response: {status: "SUSPENDED"}

POST /api/admin/users/:id/resume
  Response: {status: "CONTAINER_READY"}

DELETE /api/admin/users/:id/terminate
  Response: {status: "TERMINATED", data_retention: "90 days"}

GET /api/admin/actions
  Query: ?user_id=&limit=50
  Response: [{admin_id, user_id, action, details, created_at}]
```

---

## State Machine

```
SIGNUP
  → PENDING_PROFILE (profile incomplete)
    → kid completes profile
      → PENDING_RESTRICTIONS (waiting for admin config)
        → admin configures restrictions
          → PENDING_APPROVAL (admin sees approve button)
            → admin approves
              → APPROVED (triggers container creation)
                → container starts successfully
                  → CONTAINER_READY (kid can chat)
                    → 7 days inactive → SUSPENDED (auto-pause)
                      → kid logs in → CONTAINER_READY (auto-resume)
                    → admin suspends → SUSPENDED
                      → admin resumes → CONTAINER_READY
                    → admin terminates → TERMINATED
            → admin rejects → REJECTED
```

---

## Files to Create / Modify

### New Files
- `src/api/routes/auth.py` — signup, login, JWT
- `src/api/routes/profile.py` — profile completion
- `src/api/routes/admin.py` — all admin endpoints
- `src/api/models/user.py` — User ORM model
- `src/api/models/restrictions.py` — UserRestrictions ORM model
- `src/api/models/container.py` — Container ORM model
- `src/api/models/audit.py` — AdminAction ORM model
- `src/api/services/orchestrator_client.py` — HTTP client to orchestrator (7883)
- `src/api/services/permissions_writer.py` — Write permissions.json to disk
- `src/api/middleware/auth.py` — JWT validation, admin role check
- `src/api/middleware/rate_limit.py` — Basic rate limiting
- `src/api/templates/signup.html` — Simple signup form (POC, no React)
- `src/api/templates/admin.html` — Simple admin dashboard (POC, no React)
- `src/api/static/css/admin.css` — Minimal admin styling
- `src/orchestrator/lifecycle.py` — Container create/start/stop/resume
- `src/orchestrator/permissions.py` — Generate permissions.json
- `src/orchestrator/auto_pause.py` — 7-day inactivity check

### Modified Files
- `src/api/main.py` — Register new routes
- `src/orchestrator/main.py` — Add lifecycle endpoints
- `docs/ARCHITECTURE-v2.md` — Update with final state machine

---

## Test Criteria

### TC-1: Signup Flow
Given: A new kid with email "test@example.com", age 12
When: They submit the signup form
Then: User record created with status `PENDING_PROFILE`

### TC-2: Profile Completion
Given: User in `PENDING_PROFILE` status
When: They submit display name, avatar, interests
Then: Status changes to `PENDING_RESTRICTIONS`

### TC-3: Admin Restrictions Configuration
Given: User in `PENDING_RESTRICTIONS` status
When: Admin sets age_group="10-12", model="gemma4:31b-cloud"
Then: Status changes to `PENDING_APPROVAL`, permissions.json written

### TC-4: Admin Approval → Container Creation
Given: User in `PENDING_APPROVAL` with restrictions configured
When: Admin clicks "Approve"
Then: Status → `APPROVED` → `CONTAINER_READY`, Docker container running, port assigned

### TC-5: Admin Reject
Given: User in `PENDING_APPROVAL`
When: Admin clicks "Reject" with reason "age inappropriate"
Then: Status → `REJECTED`, user notified, no container created

### TC-6: Auto-Pause
Given: User in `CONTAINER_READY`, last message 8 days ago
When: Orchestrator runs daily cron check
Then: Container stopped, status → `SUSPENDED`

### TC-7: Auto-Resume
Given: User in `SUSPENDED` (auto-paused)
When: Kid logs in and sends chat message
Then: Container restarted, status → `CONTAINER_READY`

### TC-8: Admin Terminate
Given: User in `CONTAINER_READY`
When: Admin clicks "Terminate" and confirms
Then: Container destroyed, data archived, status → `TERMINATED`

### TC-9: Security — Kid Cannot Access Admin
Given: Kid with valid JWT token
When: They send GET /api/admin/pending
Then: Response 403 Forbidden

### TC-10: Security — No Duplicate Emails
Given: User with email "test@example.com" already exists
When: New signup with same email
Then: Response 400 "Email already registered"

---

## Edge Cases

### EC-1: Container Creation Failure
- If `docker run` fails during approval, log error, notify admin, keep user in `APPROVED` state
- Admin can retry container creation via "Retry Container" button

### EC-2: Port Exhaustion
- If all 8 ports (7884-7891) are assigned, reject new approvals with "Max capacity reached"
- Admin sees capacity indicator: "6/8 containers active"

### EC-3: Admin Self-Approval
- Admin users should not need approval workflow
- Admin account created manually (not via signup form)

### EC-4: Concurrent Admin Actions
- Two admins approve same user simultaneously → second gets 409 Conflict
- Use database transactions with row-level locking

### EC-5: Network Failure During Container Start
- Orchestrator retries container start up to 3 times with exponential backoff
- After 3 failures: mark container status as "error", notify admin

---

## Timeline Estimate

| Phase | Days | Description |
|-------|------|-------------|
| v1 Spec | 0.5 | This document |
| Claude Review | 0.25 | Architectural feedback |
| Codex Review | 0.25 | Implementation concerns |
| v2 Spec | 0.25 | Corrections |
| Implementation | 2 | Code + unit tests |
| Alfred Validation | 0.5 | End-to-end testing |
| Bug fixes | 0.5 | Address Alfred findings |
| **Total** | **~4 days** | |

---

## Open Questions

1. **Q:** Should the signup form be a standalone HTML page or integrated into the Next.js portal?
   **A:** For POC, standalone HTML on the Flask API (port 7882). Next.js portal is ticket #8.

2. **Q:** Do we need password reset flow for POC?
   **A:** No. Email + password only, no reset. Phase 2.

3. **Q:** Should rejected users be able to reapply?
   **A:** No for POC. They can create a new account with different email. Phase 2.

4. **Q:** How does admin get notified of new pending users?
   **A:** Admin dashboard shows count badge. Real-time notifications (SSE/WebSocket) deferred to Phase 2.

5. **Q:** Should we encrypt user data at rest in SQLite?
   **A:** No for POC. SQLite file on host SSD. Phase 2 with LUKS per volume.

---

## Dependencies

- Docker daemon running on pi-agent
- SQLite database initialized (orchestrator.db)
- Ollama reachable at 127.0.0.1:11434
- Port range 7884-7891 available
- `/var/abis/permissions/` directory writable by orchestrator
- `/var/abis/volumes/` directory exists for bind mounts

---

*Spec v1.0 — Ready for Claude Code review.*
