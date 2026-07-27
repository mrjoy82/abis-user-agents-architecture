# Critical Review: Admin Approval Workflow Spec v1

**Reviewer:** Claude  
**Date:** 2026-07-27  
**Classification:** Needs major cuts to ship within 2-3 days

---

## 1. Architecture Concerns

### CRITICAL: Spec contradicts project constraints
- **Issue:** Section "Files to Create" lists `src/api/models/user.py` ("User ORM model"), `restrictions.py` ("ORM model"), `container.py`, `audit.py` — but project mandate says **"No ORMs — direct SQL or lightweight wrappers only."**
- **Impact:** Implementation confusion, wasted time, possible rewrite.
- **Fix:** Remove all ORM references. Use raw SQLite + simple dataclasses or NamedTuple.

### CRITICAL: Timeline is 4+ days, user wants 2-3
- **Issue:** Spec explicitly lists ~4 days including review cycles, validation phases, bug fixes. User context says "~2-3 days for MVP, not 4+ days."
- **Impact:** Guaranteed miss of ship target.
- **Fix:** Cut scope to fit 2 days. See Recommended Simplifications below.

### IMPORTANT: Over-engineered state machine (8 states)
- **Issue:** `PENDING_PROFILE` → `PENDING_RESTRICTIONS` → `PENDING_APPROVAL` → `APPROVED` → `CONTAINER_READY` → `SUSPENDED` → `REJECTED` → `TERMINATED`.
- **Impact:** Complex frontend logic, UI gating, multiple API endpoints and templates for 8 kids on a Pi.
- **Fix:** Collapse to 3 states: `PENDING` → `ACTIVE` → `REJECTED`. Container creation is synchronous with approval. Pause/Stop are container ops, not user lifecycle states.

### IMPORTANT: Dual source of truth for permissions
- **Issue:** `user_restrictions` table duplicates data already written to `/var/abis/permissions/<user_id>.json`.
- **Impact:** Divergence risk, extra writes, schema bloat.
- **Fix:** Either JSON on disk OR SQLite row, not both. For POC, store in SQLite and mount as JSON at container start if the container needs it.

### IMPORTANT: Schema missing password field
- **Issue:** Users table has no `password_hash` column, but `POST /api/login` requires email + password.
- **Impact:** Login cannot work.
- **Fix:** Add `password_hash TEXT NOT NULL` to schema.

### IMPORTANT: Missing admin/role field
- **Issue:** No `role` or `is_admin` field in users table. Edge case EC-3 says "Admin users should not need approval workflow" but does not explain how the system knows who is admin.
- **Impact:** All endpoints requiring "admin role check" have nothing to check against.
- **Fix:** Add `is_admin INTEGER DEFAULT 0` or `role TEXT DEFAULT 'user'`.

### IMPORTANT: Container metrics fields are phantom data
- **Issue:** `containers` table tracks `memory_mb`, `cpu_percent`, `pid` — but no collector or poller is specified in the architecture.
- **Impact:** Dead columns or unexpected work to build a metrics daemon.
- **Fix:** Remove these columns for POC. Use `docker stats` ad-hoc or defer to Phase 2.

---

## 2. User Preference Conflicts (Ship-First Mentality)

### CRITICAL: Scope is ~3x what a 2-day MVP should be
- **Issue:** 17 new files, HTML templates, CSS, audit logging, auto-pause cron, data archiving, content filter levels, avatar uploads, interest tags, preferred languages.
- **Impact:** You will burn day 1 scaffolding and day 2 debugging, with no working demo.
- **Fix:** Ruthlessly defer everything not required to prove "kid signs up, admin approves, kid chats."

### CRITICAL: "Alfred Validation" and review bureaucracy
- **Issue:** Spec allocates 0.25 days for "Claude Review", 0.25 for "Codex Review", 0.25 for "v2 Spec", 0.5 for "Alfred Validation" — 1.25 days of process for a 2-day POC.
- **Impact:** Ship-first founder is being slowed down by waterfall process inside a spec.
- **Fix:** Delete these phases. Review once (now), then code.

### IMPORTANT: Kid-facing profile completion is premature
- **Issue:** FR-2 requires a second kid-facing form (display name, avatar, interests, language) before the admin even sees them.
- **Impact:** Two HTML pages, file upload handling (or avatar selection UI), multi-select logic — all before proving the core loop works.
- **Fix:** Merge signup + profile into one form. Admin sees the signup data directly.

### IMPORTANT: Content filters and keyword lists
- **Issue:** FR-3 specifies "strict/moderate/relaxed (keyword list selection)" — a whole subsystem.
- **Impact:** Who defines the keyword lists? Where are they stored? How are they enforced? This is a research project, not a 2-day ticket.
- **Fix:** Cut entirely. Use a single hardcoded "kid-safe" prompt prefix in the agent. Defer filtering to Phase 2.

---

## 3. Technical Gaps (Will Block Implementation)

### CRITICAL: No admin creation mechanism
- **Issue:** Spec says "Admin account created manually" but provides no script, endpoint, or CLI command to do this.
- **Blocker:** You cannot test any admin endpoint without an admin user.
- **Fix:** Add a one-time CLI bootstrap script: `python -m src.cli.create_admin --email admin@abis.hk --password xyz`.

### CRITICAL: No port release/reuse logic
- **Issue:** Ports assigned "sequential: 7884, 7885, ..." but when a user is terminated, that port is never returned to the pool.
- **Blocker:** After 8 approvals/terminations, you are out of ports even with zero active users.
- **Fix:** Track free ports in a simple table or in-memory set. Reuse freed ports.

