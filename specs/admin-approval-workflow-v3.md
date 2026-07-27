# Admin Approval Workflow and User Management — Spec v3 (Final)

**Ticket:** #5 [task] Implement admin approval workflow and user management
**Depends on:** #4 [prototype] (validated)
**Date:** 2026-07-27
**Author:** Hermes (post-Claude + Codex review)
**Status:** v3 — All review feedback addressed

---

## Changelog from v2

### Fixes from Codex Review (applied)
- **ADDED:** WebSocket proxy endpoint in API spec ( kid → API → container )
- **FIXED:** Docker command uses `--add-host=host.docker.internal:host-gateway` + `-p 127.0.0.1:<port>:7884`
- **FIXED:** Prototype `main.py` Ollama URL updated to `http://host.docker.internal:11434`
- **FIXED:** Base Dockerfile creates `user` account with home `/home/user`
- **FIXED:** Approve flow pre-creates volume dir with `os.makedirs(..., exist_ok=True)` + `os.chmod(..., 0o755)`
- **FIXED:** Port pool uses `BEGIN IMMEDIATE` + atomic UPDATE with `changes == 0` check (not "row-level lock")
- **FIXED:** Approve endpoint order: DB transaction FIRST (status + port claim + container record), THEN `docker run`
- **FIXED:** Use `aiosqlite` instead of blocking `sqlite3`
- **ADDED:** Dependencies list: `aiosqlite`, `python-jose[cryptography]`, `passlib[bcrypt]`, `email-validator`, `jinja2`, `python-multipart`
- **ADDED:** Orchestrator startup documented (manual `uvicorn` for POC)
- **ADDED:** Docker retry logic: `subprocess.run(..., check=True)` with `try/except`, clear error messages
- **DOCUMENTED:** 30-day soft delete is manual cleanup for POC (no automatic cron)
- **DOCUMENTED:** `updated_at` is set on creation only for POC (no trigger)

### Remaining NICE-TO-HAVE items (deferred to Phase 2)
- Rate limiting on public endpoints
- Admin dashboard XSS hardening (Jinja2 auto-escapes by default)
- Container metrics (memory, CPU) — use `docker ps` for now
- Real-time admin notifications (SSE/WebSocket)

---

## Summary

Build the minimal user signup and admin approval flow for ABIS Academy POC. One signup form, one admin dashboard, one-click approve/reject. Container spins up synchronously on approval. WebSocket proxy lets kid chat through the API to their container.

---

## Context

- Docker on Raspberry Pi 5 (16GB RAM), max 8 concurrent kids
- SQLite (aiosqlite) for state, FastAPI for API (port 7882)
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

### FR-2: User Login
- **Fields:** email, password
- **Response:** JWT token
- **Redirect:**
  - If status `PENDING` → "Waiting for admin approval" page
  - If status `ACTIVE` → Chat page (WebSocket proxy)
  - If status `REJECTED` → "Your request was rejected"

### FR-3: WebSocket Chat Proxy (API → Container)
- **Endpoint:** `ws://pi-agent:7882/ws/chat`
- **Flow:**
  1. Kid's browser connects to API WebSocket (port 7882)
  2. API validates JWT, identifies user
  3. API looks up user's assigned container port from `containers` table
  4. API proxies messages bidirectionally:
     - Kid message → forwarded to `ws://127.0.0.1:<port>/ws/chat` (container)
     - Container response stream → forwarded back to kid's browser
- **No orchestrator involvement in chat path.** Orchestrator only manages lifecycle.
- **Note:** This is a simple pass-through proxy. No safety scanning in POC (Phase 2).

### FR-4: Admin Dashboard — Pending Approvals
- **Route:** `/admin` (HTML page served by FastAPI)
- **Columns:**
  - Name
  - Age
  - Signup date
  - Approve button
  - Reject button
- **No filters, no sorting.** Raw HTML table. No CSS framework.

