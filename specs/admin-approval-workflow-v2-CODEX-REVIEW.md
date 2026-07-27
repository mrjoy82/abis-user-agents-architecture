# Codex Review: Admin Approval Workflow Spec v2 (MVP Cut)

**Reviewer:** Codex (implementation/dev perspective)
**Date:** 2026-07-27
**Classification:** Shippable in ~2 days with 5 fixes. Several hidden blockers identified.

---

## Executive Summary

The v2 spec is a massive improvement over v1 — Claude's cuts were correct and well-applied. The scope now fits 2 days of coding for a single developer. Most requirements are straightforward FastAPI + raw SQL + `subprocess` calls.

**However, there are 5 issues that will block implementation or silently break at runtime.** 3 are CRITICAL (must fix before coding), 2 are IMPORTANT (will bite you during testing). The rest are polish.

---

## 1. Can Each Requirement Be Coded in the Estimated Time?

| Requirement | Estimate | Verdict |
|---|---|---|
| FR-1: Signup (validation + bcrypt + INSERT) | 2-3 hrs | Yes. Standard. |
| FR-2: Admin dashboard (raw HTML table) | 2-3 hrs | Yes. Jinja2 + one query. |
| FR-3: Approve (DB tx + permissions.json + docker run) | 4-6 hrs | Tight. Docker subprocess debugging eats time. |
| FR-4: Reject (UPDATE + soft delete) | 30 min | Yes. Trivial. |
| FR-5: Active users + pause/resume/terminate | 3-4 hrs | Yes. Mostly docker subprocess wrappers. |
| FR-6: Login + JWT | 2 hrs | Yes. python-jose + passlib. |
| Bootstrap script + wiring | 1-2 hrs | Yes. |
| **Total** | **~14-20 hrs** | **Fits in 2 days** if you don't chase rabbit holes. |

**Risk:** FR-3 (Approve) is the only heavyweight item. Docker bind mount permissions and port pool races will consume unexpected time. Budget 6 hours, not 4.

---

## 2. Hidden Dependencies and Blockers

### CRITICAL: The "kid chats" WebSocket proxy is missing from v2

**Issue:** After admin approves and container spins up, the spec says "User can now chat" (FR-3). But v2 defines NO endpoints for how a kid's message reaches their container. The architecture doc says the orchestrator proxies ALL traffic, but v2 only gives the orchestrator container lifecycle endpoints (create/start/stop/rm).

**Impact:** You will have running containers and a login token, but no way to deliver a chat message. This is the core user story.

**Fix:** Add to v2 or accept it as a separate ticket. The simplest POC approach: ABIS API opens a WebSocket to the kid's browser, then proxies messages to the container's WebSocket (`ws://127.0.0.1:<port>/ws/chat`). No orchestrator involvement needed for chat in POC. Orchestrator only manages lifecycle.

**Classification:** CRITICAL. This is a functional gap, not just an omission.

---

### CRITICAL: Docker bind mount target `/home/user` does not exist in the base image

**Issue:** The spec's `docker run` command mounts `-v /var/abis/volumes/kid-<id>:/home/user`. But the prototype Dockerfile uses `WORKDIR /app` and does not create `/home/user`.

**Impact:** Docker will create `/home/user` inside the container at runtime (as root), but the application runs from `/app`. The kid's persistent data will be written to a directory the app never uses. If the ATA agent stores files in `~/workspace/` or `~/.hermes/`, those resolve to the container user's home directory — which is NOT `/home/user` unless you explicitly create a user named `user` with home `/home/user`.

**Fix:** Either (a) change the Dockerfile to create `RUN useradd -m user` and `WORKDIR /home/user`, or (b) mount to `/app/data` and have the agent use that path. For POC, option (a) is simplest and matches the architecture doc's intent.

**Classification:** CRITICAL. Container will run but data won't persist where expected.

---

### CRITICAL: `docker run -v` auto-creates host directories as root

**Issue:** When `docker run` mounts a host path that doesn't exist, Docker creates it as root with permissions `drwxr-xr-x`. The ABIS API (running as `matthieu`) may not be able to write to `/var/abis/volumes/` afterward, and the container's internal user may not be able to read it.

**Impact:** Permission denied errors on container startup or when the agent tries to write files. On a Pi, debugging Docker volume permissions is annoying and time-consuming.

**Fix:** In the approve endpoint, BEFORE calling `docker run`, create the directory explicitly:
```python
import os
os.makedirs(f"/var/abis/volumes/kid-{user_id}", exist_ok=True)
os.chmod(f"/var/abis/volumes/kid-{user_id}", 0o755)
```
Better yet, run a small `docker run --rm -v ... busybox chown` to set container UID ownership. But for POC, just `os.makedirs` as the API user and ensure the container runs with the same UID (Docker `--user $(id -u)`).

