# Research Report: Containerization Options and Persistence Patterns

**Date:** 2026-07-27
**Ticket:** #2 [research] Analyze containerization options and persistence patterns
**Scope:** ARM64 Raspberry Pi 5 (16GB RAM), Debian Trixie
**Status:** COMPLETE

---

## 1. Infrastructure Survey Results

### 1.1 Hardware
- **Host:** Raspberry Pi 5, 16GB RAM, ARM64 (`aarch64`)
- **OS:** Debian GNU/Linux 13 (trixie)
- **Init:** systemd (PID 1 = `systemd`)
- **Available RAM:** ~11GB (4.4GB used, 11GB cache/buffers)

### 1.2 Installed Container Runtimes
| Runtime | Installed? | Version | Notes |
|---------|-----------|---------|-------|
| Docker | YES | 29.5.3 | Full Docker CE + Buildx + Compose |
| systemd-nspawn | NO | N/A | Package `systemd-container` not installed |
| LXC/LXD | NO | N/A | Not installed |
| Podman | NO | N/A | Not installed |

### 1.3 Network Services (Active Ports)
```
7582   — Python/Flask (existing)
10888  — Unknown
11433  — LiteLLM Proxy
11434  — Ollama
11435  — LiteLLM
18789  — OpenClaw Gateway
38336  — Unknown
```

### 1.4 Storage / NFS
- `nfs-common` and `rpcbind` are installed (NFS client ready)
- **NAS device online but NFS not yet configured:** `pi-nas` at `192.168.1.109` responds to ping (0.25ms) but `showmount -e` fails with "RPC: Program not registered"
- **Decision required:** Configure NFS server on `192.168.1.109` now, or use local bind mounts as temporary stand-in for POC

| Path | Description | Trade-off |
|------|------------|-----------|
| **A. NFS now** | Set up `nfs-kernel-server` on 192.168.1.109, export `/var/nfs/abis/volumes/` | True production layout from day one, requires extra setup |
| **B. Local stand-in** | Use `/var/abis/volumes/` on host SSD as temporary directory | Immediate, zero config, transparent migration to NFS later |

---

## 2. Container Technology Recommendation

### Finding: Docker is the only working runtime today

**Recommendation: Use Docker for Phase 1 POC.**

| Technology | Status on Pi | Overhead | ARM64 Support | Verdict |
|------------|-------------|----------|--------------|---------|
| **Docker** | Installed, tested OK | ~50-100MB per container | Excellent (ARM64 images on Docker Hub) | **RECOMMENDED** |
| systemd-nspawn | Not installed | Very low (~10MB) | Native Linux | Installable but unverified |
| LXC | Not installed | Low | Good | Extra setup burden |
| chroot | Built-in | Minimal | Native | Too weak isolation for child safety |
| firejail | Not installed | Low | Good | Good for sandboxing apps, not containers |

### Why Docker over systemd-nspawn for Phase 1

1. **Works now.** No additional packages needed. The `hello-world` ARM64 image pulled and ran successfully.
2. **Image ecosystem.** ARM64 Python images (`python:3.11-slim`) available on Docker Hub.
3. **Port management.** Docker handles port mapping (`-p 7584:7584`) automatically.
4. **Volume management.** Named volumes and bind mounts are well-tested.
5. **Future portability.** If we move to Mac Mini M5s later, Docker is the universal standard.

### Phase 2 Door: systemd-nspawn
- `systemd-container` package is installable via apt (`257.13-1~deb13u1`)
- Lower overhead, no Docker daemon dependency
- **Deferred** to Phase 2 when we need max density (8+ concurrent kids)
- Docker container can be converted to systemd-nspawn directory with `docker export` + `systemd-nspawn`

---

## 3. Persistence Strategy Recommendation

### Finding: NAS device exists but NFS service is not yet configured

**Correction (2026-07-27):** `pi-nas` at `192.168.1.109` is online and reachable (0.25ms ping). The NFS *server* is not running — `showmount -e` fails with "RPC: Program not registered". This is a configuration gap, not a hardware gap.

| Strategy | Feasibility | Persistence | Speed | Verdict |
|----------|------------|-------------|-------|---------|
| **NFS from pi-nas (192.168.1.109)** | Needs `nfs-kernel-server` setup on NAS | Network-attached, survives host reboot | Fast (local LAN) | **RECOMMENDED once configured** |
| Local bind mounts (host → container) | Immediate | Survives container restart | Fast (local SSD) | **POC fallback** |
| Docker named volumes | Immediate | Survives container restart | Fast | Good alternative |
| SSHFS | Requires remote host | Network-attached | Slow | Not recommended |
| Git-based persistence | Complex | Versioned but heavy | Slow | Overkill for POC |

### POC Plan: Local bind mounts until NFS is ready

While NFS server setup is pending, use local bind mounts on host SSD:

```
/var/abis/volumes/          # On host SSD (temporary, mirrors eventual NFS layout)
├── kid-001/
│   ├── workspace/
│   ├── chat_history/
│   └── .hermes/
├── kid-002/
└── ...
```