### CRITICAL: Orchestrator-to-API authentication missing
- **Issue:** `src/api/services/orchestrator_client.py` calls orchestrator on port 7883, but there is no auth mechanism described between API and orchestrator.
- **Blocker:** If orchestrator binds to 0.0.0.0:7883, anyone on the network can create/kill containers.
- **Fix:** Shared secret header (e.g., `X-Internal-Key`) or bind orchestrator to 127.0.0.1 only.

### IMPORTANT: ID generation strategy missing
- **Issue:** `id TEXT PRIMARY KEY` with example `"kid-001"` — no generator, no uniqueness guarantee, no sequence.
- **Blocker:** Race conditions on concurrent signups.
- **Fix:** Use `INTEGER PRIMARY KEY AUTOINCREMENT` (SQLite native) or UUID4. Text IDs are cute but pointless overhead.

### IMPORTANT: Auto-pause needs a scheduler
- **Issue:** FR-11 requires "orchestrator runs daily cron check" but Pi container lifecycle is managed by Python, not cron by default.
- **Blocker:** Needs either system crontab, asyncio periodic task, or external scheduler — none specified.
- **Fix:** Cut auto-pause for POC. Admin has a "Pause" button. Revisit when you have 50+ users.

### IMPORTANT: File upload handling (avatar)
- **Issue:** FR-2 allows avatar upload. No storage path, size limit, or file type validation is specified beyond "max 5MB per file" (which is under FR-3 for agent uploads, not avatars).
- **Blocker:** Where do avatars live? `/var/abis/avatars/`? Who serves them? Nginx? FastAPI static?
- **Fix:** Cut avatars. Use a single default avatar or initials.

### IMPORTANT: SQLite WAL mode is not a silver bullet
- **Issue:** NFR-3 claims "SQLite WAL mode for concurrent reads" but the orchestrator and API may both WRITE (container status updates, user status changes).
- **Blocker:** WAL helps readers, but writers still serialize. With 8 users you may be fine, but do not assume WAL solves concurrency.
- **Fix:** Accept serialization for POC. Document known limitation.

---

## 4. Recommended Simplifications (Cut to Ship Faster)

| Feature | Current Spec | MVP Cut |
|---------|-----------|---------|
| Signup flow | 2-step (signup → profile) | Single form: email, name, age, password |
| Kid profile | Display name, avatar, interests, language | Name = display name. No avatar. No interests. |
| Restrictions config | Per-user age group, model, tokens, hours, file size, content filter | Hardcode all: 10-12 = limited, 15+ = full. No admin config UI. |
| Admin approval | Configure restrictions, then approve | One click: "Approve" creates container with defaults. |
| Content filters | strict/moderate/relaxed keyword lists | Single hardcoded system prompt. Defer. |
| Auto-pause/resume | Daily cron, 7-day inactivity | Cut. Manual pause/resume only. |
| Data archiving | `/var/abis/archives/<user_id>/`, 90-day retention | `docker rm -f` + DELETE FROM users. Defer compliance. |
| Audit logging | `admin_actions` table | Cut. Use application logs (print/logging) for POC. |
| Token usage dashboard | Daily/weekly token counts | Cut. Not built yet anyway. |
| Alert counts | Flagged messages counter | Cut. No moderation pipeline in POC. |
| Rejection reasons | Dropdown + custom note | Single text reason or just "Rejected". |
| Email notifications | In-app notification | Cut. Just show status on dashboard. |
| HTML templates | signup.html, admin.html, CSS | Two plain HTML files, zero CSS framework. Raw `<table>` for admin. |
| Container metrics | memory_mb, cpu_percent, pid | Cut columns. Use `docker ps` for now. |

**Resulting file count:** ~6 files instead of 17.
- `src/api/routes/auth.py` (signup + login)
- `src/api/routes/admin.py` (approve/reject + dashboard data)
- `src/api/middleware/auth.py` (JWT + admin check)
- `src/api/db.py` (raw SQL helpers)
- `src/api/templates/signup.html` (bare form)
- `src/api/templates/admin.html` (bare table)

---

## 5. Specific Questions for the User

1. **Do you actually need the kid to fill anything after signup?** For an MVP with 8 kids, can the signup form capture name + age + email + password, and the admin approves in one click? That collapses 3 states into 1 and saves a day.

2. **Who is the admin?** Is it you (Matthieu), or will there be multiple admins? If it is just you, skip the role system and hardcode one admin email.

3. **What does the container actually run?** The spec says "Cloud models via Ollama" — if the model is cloud-hosted, does the kid's container just run a FastAPI/WebSocket agent that proxies to the cloud? Clarify container contents so the approval→create flow is realistic.

4. **Is PDPO/GDPR compliance actually required for a Pi-hosted POC with 8 kids?** If this is a private demo for friends/family, data retention policies and archiving are theater. If it is a real pilot with real children, you need more than a spec paragraph — you need legal review.

5. **Can we defer the admin dashboard UI and use a CLI or `sqlite3` shell for approvals?** A CLI tool (`python -m src.cli.approve_user --email kid@example.com`) ships in 30 minutes. A web dashboard with tables, filters, sorting, and buttons ships in 2 days.

---

## Summary Verdict

**This spec is not a 2-3 day MVP. It is a 1-2 week production feature set disguised as a POC.**

The core user story — "kid signs up, admin clicks approve, container spins up, kid chats" — requires about 6 endpoints, 2 HTML pages, and a single `docker run` call. This spec layers on state machines, audit logs, content filters, auto-schedulers, data archiving, and metric tracking that do not materially help validate the core hypothesis.

**Recommendation:** Rewrite as "Admin Approval Workflow — MVP Cut" with the simplified table above. Target: 2 days max. Ship the core loop. Everything else goes to a Phase 2 backlog.
