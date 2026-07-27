# ABIS User Agents Architecture v1.0

> Ticket: #1 [map] Define system architecture for ABIS User Agents
> Date: 2026-07-27
> Author: Hermes (Chief of Staff)

---

## 1. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL WORLD                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────────┐  │
│  │  New User   │  │   Admin     │  │      Chief of Staff (Hermes)        │  │
│  │  (Browser)  │  │  (Browser)  │  │         (You, outside)              │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────────┬──────────────────────┘  │
│         │                │                        │                         │
└─────────┼────────────────┼────────────────────────┼─────────────────────────┘
          │                │                        │
          ▼                ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HOST (Raspberry Pi)                               │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     ABIS Portal (Next.js)                           │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │  Public Pages│  │ Admin Panel  │  │    User Dashboard      │  │   │
│  │  │  - Landing   │  │ - Approvals  │  │  - Agent Status        │  │   │
│  │  │  - Signup    │  │ - User List  │  │  - Task Input          │  │   │
│  │  │  - Pricing   │  │ - Analytics  │  │  - File Browser        │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              ABIS API (Flask / FastAPI on port 7582)              │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │ /auth    │  │ /users   │  │ /agents  │  │ /admin           │  │   │
│  │  │ /signup  │  │ /:id     │  │ /:id/run │  │ /approvals       │  │   │
│  │  │ /login   │  │ /:id/data│  │ /:id/status│ │ /users           │  │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Orchestrator Service (Python, persistent)              │   │
│  │                                                                     │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │  Task Queue │  │ Container    │  │   SQLite State DB       │  │   │
│  │  │  (per user) │  │ Lifecycle    │  │  - users table          │  │   │
│  │  │             │  │  Manager     │  │  - containers table     │  │   │
│  │  │  ┌───────┐  │  │  (spawn,   │  │  - tasks table          │  │   │
│  │  │  │user-a │──┼──┼─▶ kill,     │  │  - sessions table       │  │   │
│  │  │  │user-b │──┼──┼─▶ restart)  │  │                         │  │   │
│  │  │  └───────┘  │  │             │  │                         │  │   │
│  │  └─────────────┘  └──────┬──────┘  └──────────────────────────┘  │   │
│  └───────────────────────────┼───────────────────────────────────────┘   │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    USER CONTAINERS (isolated)                       │   │
│  │                                                                     │   │
│  │  ┌─────────────────────┐    ┌─────────────────────┐               │   │
│  │  │ Container: user-001 │    │ Container: user-002 │  ... (N users)│   │
│  │  │                     │    │                     │               │   │
│  │  │ ┌───────────────┐ │    │ ┌───────────────┐   │               │   │
│  │  │ │ Hermes Agent  │ │    │ │ Hermes Agent  │   │               │   │
│  │  │ │ (Python proc) │ │    │ │ (Python proc) │   │               │   │
│  │  │ └───────┬───────┘ │    │ └───────┬───────┘   │               │   │
│  │  │         │         │    │         │             │               │   │
│  │  │ ┌───────▼───────┐ │    │ ┌───────▼───────┐   │               │   │
│  │  │ │ User Data Vol │ │    │ │ User Data Vol │   │               │   │
│  │  │ │ ~/workspace/  │ │    │ │ ~/workspace/  │   │               │   │
│  │  │ │ ~/.hermes/     │ │    │ │ ~/.hermes/    │   │               │   │
│  │  │ │ ~/.openclaw/   │ │    │ │ ~/.openclaw/  │   │               │   │
│  │  │ │ (persistent)   │ │    │ │ (persistent)  │   │               │   │
│  │  │ └───────────────┘ │    │ └───────────────┘   │               │   │
│  │  │                     │    │                     │               │   │
│  │  │ ┌───────────────┐ │    │ ┌───────────────┐   │               │   │
│  │  │ │ Task Inbox    │ │    │ │ Task Inbox    │   │               │   │
│  │  │ │ /shared/in/   │ │    │ │ /shared/in/   │   │               │   │
│  │  │ └───────────────┘ │    │ └───────────────┘   │               │   │
│  │  │ ┌───────────────┐ │    │ ┌───────────────┐   │               │   │
│  │  │ │ Result Outbox │ │    │ │ Result Outbox │   │               │   │
│  │  │ │ /shared/out/  │ │    │ │ /shared/out/  │   │               │   │
│  │  │ └───────────────┘ │    │ └───────────────┘   │               │   │
│  │  └─────────────────────┘    └─────────────────────┘               │   │
│  │                                                                     │   │
│  │  NO NETWORK BETWEEN CONTAINERS. Pure silos.                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    SHARED SERVICES (read-only)                       │   │
│  │                                                                     │   │
│  │  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────────┐ │   │
│  │  │ Ollama      │  │ LiteLLM      │  │ OpenClaw Gateway (optional)  │ │   │
│  │  │ 127.0.0.1   │  │ 127.0.0.1    │  │ 127.0.0.1                    │ │   │
│  │  │ :11434      │  │ :11435       │  │ :18789 (for OpenClaw bridge)│ │   │
│  │  └─────────────┘  └──────────────┘  └──────────────────────────────┘ │   │
│  │                                                                     │   │
│  │  Containers access these via host network (or proxy if needed).    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Breakdown