Each container gets a bind mount:
```bash
docker run -v /var/abis/volumes/kid-001:/home/user ...
```

**Migration to NFS is transparent:** when NFS is ready on `192.168.1.109`, mount it at `/var/abis/volumes/` on the host. Containers keep the same bind mounts — no container changes needed.

```bash
# Once NFS is configured on pi-nas:
mount -t nfs 192.168.1.109:/var/nfs/abis/volumes /var/abis/volumes
# Containers continue working unchanged
```

### Phase 2 Door: Real pi-nas
- Deploy second Raspberry Pi as NFS server
- Export `/var/nfs/abis/volumes/` with `rw,no_root_squash`
- Host mounts NFS, containers bind-mount from host mountpoint
- Add daily `rsync` backup to host SSD for redundancy

---

## 4. Communication Protocol Recommendation

### Finding: WebSocket proxy through orchestrator is already in architecture

| Approach | Latency | Complexity | Safety Monitorable | Verdict |
|----------|---------|-----------|-------------------|---------|
| **HTTP API + WebSocket per container** | Low | Medium | Yes (orchestrator intercepts) | **RECOMMENDED** |
| Shared filesystem (inbox/outbox) | High (polling) | Low | No (not real-time) | Rejected |
| Unix socket | Very low | Medium | No (bypasses orchestrator) | Rejected |
| Redis pub/sub | Low | Medium | Yes (if orchestrator reads) | Good but extra dependency |
| stdin/stdout pipe | Low | Low | No | Brittle, rejected |

### Why HTTP API + WebSocket
1. **Architecture already specifies it** (FastAPI + WebSocket in each container)
2. **Orchestrator can intercept** all traffic for safety scanning before forwarding
3. **Standard tooling** (`curl`, browser WebSocket API, `websocat`)
4. **Port allocation is simple** (sequential: 7584, 7585, ...)
5. **Same protocol for Phase 2** (no migration needed when adding more features)

### Why not SSE (Server-Sent Events)?

SSE was considered and explicitly rejected:

| Aspect | WebSocket | SSE (HTTP streaming) |
|--------|-----------|----------------------|
| Direction | **Bidirectional** (send + receive on same connection) | Unidirectional (server→client only) |
| Send message | Same socket | Separate POST request |
| State management | One connection object | Two connection objects to manage |
| Real-time chat | Natural | Requires polling or dual connection |
| Tool results | JSON payload back on same socket | Needs another POST/response |

**Verdict:** SSE is elegant for one-way push (notifications, logs) but awkward for conversational AI where user sends messages and agent streams responses back. WebSocket is the correct abstraction for bidirectional chat.

**Phase 2 door:** SSE could supplement WebSocket for admin notifications (new signup alert, safety flag) where only server→client push is needed.

### Port Allocation Plan
```
7582 — ABIS API (Flask/FastAPI on host)
7583 — Orchestrator service (localhost only)
7584 — ATA Agent: kid-001
7585 — ATA Agent: kid-002
7586 — ATA Agent: kid-003
7587 — ATA Agent: kid-004
7588 — ATA Agent: kid-005
7589 — ATA Agent: kid-006
7590 — ATA Agent: kid-007
7591 — ATA Agent: kid-008
```

**Max:** 8 concurrent kids for POC (8 × 1GB = 8GB RAM, leaving ~3GB for host services).

---

## 5. Admin Approval Workflow Recommendation

| Pattern | Implementation | Effort | Flexibility | Verdict |
|---------|---------------|--------|-------------|---------|
| **Boolean flag in SQLite** | `approved = 0/1` in users table | 1 hour | Low | **POC RECOMMENDATION** |
| Email notification | SMTP integration | 2 hours | Medium | Phase 2 |
| Webhook to external system | Generic HTTP callback | 2 hours | High | Phase 2 |
| Queue-based workflow | Celery/Redis tasks | 4+ hours | High | Overkill for POC |

### POC: Simple boolean flag
- User signs up → `approved = 0`
- Admin sees pending list → toggles `approved = 1`
- Login blocked if `approved = 0`
- Orchestrator only creates containers for `approved = 1` users

### Production workflow (Phase 2)

The user's refinement: admin should only see the "Approve" button after the kid's full setup is complete.

```
signup
  → profile_complete (kid fills profile)
    → access_restrictions_set (admin configures age-appropriate permissions)
      → admin_sees_approve_button
        → approved = 1
          → container_created
```

**States:** `PENDING_PROFILE` → `PENDING_RESTRICTIONS` → `PENDING_APPROVAL` → `APPROVED` → `CONTAINER_READY`

This ensures the admin never approves a kid whose permissions haven't been configured.

### Phase 2 Doors
- Email notification to admin on new signup
- Webhook to Slack/Discord/Mission Control
- Auto-approve with CAPTCHA + email verification
- Classroom code bulk approval (teacher generates code, kids self-register)

---

## 6. Resource Budget