### FR-5: Admin Approve Action
- **Effects (strict order):**
  1. **DB transaction (BEGIN IMMEDIATE):**
     - `UPDATE users SET status='ACTIVE' WHERE id=?`
     - Claim port atomically: `UPDATE port_pool SET user_id=? WHERE port=(SELECT port FROM port_pool WHERE user_id IS NULL LIMIT 1)`
     - Verify `changes == 0` (port was free) — if 0, ROLLBACK and return 409
     - `INSERT INTO containers (user_id, host_port, status) VALUES (?, ?, 'creating')`
     - `COMMIT`
  2. **Pre-create volume directory:**
     - `os.makedirs(f"/var/abis/volumes/kid-{user_id}", exist_ok=True)`
     - `os.chmod(f"/var/abis/volumes/kid-{user_id}", 0o755)`
  3. **Write permissions.json:**
     - Based on age group (hardcoded rules below)
     - Path: `/var/abis/permissions/kid-{user_id}.json`
  4. **Docker run:**
     ```bash
     docker run -d \
       --name kid-<user_id> \
       --memory=1g \
       --cpus=1.0 \
       --add-host=host.docker.internal:host-gateway \
       -p 127.0.0.1:<assigned_port>:7884 \
       -v /var/abis/volumes/kid-<user_id>:/home/user \
       -v /var/abis/permissions/kid-<user_id>.json:/etc/ata/permissions.json:ro \
       abis-ata-base
     ```
  5. **Update container record:**
     - `UPDATE containers SET docker_container_id=?, status='running' WHERE user_id=?`
- **Error handling:**
  - If docker run fails: `UPDATE containers SET status='error' WHERE user_id=?`
  - Admin dashboard shows "Error" status with retry button
  - User stays `ACTIVE` (approval decision not lost)

### FR-6: Admin Reject Action
- **Effects:**
  1. `UPDATE users SET status='REJECTED', deleted_at=CURRENT_TIMESTAMP WHERE id=?`
  2. No container created
  3. User data retained for 30 days then manually deleted (documented: no automatic cleanup in POC)

### FR-7: Admin Dashboard — Active Users
- **Route:** `/admin/active`
- **Columns:**
  - Name
  - Age
  - Container status (running / error / none)
  - Actions: Pause, Resume, Terminate
- **Pause:** `docker stop` container. Update `containers.status='paused'`.
- **Resume:** `docker start` container. Update `containers.status='running'`.
- **Terminate:** `docker rm -f` + free port + soft-delete user.

---

## Hardcoded Rules (No Admin Config UI)

### Age Group → Permissions
```json
// Age 10-12
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

// Age 15+
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

---

## Database Schema (Raw SQLite + aiosqlite)

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
    status TEXT DEFAULT 'none',     -- none, creating, running, paused, error
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Port pool
CREATE TABLE IF NOT EXISTS port_pool (
    port INTEGER PRIMARY KEY,
    user_id INTEGER                 -- NULL if free
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

### User-facing (JWT Required)
```
GET /api/me
  Headers: Authorization: Bearer <token>
  Response: {id, name, status}

WS /ws/chat
  Headers: Authorization: Bearer <token> (passed as query param for WebSocket)
  Query: ?token=<jwt>
  Protocol: Kid message → API → Container → API → Kid (bidirectional proxy)
```

### Admin-facing (JWT + is_admin Required)
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

### Orchestrator (Localhost Only, 127.0.0.1:7883)
```
POST /orchestrator/containers
  Body: {user_id, name, age}
  Response: {docker_container_id, port}

POST /orchestrator/containers/:id/start
  Action: docker start

POST /orchestrator/containers/:id/stop
  Action: docker stop

DELETE /orchestrator/containers/:id
  Action: docker rm -f
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
- Container status: `none` | `creating` | `running` | `paused` | `error`

---

## Files to Create

### New Files (~7)
1. `src/api/db.py` — aiosqlite connection + raw SQL helpers
2. `src/api/routes/auth.py` — signup, login, JWT
3. `src/api/routes/admin.py` — approve, reject, pause, resume, terminate, dashboard data
4. `src/api/routes/chat.py` — WebSocket proxy (kid → API → container)
5. `src/api/middleware/auth.py` — JWT validation, admin check
6. `src/api/templates/signup.html` — bare HTML form
7. `src/api/templates/admin.html` — bare HTML table

### Modified Files
- `src/api/main.py` — Register new routes
- `src/orchestrator/main.py` — Add container lifecycle endpoints
- `prototype/ata/main.py` — Update Ollama URL to `host.docker.internal:11434`
- `prototype/ata/Dockerfile` — Add `RUN useradd -m user` + `WORKDIR /home/user`

### Bootstrap Script
- `scripts/create_admin.py` — One-time CLI

---

## Port Pool Atomic Claim (Correct Implementation)