### 2.1 ABIS Portal (Next.js)
- **Public pages:** Landing, signup, pricing
- **User dashboard:** Agent status, task input, file browser, session history
- **Admin panel:** User approvals, user list, analytics, container controls
- **Deployment:** Cloudflare Pages (existing `abishk-website`) or Vercel
- **Auth:** JWT tokens, stored in SQLite on host

### 2.2 ABIS API (Flask/FastAPI)
- **Port:** 7582 (or similar, not conflicting with 11434/11435/18789)
- **Responsibilities:**
  - User signup/login
  - Admin approval endpoints
  - Agent task dispatch (forward to orchestrator)
  - File retrieval (proxy from container volumes)
  - Container status queries
- **State:** SQLite database on host (`/home/matthieu/.abis/db.sqlite`)

### 2.3 Orchestrator Service (Python, persistent daemon)
- **Location:** Runs on host, outside containers
- **Responsibilities:**
  - Receive tasks from API (from you, the Chief of Staff)
  - Write tasks to container inboxes (`/var/abis/containers/{user-id}/in/`)
  - Poll container outboxes for results
  - Manage container lifecycle (create, start, stop, destroy)
  - Maintain state in SQLite
- **Why outside containers:** You (Chief of Staff) need to see and control all containers

### 2.4 User Containers (isolated)
- **Technology:** systemd-nspawn (recommended — see Section 3)
- **Contents:**
  - Hermes agent process (Python venv, `.local/bin/hermes`)
  - User data volume (bind-mounted from host, persistent)
  - Task inbox (`/shared/in/` — bind-mounted read-write)
  - Result outbox (`/shared/out/` — bind-mounted read-write)
- **Network:** Host-only (access to Ollama 11434, no container-to-container)
- **Resource limits:** CPU 25%, Memory 512MB per container (cgroups)

### 2.5 Shared Services
- **Ollama (11434):** Native Ollama, direct connection
- **LiteLLM (11435):** Optional — if containers need model routing
- **OpenClaw (18789):** Optional — for OpenClaw bridge mode if needed

---

## 3. Technology Choices

### 3.1 Container Technology: systemd-nspawn

**Why systemd-nspawn over Docker/LXC:**
| Criteria | systemd-nspawn | Docker | LXC |
|----------|---------------|--------|-----|
| Overhead | Minimal — no daemon | Medium — dockerd | Low — lxd |
| Boot time | Fast (seconds) | Medium (tens of sec) | Fast |
| Native on Pi | Yes (systemd built-in) | Needs install | Needs install |
| Rootless support | Yes (--private-users) | Complex | Yes |
| Bind mount ease | Trivial (-D flag) | Volume mgmt | Medium |
| cgroup support | Native (systemd) | Docker handles | lxc handles |
| Learning curve | Low | Medium | Medium |

**Recommendation:** systemd-nspawn with `--private-users` for rootless isolation, `--bind` for persistent volumes, and systemd slice for resource limits.

**Container creation command (prototype):**
```bash
sudo systemd-nspawn \
  -D /var/abis/containers/user-001 \
  --private-users=pick \
  --bind=/var/abis/volumes/user-001:/home/user \
  --bind=/var/abis/tasks/user-001/in:/shared/in:rw \
  --bind=/var/abis/tasks/user-001/out:/shared/out:rw \
  --property=MemoryLimit=512M \
  --property=CPUQuota=25% \
  --network-veth \
  --boot
```

### 3.2 Persistence: Host Bind Mounts

Each container gets persistent storage via bind mounts from the host:

```
/var/abis/
├── containers/          # Container root filesystems (ephemeral, resettable)
│   ├── user-001/
│   ├── user-002/
│   └── ...
├── volumes/             # Persistent user data (survives container rebuild)
│   ├── user-001/        # Hermes workspace, skills, memory
│   │   ├── workspace/
│   │   ├── .hermes/
│   │   └── .openclaw/   # If user wants OpenClaw bridge
│   ├── user-002/
│   └── ...
├── tasks/               # Task inboxes/outboxes (transient, but logged)
│   ├── user-001/
│   │   ├── in/          # Tasks waiting for agent
│   │   └── out/         # Results from agent
│   ├── user-002/
│   └── ...
└── db.sqlite            # Orchestrator state DB
```

### 3.3 Communication: Filesystem IPC (Inbox/Outbox)

**Why filesystem over HTTP/socket:**
- No port allocation complexity per container
- No network stack needed between orchestrator and container
- Simple polling: orchestrator watches directories with `inotify`
- Hermes agent reads JSON task files, writes JSON result files
- Survives container restarts (files persist on host)

**Task format (JSON):**
```json
{
  "task_id": "uuid",
  "timestamp": "2026-07-27T13:45:00Z",
  "from": "chief-of-staff",
  "type": "code_review|research|coding|qa",
  "prompt": "Review this Python file for bugs...",
  "attachments": ["/shared/volumes/user-001/workspace/file.py"],
  "timeout_seconds": 300
}
```

