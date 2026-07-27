# ABIS User Agents Architecture v2.0

> Ticket: #1 [map] Define system architecture for ABIS User Agents
> Date: 2026-07-27
> Author: Hermes (Chief of Staff)
> Status: Architecture defined after grilling session with Matthieu

---

## 1. What We Are Building (Elevator Pitch)

ABIS Academy gives every student their own persistent AI tutor agent (ATA) in an isolated container. The student chats with their agent through a web browser — on phone, iPad, or computer. An admin approves students before they gain access. A Chief of Staff (Hermes, outside all containers) oversees all agent activity, monitors token usage and traces, and detects suspicious or dangerous conversations for child safety.

The container is a **progressive environment**: it starts as a friendly chat tutor for younger kids (ages 10-12), then unlocks terminal access, code execution, and advanced tools as the student grows older (15+). The student never loses their files or conversation history — everything persists on network-attached storage.

---

## 2. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL WORLD                                 │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    STUDENT (Kid)                                       │  │
│  │  Phone / iPad / Computer — any web browser                             │  │
│  │  Chat panel (left) + File browser (right)                            │  │
│  └──────────────────────┬────────────────────────────────────────────────┘  │
│                         │ HTTPS                                               │
│                         ▼                                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │              ABIS PORTAL — Cloudflare Pages                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │  │
│  │  │  Public Pages│  │ Admin Panel  │  │    Login / Signup      │   │  │
│  │  │  - Landing   │  │ - Approvals  │  │  - Email + password    │   │  │
│  │  │  - Pricing   │  │ - User List  │  │  - OAuth (Phase 2)     │   │  │
│  │  │  - About     │  │ - Analytics  │  │  - Classroom code (P2) │   │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘   │  │
│  └───────────────────────┬───────────────────────────────────────────────┘  │
│                          │ WebSocket (real-time chat)                       │
│                          │ REST API (file browser, status)                  │
│                          ▼                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                           LOCAL NETWORK (Home/School)                       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      pi-agent (Raspberry Pi 5)                      │   │
│  │                         16GB RAM                                  │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                 ABIS API (Flask/FastAPI)                     │   │   │
│  │  │  Port: 7582 (or similar, not conflicting)                    │   │   │
│  │  │  Responsibilities:                                         │   │   │
│  │  │  - Auth (signup, login, JWT)                               │   │   │
│  │  │  - Admin approval endpoints                                │   │   │
│  │  │  - WebSocket proxy: student ↔ container agent              │   │   │
│  │  │  - File proxy: serve files from pi-nas                     │   │   │
│  │  │  - Container status queries                              │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                              │                                      │   │
│  │                              ▼                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              ORCHESTRATOR SERVICE (Python daemon)          │   │   │
│  │  │  Port: 7583 (localhost only)                               │   │   │
│  │  │  Responsibilities:                                         │   │   │
│  │  │  - Safety scanning (keyword check on ALL traffic)          │   │   │
│  │  │  - Forward chat messages to appropriate container          │   │   │
│  │  │  - Monitor token usage via LiteLLM traces                  │   │   │
│  │  │  - Container lifecycle (create, start, stop, destroy)      │   │   │
│  │  │  - Auto-pause inactive containers (7-day timeout)          │   │   │
│  │  │  - SQLite state DB on local SSD                          │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                              │                                      │   │
│  │                              ▼                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │           USER CONTAINERS (isolated, always running)       │   │   │
│  │  │                                                             │   │   │
│  │  │  ┌─────────────────────┐    ┌─────────────────────┐         │   │   │
│  │  │  │ Container: kid-001  │    │ Container: kid-002  │  ...   │   │   │
│  │  │  │                     │    │                     │        │   │   │
│  │  │  │ ┌───────────────┐ │    │ ┌───────────────┐   │        │   │   │
│  │  │  │ │ ATA Agent     │ │    │ │ ATA Agent     │   │        │   │   │
│  │  │  │ │ (FastAPI +    │ │    │ │ (FastAPI +    │   │        │   │   │
│  │  │  │ │  WebSocket)   │ │    │ │  WebSocket)   │   │        │   │   │
│  │  │  │ └───────┬───────┘ │    │ └───────┬───────┘   │        │   │   │
│  │  │  │         │         │    │         │             │        │   │   │
│  │  │  │ ┌───────▼───────┐ │    │ ┌───────▼───────┐   │        │   │   │
│  │  │  │ │ User Data Vol │ │    │ │ User Data Vol │   │        │   │   │
│  │  │  │ │ (NAS mount)   │ │    │ │ (NAS mount)   │   │        │   │   │
│  │  │  │ │ ~/workspace/  │ │    │ │ ~/workspace/  │   │        │   │   │
│  │  │  │ │ ~/.hermes/    │ │    │ │ ~/.hermes/    │   │        │   │   │
│  │  │  │ │ chat_history/ │ │    │ │ chat_history/ │   │        │   │   │
│  │  │  │ │ (persistent)  │ │    │ │ (persistent)  │   │        │   │   │
│  │  │  │ └───────────────┘ │    │ └───────────────┘   │        │   │   │
│  │  │  └─────────────────────┘    └─────────────────────┘        │   │   │
│  │  │                                                             │   │   │
│  │  │  NO NETWORK BETWEEN CONTAINERS. Pure silos.               │   │   │
│  │  │  Each container reaches Ollama via host network.            │   │   │
│  │  │  Containers cannot see each other's data.                   │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              SHARED SERVICES (on pi-agent host)              │   │   │
│  │  │                                                             │   │   │
│  │  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │   │   │
│  │  │  │ Ollama      │  │ LiteLLM      │  │ OpenClaw Gateway    │  │   │   │
│  │  │  │ 127.0.0.1   │  │ 127.0.0.1    │  │ 127.0.0.1           │  │   │   │
│  │  │  │ :11434      │  │ :11435       │  │ :18789 (optional)   │  │   │   │
│  │  │  └─────────────┘  └──────────────┘  └─────────────────────┘  │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      pi-nas (Raspberry Pi NAS)                      │   │
│  │                                                                     │   │
│  │  /var/nfs/abis/                                                     │   │
│  │  ├── volumes/                                                        │   │
│  │  │   ├── kid-001/          # Persistent user data                    │   │
│  │  │   │   ├── workspace/    # Kid's files                            │   │
│  │  │   │   ├── chat_history/ # SQLite conversation DB                 │   │
│  │  │   │   └── .hermes/      # Hermes skills, memory, config          │   │
│  │  │   ├── kid-002/                                                     │   │
│  │  │   └── ...                                                          │   │
│  │  ├── templates/         # Base container images (read-only)         │   │
│  │  └── backups/           # Daily snapshots (rsync)                  │   │
│  │                                                                     │   │
│  │  Protocol: NFS (initial). Samba can be added per-admin request.    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 ABIS Portal (Cloudflare Pages)
- **Deployment:** Cloudflare Pages (same CDN as existing `abishk-website`)
- **Technology:** Next.js + Tailwind (reused from existing website)
- **Pages:**
  - **Public:** Landing, signup, pricing, about
  - **User Dashboard:** Chat panel (left), file browser (right), settings
  - **Admin Panel:** User approvals, user list with metadata, container controls, analytics
