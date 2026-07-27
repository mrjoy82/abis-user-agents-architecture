# Grilling Session #2: Architecture Stress-Test

**Date:** 2026-07-27
**Ticket:** #3 [grilling] Stress-test user-agent architecture for failure modes
**Status:** COMPLETE

---

## Stress-Test Results: 8 Gaps Found and Resolved

### Gap 1: Container Runtime — systemd-nspawn vs Docker
**Finding:** systemd-nspawn installed successfully, but debootstrap failed to create a working Debian rootfs (tar extraction error during package unpacking). Incomplete rootfs = unusable container.
**Decision:** Use **Docker for POC**. systemd-nspawn deferred to Phase 2 when we have time to debug debootstrap or use a pre-built rootfs.
**Locked by:** user.

### Gap 2: Pi 5 RAM Specification
**Finding:** Architecture doc says "16GB RAM" but user had earlier mentioned 8GB. Ambiguity could cause incorrect resource budgeting.
**Decision:**
- **pi-agent (compute):** 16GB RAM
- **pi-nas (storage):** 8GB RAM
**Locked by:** user.

### Gap 3: Mac Mini "M5" Does Not Exist
**Finding:** Apple has not announced an M5 chip. Current Mac Mini ships with M4 (late 2024).
**Decision:** Architecture refers to "latest Apple Silicon Mac Mini available at Phase 2 deployment time." User will procure whatever is current (M5 or later) when Phase 2 arrives.
**Locked by:** user.

### Gap 4: Port 7582 Already in Use
**Finding:** A Flask server (PID 761432) is already listening on port 7582. Architecture assigns 7582 to ABIS API.
**Decision:** Shift all ports. New anchor: **7882** for ABIS API.

**Updated port allocation:**
```
7882 — ABIS API (Flask/FastAPI on host)
7883 — Orchestrator service (localhost only)
7884 — ATA Agent: kid-001
7885 — ATA Agent: kid-002
7886 — ATA Agent: kid-003
7887 — ATA Agent: kid-004
7888 — ATA Agent: kid-005
7889 — ATA Agent: kid-006
7890 — ATA Agent: kid-007
7891 — ATA Agent: kid-008
```
**Locked by:** user.

### Gap 5: Model Type (Local vs Cloud)
**Finding:** Architecture says `gemma4:31b-cloud` but doesn't clarify whether inference runs locally on Pi 5 or via cloud.
**Decision:** **Cloud model.** The `-cloud` suffix means Ollama routes the request to a cloud-hosted model. Pi 5 does NOT run a 31B parameter model locally (would need ~20-25GB RAM). The ATA agent calls Ollama's cloud model endpoint, same as Hermes does today.
**Locked by:** user.

### Gap 6: Hermes DNA Reuse Scope
**Finding:** Architecture says "same Ollama client code, same tool execution logic, same skill loading" but Hermes is a terminal TUI with very different architecture.
**Decision:**
- **Port:** Ollama client (HTTP API calls), skill loader (YAML parsing), memory/conversation persistence (SQLite schema)
- **Partially port:** File tools (read/write). Terminal tools deferred to Phase 2.
- **Discard:** Terminal rendering, ANSI output, keyboard event loop
- **New:** WebSocket event loop, JSON tool results, permission gating
**Locked by:** user.

### Gap 7: Auto-Pause Trigger Definition
**Finding:** Architecture says "auto-pause after 7 days of inactivity" but doesn't define what counts as "activity."
**Decision:** Track **last WebSocket message timestamp per kid**. If no chat message sent in 7 days, orchestrator pauses the container. Other activity (file browsing, settings changes) does NOT reset the timer — chat is the primary signal.
**States:** `running` → `paused` (after 7d idle) → `running` (on next login attempt, orchestrator auto-resumes).
**Locked by:** user. Recommendation A accepted.

### Gap 8: Hermes TUI for 15+ Stage
**Finding:** We rejected terminal-in-browser during initial grilling as "inappropriate for children and impossible to safety-monitor." But architecture still lists "Full (Hermes)" as the final progressive stage.
**Decision:** **Keep the stage** but redefine it. For 15+ advanced users, Hermes is NOT integrated into the ATA web UI. Instead, the kid gets a **separate window/tab** (or SSH session) with a terminal running Hermes TUI. The ATA and Hermes run as separate processes — ATA in the browser, Hermes in a terminal window. Safety monitoring applies to both.
**Locked by:** user.

---

## Failure Mode Matrix

| Failure Scenario | Likelihood | Impact | Mitigation | Locked Decision |
|-----------------|------------|--------|------------|-----------------|
| debootstrap fails | **CONFIRMED** | Cannot create systemd-nspawn container | Use Docker for POC | #1 |
| Port 7582 conflict | **CONFIRMED** | ABIS API cannot start | Shift to 7882 | #4 |
| Pi 5 runs out of RAM | Medium | Container OOM killed | 1GB per container, auto-pause after 7d | #7 |
| Pi 5 CPU oversubscribed | **CONFIRMED** | 4 cores / 8 kids = throttling | Manageable for 1-3 active kids; Mac Mini for scale | #3 |
| Cloud model unavailable | Low | ATA agent cannot chat | Fallback to other cloud models (qwen, glm) | #5 |
| NFS not configured on pi-nas | **CONFIRMED** | No network persistence | Local bind mounts as temporary stand-in | #2 (from RESEARCH) |
| Kid edits own permissions.json | Low (theoretical) | Bypasses safety controls | Read-only bind mount from host | ARCHITECTURE v2.0 |
| Safety keyword false positive | Medium | Kid's message blocked incorrectly | Admin review + allowlist per kid | ARCHITECTURE v2.0 |
| Container crash loses conversation | Low | Kid loses unsaved chat | SQLite persistence on NAS/local mount | ARCHITECTURE v2.0 |

---

## Updated Acceptance Criteria for Ticket #4 (Prototype)

- [ ] Create base Docker image for ATA agent (Python 3.11 + FastAPI + WebSocket)
- [ ] Build ATA agent: chat endpoint with streaming via WebSocket
- [ ] Build ATA agent: file read/write endpoints
- [ ] Build ATA agent: skill loader (reuse Hermes skill YAML format)
- [ ] Build ATA agent: conversation persistence (SQLite in user volume)
- [ ] Build orchestrator: create/start/stop/pause/resume containers via Docker
- [ ] Build orchestrator: safety keyword scanning on all messages
- [ ] Build orchestrator: WebSocket proxy from ABIS API to ATA agent
- [ ] Build ABIS API: user signup, JWT auth, admin endpoints
- [ ] Build ABIS API: WebSocket endpoint for kid → orchestrator → ATA agent
- [ ] Test end-to-end: kid browser → ABIS API (7882) → orchestrator (7883) → ATA container (7884) → Ollama cloud
- [ ] Test persistence: container restart, user files and history survive
- [ ] Test safety: flagged message triggers alert in admin dashboard

---

## Decisions by Ticket

| Ticket | Status | Key Decisions Locked |
|--------|--------|---------------------|
| #1 [map] | CLOSED | ATA agent, systemd-nspawn→Docker, NFS persistence, split-screen UI |
| #2 [research] | CLOSED | Docker for POC, local bind mounts until NFS ready, SSE rejected |
| #3 [grilling] | CLOSED (this file) | Docker fallback, port shift to 7882, cloud model, auto-pause by chat idle |
| #4 [prototype] | OPEN | Next step: build first ATA container |
| #5-8 | OPEN | Depend on #4 |

---

*All branches resolved. Proceed to prototype (#4).*
