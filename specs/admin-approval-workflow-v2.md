# Admin Approval Workflow and User Management — Spec v2 (MVP Cut)

**Ticket:** #5 [task] Implement admin approval workflow and user management
**Depends on:** #4 [prototype] (validated)
**Date:** 2026-07-27
**Author:** Hermes (post-Claude review)
**Status:** v2 — Addressed Claude's feedback

---

## Changelog from v1

### Simplifications (Claude review applied)
- **REMOVED:** 8-state machine → **3 states:** `PENDING` → `ACTIVE` → `REJECTED`
- **REMOVED:** Separate profile completion → **Merged into signup form**
- **REMOVED:** Admin restriction configuration UI → **Hardcoded by age group**
- **REMOVED:** ORM models → **Raw SQLite with helper functions**
- **REMOVED:** Audit logging table → **Application logs only**
- **REMOVED:** Auto-pause cron → **Manual pause/resume only**
- **REMOVED:** Data archiving → **Simple delete for POC**
- **REMOVED:** Token usage dashboard → **Deferred to Phase 2**
- **REMOVED:** Alert counts → **No moderation pipeline in POC**
- **REMOVED:** Content filter levels → **Single hardcoded system prompt**
- **REMOVED:** Avatar uploads → **Use default avatar or initials**
- **REMOVED:** Container metrics (memory_mb, cpu_percent, pid) → **Use `docker ps` for now**
- **REMOVED:** Email notifications → **Status shown on dashboard only**
- **ADDED:** `password_hash` and `is_admin` columns to schema
- **ADDED:** Admin bootstrap CLI script
- **ADDED:** Port pool tracking and reuse logic
- **ADDED:** Orchestrator binds to 127.0.0.1:7883 (localhost only)
- **CHANGED:** File count from 17 → **~6 files**
- **CHANGED:** Timeline from 4 days → **2 days target**

---

## Summary

Build the minimal user signup and admin approval flow for ABIS Academy POC. One signup form, one admin dashboard, one-click approve/reject. Container spins up synchronously on approval. No bells and whistles.

---

## Context

- Docker on Raspberry Pi 5 (16GB RAM), max 8 concurrent kids
- SQLite for state, FastAPI for API (port 7882)
- Cloud models via Ollama (gemma4:31b-cloud)
- Email + password auth for POC
- Raw SQL only — no ORMs
- Admin: Matthieu (hardcoded one admin account)

---

## Requirements

### FR-1: User Signup Form (Single Step)
- **Fields:**
  - Email (required, unique, validated format)
  - Name (required, used as display name)
  - Age (required, integer, 10-18)
  - Password (required, min 8 chars)
- **Validation:**
  - Email must not already exist
  - Age 10-18
  - Password min 8 chars
- **Output:** User record created with status `PENDING`
- **Note:** No separate profile step. Name = display name. No avatar, no interests, no language selection.

### FR-2: Admin Dashboard — Pending Approvals
- **Route:** `/admin` (HTML page served by FastAPI)
- **Columns:**
  - Name
  - Age
  - Signup date
  - Approve button
  - Reject button
- **No filters, no sorting.** Raw HTML table. No CSS framework.

### FR-3: Admin Approve Action
- **Effects:**
  1. User status: `PENDING` → `ACTIVE`
  2. Generate `permissions.json` based on age (hardcoded rules below)
  3. Write `/var/abis/permissions/<user_id>.json`
  4. Orchestrator: `docker run` with bind mounts
  5. Assign next free port from pool (7884-7891)
  6. User can now chat
- **Error:** If docker run fails, log error, keep user `ACTIVE` but mark container_status as `error`
- **Port pool:** Track free ports in SQLite. Reuse freed ports on termination.

### FR-4: Admin Reject Action
- **Effects:**
  1. User status: `PENDING` → `REJECTED`
  2. No container created
  3. User data retained for 30 days then deleted (soft-delete: set `deleted_at` timestamp)

### FR-5: Admin Dashboard — Active Users
- **Route:** `/admin/active`
- **Columns:**
  - Name
  - Age
  - Container status (running / error / none)
  - Actions: Pause, Resume, Terminate