- **Auth:** Email + password (POC). OAuth, magic links, classroom codes deferred.
- **Real-time:** WebSocket connection from browser to pi-agent API (via Cloudflare Tunnel or direct IP)

### 3.2 ABIS API (pi-agent, Flask/FastAPI)
- **Port:** 7582
- **Responsibilities:**
  - HTTP: signup, login, JWT validation, admin endpoints
  - WebSocket: proxy student chat to container's ATA agent
  - File proxy: serve/download files from pi-nas volumes
  - Container status: query orchestrator for running/stopped containers
- **No state:** All state lives in orchestrator SQLite or pi-nas

### 3.3 Orchestrator Service (pi-agent, Python daemon)
- **Port:** 7583 (localhost only, not exposed externally)
- **Responsibilities:**
  - **Safety scanning:** Keyword-based scan on ALL messages (kid → agent AND agent → kid). Logs flagged conversations for admin review.
  - **Traffic forwarding:** Route WebSocket messages to correct container
  - **Token monitoring:** Collect LiteLLM traces, log per-user token usage
  - **Container lifecycle:** create, start, stop, destroy, pause, resume
  - **Auto-pause:** Stop container after 7 days of inactivity. Restart on next login.
  - **Permission sync:** Write `/etc/ata/permissions.json` (read-only bind mount) when admin changes permissions
- **Database:** SQLite on pi-agent local SSD (`/var/abis/orchestrator.db`)

### 3.4 ATA Agent (inside each container)
- **Technology:** FastAPI + WebSocket server (Python, ~200-500 lines)
- **Port:** 7584 (inside container, forwarded from host)
- **DNA from Hermes:**
  - Same Ollama client code (OpenAI-compatible Python client)
  - Same tool execution logic (subprocess, file read/write)
  - Same skill loading (`~/.hermes/skills/`)
  - Same memory/conversation persistence (SQLite in user volume)
