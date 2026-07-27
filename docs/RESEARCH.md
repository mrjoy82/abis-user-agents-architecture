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
- **No NFS exports configured** on this Pi (`showmount -e` failed)
- No dedicated `pi-nas` device is currently online or exporting volumes

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

### Finding: No separate NAS device is currently operational

| Strategy | Feasibility | Persistence | Speed | Verdict |
|----------|------------|-------------|-------|---------|
| **Local bind mounts** (host → container) | Immediate | Survives container restart | Fast (local SSD) | **POC RECOMMENDATION** |
| Docker named volumes | Immediate | Survives container restart | Fast | Good alternative |
| NFS from separate Pi | Requires 2nd Pi | Network-attached | Medium | **Production target** |
| SSHFS | Requires remote host | Network-attached | Slow | Not recommended |
| Git-based persistence | Complex | Versioned but heavy | Slow | Overkill for POC |

### POC Plan: Simulated pi-nas on same host

Since no separate NAS Pi is online, Phase 1 will simulate the pi-nas layout:

```
/var/abis/volumes/          # On host SSD (simulates /var/nfs/abis/volumes/)
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

When `pi-nas` is deployed, the same directory structure migrates to NFS:
```bash
# Mount NFS on host
mount pi-nas:/var/nfs/abis/volumes /var/abis/volumes
# Containers keep same bind mounts — transparent migration
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
Pi 5 has 4 cores. 8 containers × 1 core = 8 cores requested. Containers will be CPU-throttled but not crash — Linux handles oversubscription via time-slicing. For POC with 1-3 active kids simultaneously, this is fine. For 8 concurrent active kids, we need either:
- Mac Mini M5 (Phase 2 hardware)
- systemd-nspawn (lower overhead)
- Docker CPU limits (`--cpus=0.5` per container)

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
| 2 | Persistence | Local bind mounts on host SSD | NFS from dedicated pi-nas |
| 3 | Communication | HTTP API + WebSocket per container | Same (no change needed) |
| 4 | Port range | 7584-7591 (8 containers) | Expand as needed |
| 5 | Admin approval | Boolean flag in SQLite | Email/webhook/classroom codes |
| 6 | Resource limit | 512MB-1GB RAM, 5GB disk per kid | CPU throttling, quotas |
| 7 | Max concurrent | 8 kids (CPU oversubscribed) | Mac Mini M5 scaling |

---

## 9. Next Steps

1. Proceed to ticket #3 [grilling] or #4 [prototype]
2. When ready to build: `mkdir -p /var/abis/volumes/kid-001/{workspace,chat_history,.hermes}`
3. Create base Docker image: `python:3.11-slim` + FastAPI + WebSocket + Ollama client
4. Test container with: `docker run -p 7584:7584 -v /var/abis/volumes/kid-001:/home/user abis-ata-base`