```python
async def claim_port(db, user_id):
    await db.execute("BEGIN IMMEDIATE")
    
    # Claim atomically with UPDATE ... WHERE port = (SELECT ...)
    await db.execute("""
        UPDATE port_pool 
        SET user_id = ? 
        WHERE port = (
            SELECT port FROM port_pool 
            WHERE user_id IS NULL 
            LIMIT 1
        )
    """, (user_id,))
    
    if db.changes == 0:
        await db.execute("ROLLBACK")
        raise HTTPException(503, "Max capacity reached")
    
    # Get the claimed port
    cursor = await db.execute("SELECT port FROM port_pool WHERE user_id = ?", (user_id,))
    row = await cursor.fetchone()
    port = row[0]
    
    await db.execute("COMMIT")
    return port
```

**Note:** SQLite serializes writes at the DB level. `BEGIN IMMEDIATE` ensures the second writer blocks until the first commits. No true "row-level lock" exists — the entire DB is locked for writes.

---

## Approve Flow (Correct Order)

```python
async def approve_user(user_id):
    # Step 1: DB transaction FIRST
    await db.execute("BEGIN IMMEDIATE")
    await db.execute("UPDATE users SET status='ACTIVE' WHERE id=?", (user_id,))
    port = await claim_port(db, user_id)
    await db.execute("INSERT INTO containers (user_id, host_port, status) VALUES (?, ?, 'creating')", (user_id, port))
    await db.execute("COMMIT")
    
    # Step 2: Pre-create volume directory
    vol_path = f"/var/abis/volumes/kid-{user_id}"
    os.makedirs(vol_path, exist_ok=True)
    os.chmod(vol_path, 0o755)
    
    # Step 3: Write permissions.json
    permissions = generate_permissions(age)  # hardcoded by age
    with open(f"/var/abis/permissions/kid-{user_id}.json", "w") as f:
        json.dump(permissions, f)
    
    # Step 4: Docker run
    try:
        result = subprocess.run(
            ["docker", "run", "-d",
             "--name", f"kid-{user_id}",
             "--memory=1g",
             "--cpus=1.0",
             "--add-host=host.docker.internal:host-gateway",
             "-p", f"127.0.0.1:{port}:7884",
             "-v", f"{vol_path}:/home/user",
             "-v", f"/var/abis/permissions/kid-{user_id}.json:/etc/ata/permissions.json:ro",
             "abis-ata-base"],
            check=True, capture_output=True, text=True
        )
        container_id = result.stdout.strip()
        
        # Step 5: Update container record
        await db.execute("UPDATE containers SET docker_container_id=?, status='running' WHERE user_id=?", (container_id, user_id))
        
    except subprocess.CalledProcessError as e:
        await db.execute("UPDATE containers SET status='error' WHERE user_id=?", (user_id,))
        raise HTTPException(500, f"Container creation failed: {e.stderr}")
```

---

## Docker Command (Correct)

```bash
docker run -d \
  --name kid-<user_id> \
  --memory=1g \
  --cpus=1.0 \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:<assigned_port>:7884 \
  -v /var/abis/volumes/kid-<user_id>:/home/user \
  -v /var/abis/permissions/kid-<user_id>.json:/etc/ata/permissions.json:ro \
  abis-ata-base
```

**Inside container:** Ollama URL is `http://host.docker.internal:11434` (not `127.0.0.1`)

---

## Dependencies

```
fastapi==0.115.6
uvicorn[standard]==0.32.1
aiosqlite==0.20.0
httpx==0.27.2
websockets==14.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
email-validator==2.2.0
jinja2==3.1.4
python-multipart==0.0.20
```

---

## Test Criteria

### TC-1: Signup
Given: New email, name, age 12, password
When: POST /api/signup
Then: User created with status `PENDING`, password hashed

### TC-2: Duplicate Email
Given: Email already exists
When: POST /api/signup with same email
Then: 400 "Email already registered"

### TC-3: Admin Approve
Given: User in `PENDING`, age 12
When: Admin POST /api/admin/users/1/approve
Then: Status → `ACTIVE`, container created, port assigned, permissions.json written

### TC-4: Admin Reject
Given: User in `PENDING`
When: Admin POST /api/admin/users/1/reject
Then: Status → `REJECTED`, no container

### TC-5: WebSocket Chat
Given: Approved user with running container
When: Browser connects to `ws://pi-agent:7882/ws/chat?token=<jwt>`
Then: Message proxied to container, streaming response returned

### TC-6: Login Redirect
Given: User status `PENDING`
When: POST /api/login
Then: Token returned, frontend shows "Waiting for approval"

### TC-7: Security — Kid Cannot Access Admin
Given: Kid JWT token
When: GET /api/admin/pending
Then: 403 Forbidden