- **Web-native differences:**
  - WebSocket streaming instead of terminal rendering
  - JSON tool results instead of ANSI terminal output
  - Permission-gated tool execution (reads `/etc/ata/permissions.json`)
- **Capabilities (POC):**
  - Chat with streaming responses
  - Create, read, edit files (any type)
  - Load and use skills (from `~/.hermes/skills/`)
  - Conversation history persistence
- **Deferred (Phase 2):**
  - Web search
  - Code execution / terminal
  - Browser automation
  - Image generation
  - Cron jobs

### 3.5 User Data Volume (pi-nas, NFS)
Each kid gets a persistent directory on pi-nas, bind-mounted into their container:

```
/var/nfs/abis/volumes/kid-001/
├── workspace/              # Kid's files (any type)
│   ├── notes.md
│   ├── script.py
│   └── project/
├── chat_history/
│   └── conversations.sqlite  # Full conversation log
├── .hermes/
│   ├── skills/              # Custom skills the kid downloads
│   ├── memory/              # Agent memory persistence
│   └── config.yaml          # Agent preferences
└── .openclaw/               # For Phase 2 (if kid unlocks OpenClaw)
```

### 3.6 Container Technology: systemd-nspawn
**Why systemd-nspawn over Docker/LXC:**

| Criteria | systemd-nspawn | Docker | LXC |
|----------|---------------|--------|-----|
| Overhead | Minimal — no daemon | Medium — dockerd | Low — lxd |
| Boot time | Fast (seconds) | Medium (tens of sec) | Fast |
| Native on Pi | Yes (systemd built-in) | Needs install | Needs install |
| Rootless | Yes (`--private-users`) | Complex | Yes |
| Bind mount | Trivial (`--bind`) | Volume mgmt | Medium |
| Resource limits | Native cgroups (systemd) | Docker handles | lxc handles |
| Portability to Mac | **No** (Linux only) | **Yes** (Docker Desktop) | **No** |

**Critical finding:** systemd-nspawn is Linux-only. When we migrate to Mac Mini M5s, we MUST switch to Docker or Podman. **This is a Phase 2 migration.** For POC on Pi: systemd-nspawn is fine.

**Container creation (POC):**
```bash
sudo systemd-nspawn \
  -D /var/abis/containers/kid-001 \
  --private-users=pick \
  --bind=/var/nfs/abis/volumes/kid-001:/home/kid \
  --bind=/var/abis/permissions/kid-001.json:/etc/ata/permissions.json:ro \
  --property=MemoryLimit=1G \
  --property=CPUQuota=25% \
  --network-veth \
  --boot
```

### 3.7 Permission Gating
Each container has a read-only permissions file (bind-mounted from host). The ATA agent checks this before executing any tool:

```json
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
```

**Admin changes permissions → orchestrator updates JSON → container restart required.** Kid cannot edit their own permissions (read-only bind mount from host).

### 3.8 Progressive Container Evolution
The same container image supports all stages. Only the permissions file changes:

| Stage | Age | Permissions | UI Features |
|-------|-----|-------------|-------------|
| **Base (ATA)** | 10-12 | chat, file_management | Chat + file browser |
| **Advanced** | 15+ | +web_search, +code_execution | Chat + file browser + terminal tab |
| **Full (Hermes)** | Graduate | +terminal_commands, +openclaw | Chat + terminal + full Hermes TUI |

No data migration needed. The kid's files and history stay in the same NAS volume.

---

## 4. Communication Flow: Kid Chat

```
Kid's Browser (Cloudflare Pages)
  │
  │ WebSocket: "Hello, can you help me with Python loops?"
  ▼
Cloudflare Tunnel (or direct IP to pi-agent)
  │
  ▼
ABIS API (pi-agent:7582)
  │
  │ 1. Validate JWT token
  │ 2. Identify kid-001
  │ 3. Forward message to orchestrator
  ▼
Orchestrator Service (pi-agent:7583)
  │
  │ 1. Safety scan message (keyword check)
  │ 2. If flagged: log alert, notify admin, optionally block
  │ 3. Forward to kid-001's container
  ▼
Container kid-001 (systemd-nspawn)
  │
  │ ATA Agent receives message
  │ Loads conversation history from NAS volume
  │ Calls Ollama (via LiteLLM on host:11435)
  ▼
LiteLLM (pi-agent:11435)
  │
  │ Routes to Ollama cloud model
  │ Emits trace for monitoring
  ▼
Ollama Cloud (Internet)
  │
  │ Returns streaming response
  ▼
Container kid-001
  │
  │ ATA Agent receives token chunks
  │ Streams back through WebSocket
  ▼
Orchestrator Service
  │
  │ Safety scan response (keyword check)
  ▼
ABIS API
  │
  │ Forwards streaming response to kid's browser
  ▼
Kid's Browser
  │
  │ Sees streaming text appear in chat panel
```