- **Pause:** `docker stop` container. Kid sees "Agent paused."
- **Resume:** `docker start` container.
- **Terminate:** `docker rm -f` + soft-delete user data.

### FR-6: User Login
- **Route:** `/login`
- **Fields:** email, password
- **Response:** JWT token
- **Redirect:**
  - If status `PENDING` → "Waiting for admin approval"
  - If status `ACTIVE` → Chat page
  - If status `REJECTED` → "Your request was rejected"

---

## Hardcoded Rules (No Admin Config UI)

### Age Group → Permissions
```json
// Age 10-12 (default POC permissions)
{
  "chat": true,
  "file_management": true,
  "web_search": false,
  "code_execution": false,
  "terminal_commands": false,
  "browser_automation": false,
  "image_generation": false,
  "cron_jobs": false,
  "openclaw_bridge": false
}

// Age 15+ (unlocks more tools)
{
  "chat": true,
  "file_management": true,
  "web_search": true,
  "code_execution": true,
  "terminal_commands": false,
  "browser_automation": false,
  "image_generation": false,
  "cron_jobs": false,
  "openclaw_bridge": false
}
```

### Age Group → Model
- Both ages use `gemma4:31b-cloud` for POC.
- Model picker deferred to Phase 2.

### Age Group → Token Quota
- Not enforced in POC. Deferred to Phase 2.

### Age Group → Time Window
- Not enforced in POC. Deferred to Phase 2.

### Age Group → File Size Limit
- Not enforced in POC. Deferred to Phase 2.

---

## Database Schema (Raw SQLite)

```sql
-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    status TEXT DEFAULT 'PENDING',  -- PENDING, ACTIVE, REJECTED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP            -- soft delete
);

-- Container tracking
CREATE TABLE IF NOT EXISTS containers (
    user_id INTEGER PRIMARY KEY,
    docker_container_id TEXT,
    host_port INTEGER,
    status TEXT DEFAULT 'none',     -- none, running, paused, error
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Port pool
CREATE TABLE IF NOT EXISTS port_pool (
    port INTEGER PRIMARY KEY,
    user_id INTEGER,                -- NULL if free
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Initialize port pool (7884-7891)
INSERT OR IGNORE INTO port_pool (port, user_id) VALUES
(7884, NULL), (7885, NULL), (7886, NULL), (7887, NULL),
(7888, NULL), (7889, NULL), (7890, NULL), (7891, NULL);
```

---

## API Endpoints

### Public (No Auth)
```
POST /api/signup
  Body: {email, name, age, password}
  Response: {user_id, status: "PENDING", message: "Waiting for admin approval"}

POST /api/login
  Body: {email, password}
  Response: {token, user: {id, name, status}}

GET /api/health
  Response: {status: "ok"}
```

### Admin (JWT + is_admin Required)
```
GET /api/admin/pending
  Response: [{id, name, age, created_at}]

GET /api/admin/active
  Response: [{id, name, age, container_status, created_at}]

POST /api/admin/users/:id/approve
  Response: {status: "ACTIVE", port: 7884, message: "Container created"}

POST /api/admin/users/:id/reject
  Response: {status: "REJECTED"}

POST /api/admin/users/:id/pause
  Response: {status: "paused"}

POST /api/admin/users/:id/resume
  Response: {status: "running"}

DELETE /api/admin/users/:id/terminate
  Response: {status: "TERMINATED"}
```

---

## State Machine

```
SIGNUP
  → PENDING (waiting for admin)
    → admin approves → ACTIVE (container created, kid can chat)
    → admin rejects → REJECTED
```

Container status is SEPARATE from user status:
- User status: `PENDING` | `ACTIVE` | `REJECTED`
- Container status: `none` | `running` | `paused` | `error`

---

## Files to Create

### New Files (~6)
1. `src/api/db.py` — SQLite connection + raw SQL helpers
2. `src/api/routes/auth.py` — signup, login, JWT
3. `src/api/routes/admin.py` — approve, reject, pause, resume, terminate, dashboard data
4. `src/api/middleware/auth.py` — JWT validation, admin check
5. `src/api/templates/signup.html` — bare HTML form
6. `src/api/templates/admin.html` — bare HTML table