### TC-8: Port Reuse
Given: User terminated, port freed
When: New user approved
Then: Port reassigned

### TC-9: Container Creation Failure
Given: Docker daemon unavailable
When: Admin approves user
Then: User stays `ACTIVE`, container status = `error`, admin sees retry button

### TC-10: Admin Bootstrap
Given: Fresh database
When: Run `python scripts/create_admin.py --email admin@abis.hk --password admin123`
Then: Admin user created with `is_admin=1`

---

## Edge Cases

### EC-1: Container Creation Failure
- Docker run fails → log error, mark container status `error`, user stays `ACTIVE`
- Admin sees "Error" in dashboard, can retry

### EC-2: Port Exhaustion
- All 8 ports assigned → new approval returns 503 "Max capacity reached"
- Admin sees "8/8 containers active"

### EC-3: Concurrent Approvals
- Two admins approve simultaneously → SQLite serializes via `BEGIN IMMEDIATE`
- Second blocks until first commits. No 409 needed — just natural serialization.

### EC-4: Terminated User Data
- Soft delete: set `deleted_at` timestamp
- Physical cleanup: manual for POC. Document: "Run `DELETE FROM users WHERE deleted_at < datetime('now', '-30 days')` periodically."

### EC-5: Docker Networking
- Container must reach Ollama on host → use `--add-host=host.docker.internal:host-gateway`
- Inside container: `host.docker.internal:11434` resolves to host IP

---

## Timeline Estimate

| Phase | Days | Description |
|-------|------|-------------|
| v1 Spec | 0.5 | Written |
| Claude Review | 0.25 | Done — major cuts |
| v2 Spec | 0.25 | Cuts applied |
| Codex Review | 0.25 | Done — 6 critical fixes |
| v3 Spec | 0.25 | All fixes applied (this doc) |
| Implementation | 1.5 | Code + tests |
| Integration Test | 0.25 | End-to-end validation |
| **Total** | **~3 days** | |

---

## Open Questions (for user)

1. **Admin account:** Should I create the bootstrap script now, or do you want to run it yourself with your chosen password?
2. **JWT secret:** Generate random and store in `~/.abis/jwt-secret.txt`? Or simpler hardcoded for POC?
3. **WebSocket proxy:** Should the API WebSocket endpoint authenticate via query param (`?token=...`) or header? Query param is standard for WebSocket.

---

## Deployment Notes

### Orchestrator Startup (POC)
```bash
# Terminal 1: Start orchestrator
python -m uvicorn src.orchestrator.main:app --host 127.0.0.1 --port 7883

# Terminal 2: Start API
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 7882
```

### Production (Phase 2)
- Systemd services for both API and orchestrator
- Reverse proxy (nginx) for SSL termination
- Orchestrator on localhost only (never exposed)

---

## Review Feedback Summary

### Claude Review (v1 → v2)
| # | Issue | Resolution |
|---|-------|-----------|
| 1 | 8-state machine over-engineered | Collapsed to 3 states |
| 2 | ORM models | Removed, raw SQL only |
| 3 | Separate profile step | Merged into signup |
| 4 | Admin restriction config UI | Hardcoded by age |
| 5 | Audit logging | Cut for POC |
| 6 | Auto-pause cron | Cut for POC |
| 7 | Data archiving | Simplified to soft delete |
| 8 | Timeline 4 days | Cut to 2-day target |
| 9 | Missing password_hash column | Added to schema |
| 10 | Missing is_admin | Added to schema |

### Codex Review (v2 → v3)
| # | Issue | Resolution |
|---|-------|-----------|
| 1 | WebSocket proxy missing | Added FR-3 with full flow |
| 2 | Docker /home/user mismatch | Dockerfile creates user account |
| 3 | docker -v auto-creates as root | Pre-create with os.makedirs + chmod |
| 4 | SQLite "row-level lock" | Documented `BEGIN IMMEDIATE` + atomic UPDATE |
| 5 | Approve not atomic | DB transaction FIRST, then docker |
| 6 | Docker networking broken | `--add-host=host.docker.internal:host-gateway` |
| 7 | 30-day cleanup | Documented as manual for POC |
| 8 | Orchestrator startup | Documented manual uvicorn for POC |
| 9 | Use aiosqlite | Added to dependencies |
| 10 | Docker retry | try/except with clear error messages |

---

*Spec v3.0 — All review feedback addressed. Ready for implementation.*