**Classification:** CRITICAL. Will fail on first container creation if `/var/abis/volumes/` doesn't already have kid subdirs.

---

### IMPORTANT: No mechanism to clean up soft-deleted rejected users after 30 days

**Issue:** FR-4 says "User data retained for 30 days then deleted (soft-delete: set `deleted_at` timestamp)". But there is no cron job, no scheduled task, and no process that actually performs the deletion.

**Impact:** Data accumulates forever. For a POC with 8 users, irrelevant. But if you forget about it, you'll eventually have a GDPR/PDPO compliance problem.

**Fix:** Add a simple daily cron or systemd timer: `sqlite3 /var/abis/orchestrator.db "DELETE FROM users WHERE deleted_at < datetime('now', '-30 days')"`. Or just document: "Manual cleanup for POC." Don't let the spec claim automatic deletion if it's not implemented.

**Classification:** IMPORTANT. Spec overpromises.

---

### IMPORTANT: The orchestrator service startup is unspecified

**Issue:** The spec modifies `src/orchestrator/main.py` and says it binds to `127.0.0.1:7883`. But who starts it? Is it a systemd service? A subprocess of the API? A separate `uvicorn` process?

**Impact:** You'll write the orchestrator endpoints but the API can't reach them because nothing is listening on 7883.

**Fix:** Clarify in the spec: "Run orchestrator as `python -m uvicorn src.orchestrator.main:app --port 7883 --host 127.0.0.1` in a separate terminal/tmux pane, or add a systemd unit. For POC, manual start is fine."

**Classification:** IMPORTANT. Deployment gap.

---

## 3. Are the API Endpoints Implementable with FastAPI + Raw SQL?

**Yes, all of them.** FastAPI + raw SQL is a good fit for this scope. However, several subtleties:

### IMPORTANT: Use `aiosqlite`, not `sqlite3`, in FastAPI handlers

**Issue:** FastAPI routes are async. `sqlite3` blocks the event loop. With 8 users it's fine, but any slow query (like a large join) will stall ALL requests.

**Impact:** Hanging requests, poor concurrency.

**Fix:** Use `aiosqlite` — it wraps sqlite3 in async/await and still lets you write raw SQL. It's a ~50KB dependency.

```python
import aiosqlite

async def get_db():
    async with aiosqlite.connect("/var/abis/orchestrator.db") as db:
        yield db
```

**Classification:** IMPORTANT. Not a blocker, but saves debugging time.

---

### NICE-TO-HAVE: No `updated_at` trigger in schema

**Issue:** SQLite does not auto-update `updated_at` on UPDATE. The schema defines `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP` but never updates it.

**Fix:** Add an explicit UPDATE in every mutation endpoint, or use an SQLite trigger (overkill for POC). Just document: "For POC, `updated_at` is set on creation only."

**Classification:** NICE-TO-HAVE.

---

## 4. Are the Docker Commands Correct for the Pi Environment?

### CRITICAL: Missing `--user` and `--network` flags

**Issue:** The spec's `docker run` is:
```bash
docker run -d --name kid-<id> -p <port>:7884 -v ... -v ... abis-ata-base
```

This is missing:
- `--memory=1g --cpus=1.0` (from architecture doc, should be enforced)
- `--network` or `--add-host=host.docker.internal:host-gateway` (containers need to reach Ollama on 127.0.0.1:11434)
- `--user` (running as root inside container is unnecessary risk)
- `--restart unless-stopped` or not? Spec says admin manually pauses/resumes.

**Impact:**
- Container can't reach Ollama because `127.0.0.1` inside the container is the container, not the host.
- No resource limits means one runaway container can eat all 16GB RAM.
- Container runs as root.

**Fix:** Update the docker command:
```bash
docker run -d \
  --name kid-<user_id> \
  --memory=1g \
  --cpus=1.0 \
  --network host \
  -v /var/abis/volumes/kid-<user_id>:/home/user \
  -v /var/abis/permissions/kid-<user_id>.json:/etc/ata/permissions.json:ro \
  abis-ata-base
```
Using `--network host` is the simplest way for the container to reach `127.0.0.1:11434` on the Pi. Alternatively, use Docker's `host.docker.internal` with `--add-host`. But `--network host` means you can't use `-p` for port mapping — the container listens directly on the host network. That's actually fine for POC since each container needs a unique port anyway.