### Modified Files
- `src/api/main.py` — Register new routes
- `src/orchestrator/main.py` — Add container lifecycle endpoints (create, start, stop, rm)

### Bootstrap Script
- `scripts/create_admin.py` — One-time CLI: `python scripts/create_admin.py --email admin@abis.hk --password <password>`

---

## Container Lifecycle (Orchestrator Endpoints)

```
POST /orchestrator/containers
  Body: {user_id, name, age}
  Response: {container_id, port}
  Action: docker run -d --name kid-<id> -p <port>:7884 -v /var/abis/volumes/kid-<id>:/home/user -v /var/abis/permissions/kid-<id>.json:/etc/ata/permissions.json:ro abis-ata-base

POST /orchestrator/containers/:id/start
  Action: docker start kid-<id>

POST /orchestrator/containers/:id/stop
  Action: docker stop kid-<id>

DELETE /orchestrator/containers/:id
  Action: docker rm -f kid-<id>
```

**Security:** Orchestrator binds to `127.0.0.1:7883` only. No external access.

---

## Test Criteria

### TC-1: Signup
Given: New email "test@example.com", name "Test Kid", age 12, password "password123"
When: POST /api/signup
Then: User created with status `PENDING`, password hashed with bcrypt

### TC-2: Duplicate Email
Given: Email "test@example.com" already exists
When: POST /api/signup with same email
Then: Response 400 "Email already registered"

### TC-3: Admin Approve
Given: User in `PENDING` status, age 12
When: Admin POST /api/admin/users/1/approve
Then: Status → `ACTIVE`, container created, port assigned (7884-7891), permissions.json written

### TC-4: Admin Reject
Given: User in `PENDING`
When: Admin POST /api/admin/users/1/reject
Then: Status → `REJECTED`, no container created

### TC-5: Login Redirect
Given: User status `PENDING`
When: POST /api/login
Then: Token returned, but frontend shows "Waiting for approval"

### TC-6: Security — Kid Cannot Access Admin
Given: Kid JWT token
When: GET /api/admin/pending
Then: 403 Forbidden

### TC-7: Port Reuse
Given: User terminated, port 7884 freed
When: New user approved
Then: Port 7884 reassigned

### TC-8: Admin Bootstrap
Given: Fresh database
When: Run `python scripts/create_admin.py --email admin@abis.hk --password admin123`
Then: Admin user created with `is_admin=1`

---

## Edge Cases

### EC-1: Container Creation Failure
- Docker run fails → log error, mark container_status as `error`, user stays `ACTIVE`
- Admin sees "Error" in dashboard, can retry

### EC-2: Port Exhaustion
- All 8 ports assigned → new approval returns 503 "Max capacity reached"
- Admin sees "8/8 containers active" indicator

### EC-3: Concurrent Approvals
- Two admins approve simultaneously → second gets 409 Conflict (row-level lock on port_pool)

### EC-4: Terminated User Data
- Soft delete: set `deleted_at` timestamp
- Physical cleanup deferred to Phase 2 (cron job)

---

## Timeline Estimate

| Phase | Days | Description |
|-------|------|-------------|
| v1 Spec | 0.5 | Written |
| Claude Review | 0.25 | Done — major cuts identified |
| v2 Spec | 0.25 | This document (corrections) |
| Implementation | 1.5 | Code + tests |
| Codex Review | 0.25 | Implementation review |
| Bug fixes | 0.25 | Address Codex findings |
| **Total** | **~3 days** | |

**Target:** 2 days of actual coding. Review cycles add ~0.5-1 day.

---

## Open Questions (for user)

1. **Admin account:** Should I create the bootstrap script with a hardcoded password you set, or do you want to run it yourself?
2. **Password storage:** bcrypt with salt rounds 12 (standard). OK?
3. **JWT secret:** Should I generate a random secret and store it in a file you control, or use a simple hardcoded one for POC?

---

## Dependencies

- Docker daemon running
- SQLite database initialized
- `/var/abis/permissions/` directory writable
- `/var/abis/volumes/` directory exists
- Port range 7884-7891 available
- Ollama reachable at 127.0.0.1:11434 (for container runtime)

---

*Spec v2.0 — Ready for Codex review.*