**Result format (JSON):**
```json
{
  "task_id": "uuid",
  "status": "completed|failed|timeout",
  "result": "...",
  "artifacts": ["/shared/out/report.md"],
  "started_at": "...",
  "completed_at": "..."
}
```

### 3.4 Orchestrator → Agent Dispatch Flow

```
You (Chief of Staff)
  │
  │ "Send task T to user-001"
  ▼
Orchestrator Service (on host)
  │
  │ 1. Validate user exists and container is running
  │ 2. Write task-T.json to /var/abis/tasks/user-001/in/
  │ 3. Notify container (SIGUSR1 or inotify)
  ▼
Container user-001 (systemd-nspawn)
  │
  │ Hermes agent polls /shared/in/ every 5s
  │ Sees task-T.json
  │ Executes task
  │ Writes result-T.json to /shared/out/
  ▼
Orchestrator Service (notices new file via inotify)
  │
  │ Reads result-T.json
  │ Optionally forwards to ABIS API
  │ Logs to SQLite
  ▼
You (Chief of Staff sees result)
```

---

## 4. Port Allocation Strategy

### Host Ports (fixed, shared)
| Port | Service | Notes |
|------|---------|-------|
| 11434 | Ollama | Native Ollama API |
| 11435 | LiteLLM | Optional model proxy |
| 18789 | OpenClaw Gateway | Optional bridge |
| 7582 | ABIS API | New — Flask/FastAPI |
| 7583 | Orchestrator API | New — internal, localhost only |

### Container Ports (none needed)
- Containers use filesystem IPC, not network ports
- If future needs require HTTP per container, use dynamic port allocation starting at 18000

---

## 5. Security Boundaries

### 5.1 User Isolation
- Each container runs with `--private-users` (UID mapping)
- Host files are owned by root; container sees them as owned by user
- No root access inside container (drops to unprivileged user)
- Containers cannot see each other's volumes (separate bind mounts)

### 5.2 Resource Limits
- Memory: 512MB per container (cgroups via `--property=MemoryLimit`)
- CPU: 25% per container (cgroups via `--property=CPUQuota`)
- Disk: 5GB per user volume (quota or separate partition)

### 5.3 Network Isolation
- `--network-veth` gives each container a virtual ethernet interface
- No bridge between containers (host acts as router, but we drop packets)
- Containers can reach Ollama 11434 but cannot reach other containers
- Firewall rules: `iptables -A FORWARD -i ve-+ -o ve-+ -j DROP`

### 5.4 Data Privacy
- User volumes encrypted at rest (optional — LUKS per volume)
- Orchestrator can read all data (by design — you oversee everything)
- Audit log of all orchestrator actions in SQLite

---

## 6. API Schema (Orchestrator ↔ Container)

### Container Lifecycle API
```
POST /containers
  Body: {"user_id": "user-001", "template": "hermes-base"}
  Response: {"container_id": "user-001", "status": "creating", "ip": "..."}

GET /containers/:id
  Response: {"id": "user-001", "status": "running|stopped|error", 
             "pid": 12345, "memory_mb": 256, "cpu_percent": 12}

POST /containers/:id/start
  Response: {"status": "started"}

POST /containers/:id/stop
  Response: {"status": "stopped"}

DELETE /containers/:id
  Response: {"status": "destroyed", "data_preserved": true}
```

### Task Dispatch API
```
POST /containers/:id/tasks
  Body: {"type": "code_review", "prompt": "...", "timeout": 300}
  Response: {"task_id": "uuid", "status": "queued"}

GET /containers/:id/tasks/:task_id
  Response: {"task_id": "...", "status": "running|completed|failed",
             "result": "...", "artifacts": [...]}
```

---

## 7. Acceptance Criteria Check

| Criterion | How Architecture Satisfies |
|-----------|---------------------------|
| Supports N users with isolated data | systemd-nspawn + private volumes per user |
| Agent data persists across reconnects | Bind-mounted volumes survive container restart |
| Admin can approve/reject from UI | ABIS API + Admin Panel + SQLite state |
| Chief of Staff can dispatch to any container | Orchestrator Service + filesystem IPC |
| Containers are pure silos | No network bridge, no shared volumes, UID isolation |

---

## 8. Open Questions for Research Phase (#2)

1. Can systemd-nspawn on Raspberry Pi 6.12.47 handle 5+ concurrent containers with 512MB each?
2. What's the actual boot time for a systemd-nspawn container with Hermes agent?
3. Does inotify work reliably across bind mounts from host to container?
4. What's the SQLite schema for users, containers, tasks, sessions?
5. Should the portal frontend be part of existing `abishk-website` or a separate deployment?
6. Do we need an OpenClaw bridge, or can Hermes agent run standalone inside containers?

---

## 9. Phase 2 Doors (Deferred)

- Multi-host scaling (Kubernetes/nomad) — not needed on single Pi
- GPU allocation per container (if we get Coral TPU or Jetson)
- Real-time collaboration (multiple users editing same file)
- Advanced monitoring (Prometheus/Grafana per container)

---

*Architecture defined. Ready for research phase (#2).*