Wait — if `--network host`, then `-p` is ignored and the container's port 7884 binds directly to host port 7884. That means you can't assign ports dynamically! The container would always claim 7884 on the host, and you can't run 8 of them.

**Better fix:** Use bridge network with explicit host binding:
```bash
docker run -d \
  --name kid-<user_id> \
  --memory=1g \
  --cpus=1.0 \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:<assigned_port>:7884 \
  -v ... \
  -v ... \
  abis-ata-base
```
Then inside the container, Ollama URL should be `http://host.docker.internal:11434` instead of `127.0.0.1:11434`. Update the prototype `main.py` accordingly.

**Classification:** CRITICAL. The current docker command will not work for networking.

---

### IMPORTANT: The base image `abis-ata-base` may need ARM64 rebuild

**Issue:** The prototype uses `python:3.11-slim` which supports ARM64. But if any wheel is not available for ARM64, `pip install` will try to compile from source. On a Pi, this is slow or fails if build tools are missing.

**Fix:** Ensure the base Dockerfile includes `build-essential` or equivalent if needed, or pin ARM64-compatible wheels. For the current requirements (fastapi, uvicorn, httpx, websockets), all have ARM64 wheels. Should be fine.

**Classification:** IMPORTANT. Test `docker build` on the Pi early.

---

## 5. Race Conditions and Concurrency Issues

### CRITICAL: Port pool assignment has a race condition

**Issue:** The spec's port pool logic (EC-3) says: "Two admins approve simultaneously → second gets 409 Conflict (row-level lock on port_pool)". **SQLite does NOT have row-level locks.** SQLite serializes ALL writes at the database level. The race condition is real, but the resolution is different.

A naive implementation:
```python
# WRONG — race condition
port = await db.execute("SELECT port FROM port_pool WHERE user_id IS NULL LIMIT 1")
await db.execute("UPDATE port_pool SET user_id = ? WHERE port = ?", (user_id, port))
```

Between the SELECT and UPDATE, another request could claim the same port.

**Fix:** Use an atomic UPDATE with RETURNING (SQLite 3.35+) or wrap in `BEGIN IMMEDIATE`:
```python
await db.execute("BEGIN IMMEDIATE")
port = await db.execute("SELECT port FROM port_pool WHERE user_id IS NULL LIMIT 1")
if not port:
    await db.execute("ROLLBACK")
    raise HTTPException(503, "Max capacity reached")
await db.execute("UPDATE port_pool SET user_id = ? WHERE port = ? AND user_id IS NULL", (user_id, port))
if db.changes == 0:
    await db.execute("ROLLBACK")
    raise HTTPException(409, "Port was just claimed")
await db.execute("COMMIT")
```

With `BEGIN IMMEDIATE`, the second writer blocks until the first commits. No 409 — just serialization. The 409 only happens if you check `changes == 0` after UPDATE.

**Classification:** CRITICAL. Spec misrepresents SQLite concurrency.

---

### CRITICAL: Approve endpoint is not atomic across docker + DB

**Issue:** The approve flow is:
1. UPDATE user status to ACTIVE
2. Write permissions.json
3. `docker run`
4. INSERT container record
5. UPDATE port_pool

Steps 1, 4, 5 are DB operations. Step 3 is an external subprocess. You cannot wrap a docker subprocess in a DB transaction.

**Impact:** If docker run succeeds but the INSERT/UPDATE fails (API crashes, disk full, power loss), you have:
- A running container
- A user marked ACTIVE
- No container record
- A consumed port that is never freed

**Fix:** Do ALL DB mutations FIRST in one transaction (BEGIN IMMEDIATE), then call `docker run`. If docker fails, update container status to `error` in a separate transaction. If the DB tx fails, don't call docker at all.

```python
# Correct order:
await db.execute("BEGIN IMMEDIATE")
await db.execute("UPDATE users SET status='ACTIVE' WHERE id=?", (user_id,))
port = ... # claim port atomically
await db.execute("INSERT INTO containers ...")
await db.execute("COMMIT")

try:
    subprocess.run(["docker", "run", ...], check=True)
except subprocess.CalledProcessError:
    await db.execute("UPDATE containers SET status='error' WHERE user_id=?", (user_id,))
```

**Classification:** CRITICAL. Will leak containers and ports.

---

### IMPORTANT: No retry logic for docker commands

**Issue:** Docker commands can fail transiently (daemon busy, network hiccup pulling image). The spec says "If docker run fails, log error, keep user ACTIVE but mark container_status as error". No retry.

**Impact:** Admin has to manually retry. For POC, acceptable. But document it.

**Fix:** At minimum, wrap `docker run` in a `try/except` and return a clear error message to the admin dashboard. Don't let the exception bubble up as a 500.