**Note:** The orchestrator sits in the middle of ALL traffic. This is intentional — it enables safety monitoring and token tracking for every message, in both directions.

---

## 5. Port Allocation

| Port | Service | Host | Notes |
|------|---------|------|-------|
| 11434 | Ollama | pi-agent | Native Ollama API |
| 11435 | LiteLLM | pi-agent | Model proxy + tracing |
| 18789 | OpenClaw Gateway | pi-agent | Optional bridge for advanced users |
| 7582 | ABIS API | pi-agent | External-facing HTTP + WebSocket |
| 7583 | Orchestrator | pi-agent | Localhost only — internal |
| 7584+ | ATA Agents | containers | Dynamic per container (7584, 7585, ...) |
| 2049 | NFS | pi-nas | NFS server for user volumes |

**Container ports are dynamic.** The orchestrator assigns a unique host port to each container's ATA agent (starting at 7584). The ABIS API knows which port maps to which kid.

---

## 6. Security Boundaries

### 6.1 User Isolation
- Each container: `--private-users` (UID mapping from host to container)
- Host files owned by root; container sees them as owned by kid's UID
- No root access inside container (drops to unprivileged user after boot)
- Containers cannot see each other's volumes (separate bind mounts)

### 6.2 Resource Limits (per container)
- **Memory:** 1GB (`--property=MemoryLimit=1G`)
- **CPU:** 25% (`--property=CPUQuota=25%`)
- **Disk:** 5GB quota on pi-nas (enforced via NAS quotas or separate partitions)

### 6.3 Network Isolation
- `--network-veth` gives each container virtual ethernet
- No bridge between containers (iptables DROP between veth interfaces)
- Containers can reach Ollama (11434/11435) on host
- Containers CANNOT reach other containers or the internet directly

### 6.4 Data Privacy
- User volumes on pi-nas encrypted at rest (optional: LUKS per volume)
- Orchestrator sees all traffic (by design — child safety monitoring)
- Admin dashboard shows per-user activity, token usage, flagged messages
- Audit log in SQLite: every orchestrator action logged with timestamp

### 6.5 Permission Tamper-Proofing
- `/etc/ata/permissions.json` is bind-mounted **read-only** from host
- Kid has no write access to this file
- Only the orchestrator (running as root on host) can modify it
- Container restart required to apply new permissions

---

## 7. Safety Architecture

### 7.1 Keyword Scanning (Phase 1 — POC)
- Orchestrator maintains a keyword list (`/var/abis/safety/keywords.txt`)
- Every message (kid → agent, agent → kid) is checked against the list
- Match → log to SQLite, increment alert counter, notify admin dashboard
- Optional: block message delivery and show kid a generic error

### 7.2 Intent Classification (Phase 2 — Deferred)
- Use a small model (or Ollama itself) to classify conversation risk level
- More nuanced than keywords: "I'm feeling sad" vs "I want to hurt myself"
- Flagged conversations enter human review queue

### 7.3 Admin Dashboard Alerts
- Per-user alert counter (number of flagged messages)
- Alert severity levels (info, warning, critical)
- One-click to view full conversation context
- One-click to pause/unpause user container

---

## 8. API Schema

### 8.1 Container Lifecycle (Orchestrator Internal)
```
POST /containers
  Body: {"user_id": "kid-001", "template": "ata-base"}
  Response: {"container_id": "kid-001", "status": "creating", "host_port": 7584}

GET /containers/:id
  Response: {"id": "kid-001", "status": "running|stopped|paused",
             "pid": 12345, "memory_mb": 256, "cpu_percent": 12,
             "last_active": "2026-07-27T13:45:00Z", "alerts": 0}

POST /containers/:id/start
POST /containers/:id/stop
POST /containers/:id/pause       # Manual admin pause
POST /containers/:id/resume
DELETE /containers/:id
```

### 8.2 Permissions Management (Admin)
```
GET /admin/users/:id/permissions
  Response: {"chat": true, "file_management": true, ...}

PUT /admin/users/:id/permissions
  Body: {"web_search": true, "code_execution": false}
  Response: {"status": "updated", "requires_restart": true}
```

### 8.3 Safety Monitoring (Admin)
```
GET /admin/alerts
  Response: [{"user_id": "kid-001", "severity": "warning",
              "message_preview": "...", "timestamp": "..."}]

GET /admin/users/:id/conversations
  Response: {"conversations": [...], "token_usage": 12345, "alert_count": 2}
```

---

## 9. Hardware and Scaling Roadmap