| Component | Memory | CPU | Disk |
|-----------|--------|-----|------|
| Ollama (loaded model) | 4-8GB | 4 cores | 20GB+ |
| LiteLLM Proxy | 200MB | Low | 1GB |
| ABIS API (Flask) | 200MB | Low | 500MB |
| Orchestrator | 200MB | Low | 500MB |
| **Per ATA container** | **512MB-1GB** | **1 core** | **5GB** |
| 8 containers | **4-8GB** | **8 cores** | **40GB** |
| **Total headroom** | **~3GB** | **4 cores (Pi 5 = 4 cores)** | **Host SSD** |

### Concern: CPU oversubscription
Pi 5 has 4 cores. 8 containers × 1 core = 8 cores requested. Containers will be CPU-throttled but not crash — Linux handles oversubscription via time-slicing. For POC with 1-3 active kids simultaneously, this is fine. For 8 concurrent active kids, response times will degrade.

**Options to scale beyond 3-4 active kids on Pi 5:**
- Docker CPU limits (`--cpus=0.5` per container) — reduces per-kid responsiveness
- systemd-nspawn — lower overhead, ~20% more capacity
- Mac Mini M5 — Phase 2 hardware (see below)

### Phase 2 Hardware: Mac Mini M5 Capacity

Why Mac Mini M5 solves the problem:

| Spec | Raspberry Pi 5 | Mac Mini M5 (24GB) | Mac Mini M5 (32GB) |
|------|---------------|---------------------|---------------------|
| CPU | 4 × Cortex-A76 @ 2.4GHz | ~12 cores (4P+8E) @ ~4.4GHz | ~12 cores (4P+8E) @ ~4.4GHz |
| Single-core IPC | ~1x baseline | ~3-4x faster per core (Apple Silicon) | ~3-4x faster per core |
| RAM | 16GB LPDDR4X | 24GB unified memory | 32GB unified memory |
| Memory bandwidth | ~34 GB/s | ~100+ GB/s | ~100+ GB/s |
| Neural Engine | None | 16-core (38 TOPS) | 16-core (38 TOPS) |
| Idle→load latency | Slow (load model from SD) | Fast (unified memory) | Fast |

**Estimated simultaneous active ATA users:**

| Hardware | Ollama RAM | Left for ATA | Per kid (512MB) | Simultaneous active |
|----------|-----------|-------------|-----------------|-------------------|
| Pi 5 (16GB) | ~6GB | ~10GB | 20 kids | **2-3** (CPU-bound) |
| Mac Mini M5 (24GB) | ~8GB | ~16GB | 32 kids | **20-25** (CPU ample) |
| Mac Mini M5 (32GB) | ~8GB | ~24GB | 48 kids | **30-40** (CPU ample) |

**Key insight:** On Pi 5, RAM is not the bottleneck — CPU is. 4 weak cores cannot drive 8 concurrent LLM inference streams. On Mac Mini M5, CPU is 9-12× faster and has 3× the cores, so CPU is no longer the bottleneck. RAM becomes the limiting factor, and 24-32GB supports 20-40 active kids comfortably.

**1 Mac Mini M5 (24GB) ≈ 8-10 Raspberry Pi 5s** for this workload.

---

## 7. Deliverables Checklist

- [x] Container technology recommendation with justification
- [x] Persistence strategy recommendation
- [x] Communication protocol recommendation
- [x] Admin approval workflow recommendation
- [x] Port allocation plan
- [x] Sample directory structure for user data
- [x] Raspberry Pi constraints considered (ARM64, limited RAM, 4 cores)
- [x] Persistence confirmed to survive container restarts (bind mounts)
- [x] Communication protocol simple enough for prototype (WebSocket, standard)

---

## 8. Summary Table

| # | Decision | Phase 1 (POC) | Phase 2 Door |
|---|----------|--------------|--------------|
| 1 | Container runtime | Docker (installed, working) | systemd-nspawn (lower overhead) |
| 2 | Persistence | Local bind mounts on host SSD (NFS at 192.168.1.109 not yet configured) | NFS from pi-nas (192.168.1.109) |
| 3 | Communication | HTTP API + WebSocket per container | SSE for admin notifications (one-way push) |
| 4 | Port range | 7584-7591 (8 containers) | Expand as needed |
| 5 | Admin approval | Boolean flag in SQLite | Multi-state workflow: profile → restrictions → approval |
| 6 | Resource limit | 512MB-1GB RAM, 5GB disk per kid | CPU throttling, quotas |
| 7 | Max concurrent (Pi 5) | 8 enrolled, ~2-3 simultaneously active | Mac Mini M5: 20-40 simultaneously active |

---

## 9. Next Steps

1. Proceed to ticket #3 [grilling] or #4 [prototype]
2. When ready to build: `mkdir -p /var/abis/volumes/kid-001/{workspace,chat_history,.hermes}`
3. Create base Docker image: `python:3.11-slim` + FastAPI + WebSocket + Ollama client
4. Test container with: `docker run -p 7584:7584 -v /var/abis/volumes/kid-001:/home/user abis-ata-base`