**Classification:** IMPORTANT.

---

## 6. Simplest Way to Implement Each Feature

### Signup / Login
- `passlib[bcrypt]` for hashing (salt rounds 10 for Pi speed, 12 is fine too).
- `python-jose[cryptography]` for JWT. Store secret in a file, not hardcoded.
- `email-validator` library or simple regex for email validation.
- Raw SQL: one INSERT, one SELECT.

### Admin Dashboard
- FastAPI `Jinja2Templates`. Two HTML files, zero CSS.
- Single query for pending: `SELECT id, name, age, created_at FROM users WHERE status='PENDING'`.
- Single query for active: `SELECT u.id, u.name, u.age, c.status FROM users u LEFT JOIN containers c ON u.id=c.user_id WHERE u.status='ACTIVE'`.
- Buttons are plain `<form method="post" action="/api/admin/users/{id}/approve">` with no JS.

### Approve Action
- BEGIN IMMEDIATE tx: update user, claim port, insert container record.
- Write permissions.json with `json.dump()`.
- `subprocess.run(["docker", "run", "-d", "--name", f"kid-{user_id}", ...], check=True, capture_output=True, text=True)`.
- Parse container ID from stdout. Update containers table with docker_container_id.
- If any step fails, rollback tx before docker call. If docker fails, mark `error`.

### Reject Action
- `UPDATE users SET status='REJECTED', deleted_at=CURRENT_TIMESTAMP WHERE id=?`. Done.

### Pause / Resume / Terminate
- `subprocess.run(["docker", "stop", f"kid-{user_id}"], ...)`.
- Update `containers.status` to `paused` / `running` / `none`.
- Terminate: `docker rm -f`, then `UPDATE port_pool SET user_id=NULL WHERE user_id=?`, then soft-delete user.

### Port Pool
- Pre-seed 8 rows. Atomic claim with UPDATE ... WHERE user_id IS NULL.
- On terminate, UPDATE port_pool SET user_id=NULL.

---

## 7. Missing Dependencies

Add to requirements (or ensure installed):
```
fastapi==0.115.6
uvicorn[standard]==0.32.1
aiosqlite==0.20.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
email-validator==2.2.0
jinja2==3.1.4
python-multipart==0.0.20  # for FastAPI form parsing
```

---

## 8. Classification Summary

| # | Issue | Classification |
|---|---|---|
| 1 | WebSocket chat proxy missing from v2 | **CRITICAL** |
| 2 | Docker `/home/user` mount target mismatch | **CRITICAL** |
| 3 | `docker run -v` auto-creates dirs as root | **CRITICAL** |
| 4 | SQLite has no row-level locks (port pool race) | **CRITICAL** |
| 5 | Approve endpoint not atomic (docker + DB split) | **CRITICAL** |
| 6 | Docker networking (Ollama reachability) broken | **CRITICAL** |
| 7 | No cleanup mechanism for 30-day soft delete | **IMPORTANT** |
| 8 | Orchestrator startup unspecified | **IMPORTANT** |
| 9 | Use `aiosqlite` not blocking `sqlite3` | **IMPORTANT** |
| 10 | Missing base image ARM64 validation | **IMPORTANT** |
| 11 | No docker retry / error handling | **IMPORTANT** |
| 12 | `updated_at` never actually updates | NICE-TO-HAVE |
| 13 | No rate limiting on public endpoints | NICE-TO-HAVE |
| 14 | Admin dashboard XSS risk (no escaping noted) | NICE-TO-HAVE |

---

## Recommended Actions Before Coding

1. **Fix the docker command** in the spec to use `--add-host=host.docker.internal:host-gateway` and `-p 127.0.0.1:<port>:7884`, then update the prototype `main.py` Ollama URL to `http://host.docker.internal:11434`.
2. **Add the missing WebSocket proxy** to the spec, or create a separate ticket for it. Don't pretend "User can now chat" is done.
3. **Document the port pool claim logic** with `BEGIN IMMEDIATE` and atomic UPDATE, not "row-level lock".
4. **Add `os.makedirs` + `os.chmod`** before `docker run` in the approve flow.
5. **Fix the base Dockerfile** to create a `user` account with home `/home/user`, or change mount target to match the image.

---

## Verdict

**Shippable in 2 days if the 5 CRITICAL issues above are addressed.** The v2 spec is lean and correct in spirit, but it still has a few "architecture hand-waves" that become runtime bugs on a real Pi. Fix the docker networking, the DB transaction ordering, and the mount paths, and you'll have a working MVP.

Everything else is polish for Phase 2.