### Phase 0: POC (Now — 1-2 months)
- **pi-agent:** Raspberry Pi 5, 16GB RAM, SSD boot
- **pi-nas:** Raspberry Pi (any model), USB HDD/SSD, NFS server
- **Max users:** 8 concurrent (8 × 1GB = 8GB RAM + 3GB host = 11GB / 16GB)
- **Test users:** You + 13yo kid + 11yo nephew

### Phase 1: Classroom (Future — 3-6 months)
- **Same hardware** but optimize: smaller containers, shared read-only layers
- **Max users:** 20-30 (with auto-pause and staggered class schedules)
- **Add:** OAuth login, classroom codes, teacher dashboards

### Phase 2: Scale (Future — 6-12 months)
- **Hardware upgrade:** 2x Mac Mini M5 (or equivalent) with 32-64GB RAM each
- **Container migration:** systemd-nspawn → Docker/Podman (Linux VMs on Mac or cloud)
- **Max users:** 100+ (load balanced across hosts)
- **Add:** Multi-school support, billing tiers, advanced monitoring

---

## 10. Acceptance Criteria Check

| Criterion | How Architecture Satisfies |
|-----------|---------------------------|
| Kid chats with own agent via web browser | Cloudflare Pages portal → WebSocket → ABIS API → container ATA agent |
| Agent data persists across reconnects | NAS-mounted volumes survive container restart |
| Admin approves/rejects from UI | ABIS API admin endpoints + SQLite state |
| Chief of Staff oversees all containers | Orchestrator monitors ALL traffic, LiteLLM traces, admin dashboard |
| Containers are pure silos | No network bridge, private users, separate NAS volumes |
| Safety scanning on all traffic | Orchestrator keyword scan on every message in both directions |
| Progressive capabilities | Permission JSON file controls available tools per user |
| Auto-pause inactive containers | Orchestrator 7-day timeout + manual admin pause |
| Resource limits per container | systemd cgroups: 1GB RAM, 25% CPU, 5GB disk |
| Lightweight on Pi 5 | 8 containers × 1GB = 8GB. Total ~11GB/16GB. Within budget. |

---

## 11. Open Questions for Research Phase (#2)

1. Can systemd-nspawn on Pi 5 boot a container with FastAPI + WebSocket in under 5 seconds?
2. Does NFS from pi-nas to pi-agent perform well enough for real-time chat + file I/O?
3. What's the actual RAM footprint of a minimal FastAPI + WebSocket server?
4. Can Cloudflare Tunnel expose WebSocket from Pi to internet reliably?
5. What's the SQLite schema for users, containers, permissions, conversations, alerts?
6. What base image for the container? Debian minimal? Alpine? Python slim?
7. Can we build a single container image with both ATA (FastAPI) and Hermes (TUI) installed, with only permissions controlling which is active?

---

## 12. Phase 2 Doors (Deferred)

- Intent-based safety classification (B + D from Q5)
- OAuth, magic links, classroom code authentication
- Model picker per kid (kid chooses from admin-approved list)
- Terminal tab for older kids (15+)
- OpenClaw bridge inside container
- Code execution / web search / browser automation
- Image generation / cron jobs
- Docker/Podman migration for Mac Mini M5s
- Multi-school support
- Billing and quotas
- Real-time collaboration (multiple kids on same project)

---

## 13. Changes From v1.0

| v1.0 (Initial) | v2.0 (After Grilling) | Why |
|----------------|----------------------|-----|
| Filesystem IPC (inbox/outbox) | **WebSocket streaming** | Kids need real-time chat, not batch task dispatch |
| Orchestrator dispatches tasks | **Orchestrator monitors + safety-scans** all traffic | Kid talks directly to agent; orchestrator oversees |
| Hermes TUI inside container | **ATA (FastAPI + WebSocket)** — kid-friendly web UI | Terminal is wrong for kids ages 10-12 |
| Single container type | **Progressive container** — same image, permissions unlock tools | No data migration, seamless growth |
| Pi-local storage | **pi-nas via NFS** for persistent user data | Separate storage from compute |
| No safety scanning | **Orchestrator-level keyword scanning** mandatory from day 1 | Child safety is non-negotiable |
| No permission system | **Permission-gated tool execution** via read-only JSON | Admin controls what each kid can do |
| Always running or immediate stop | **Always running + auto-pause after 7 days + manual pause** | Feels persistent but manages resources |
| No mention of future scaling | **Mac Mini M5 roadmap** with Docker migration | systemd-nspawn is Linux-only |

---

*Architecture v2.0 defined. Ready for research phase (#2) or prototype phase (#4).*
