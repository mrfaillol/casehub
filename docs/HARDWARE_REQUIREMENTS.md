# CaseHub White-Label -- Hardware Requirements

> Version 2.0 | Last updated: 2026-03-25

---

## 1. Minimum Specifications (Self-Hosted)

For a small firm with up to 5 concurrent users and under 500 clients.

| Resource | Minimum |
|---|---|
| CPU | 2 cores (x86_64 or ARM64) |
| RAM | 4 GB |
| Disk | 20 GB SSD |
| Network | 10 Mbps symmetric |
| OS | Ubuntu 22.04/24.04 LTS, Debian 12, or any Docker-capable Linux |

This configuration can run the full stack: PostgreSQL + Redis + CaseHub app + Nginx. Not recommended for production workloads with document-heavy usage or AI features (sentence-transformers model loading requires significant RAM).

---

## 2. Recommended Specifications

For a mid-size firm with up to 25 concurrent users and under 5,000 clients.

| Resource | Recommended |
|---|---|
| CPU | 4 cores |
| RAM | 8 GB |
| Disk | 50 GB SSD (NVMe preferred) |
| Network | 100 Mbps symmetric |
| OS | Ubuntu 24.04 LTS |

This handles the full feature set including AI-powered tools (LOR generator, personal statement generator, legal assistant), background workers, and moderate file storage.

### High-Volume Specification

For multi-tenant deployments serving 10+ organizations or 50+ concurrent users:

| Resource | High Volume |
|---|---|
| CPU | 8 cores |
| RAM | 16 GB |
| Disk | 200 GB NVMe SSD |
| Network | 1 Gbps |

---

## 3. Per-Concurrent-User Estimates

| Component | Per User (approx.) |
|---|---|
| Application memory | 50-100 MB |
| Database connections | 1-3 connections |
| Disk I/O | Negligible for page views; ~1 MB/s during file uploads |
| Network bandwidth | ~100 KB/s average, 5 MB/s peak (file downloads) |

### Scaling Formula

```
Recommended RAM (GB) = 2 (base) + (concurrent_users * 0.1) + (total_clients / 5000)
Recommended CPU cores = max(2, concurrent_users / 10)
Recommended Disk (GB) = 10 (base) + (total_documents * avg_doc_size_MB)
```

### Example Configurations

| Scenario | Users | Clients | Documents | Recommended Spec |
|---|---|---|---|---|
| Solo attorney | 1-2 | 100 | 500 | 2 cores, 4 GB, 20 GB |
| Small firm | 5-10 | 500 | 5,000 | 4 cores, 8 GB, 50 GB |
| Mid-size firm | 10-25 | 2,000 | 20,000 | 4 cores, 8 GB, 100 GB |
| Multi-tenant SaaS | 50+ | 10,000+ | 100,000+ | 8 cores, 16 GB, 500 GB |

---

## 4. Database Sizing Guide

### PostgreSQL Storage

| Data Type | Estimated Size |
|---|---|
| Per client record | ~2 KB |
| Per case record | ~3 KB |
| Per document metadata record | ~1 KB |
| Per task record | ~0.5 KB |
| Per billing item | ~0.5 KB |
| Per audit log entry | ~0.3 KB |

### Projection Table

| Clients | Cases | Documents | Audit Logs | Estimated DB Size |
|---|---|---|---|---|
| 500 | 1,000 | 5,000 | 50,000 | ~50 MB |
| 2,000 | 5,000 | 20,000 | 200,000 | ~200 MB |
| 10,000 | 25,000 | 100,000 | 1,000,000 | ~1 GB |
| 50,000 | 100,000 | 500,000 | 5,000,000 | ~5 GB |

The database itself is compact. File storage (uploaded documents, signatures, email attachments) is the primary disk consumer. Budget 5-50 MB per client for document storage, depending on case complexity.

### PostgreSQL Configuration

For the recommended 8 GB RAM server, tune `postgresql.conf`:

```ini
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 16MB
maintenance_work_mem = 512MB
max_connections = 100
```

---

## 5. Network Requirements

### Ports

| Port | Service | Access |
|---|---|---|
| 80 | Nginx (HTTP redirect) | Public |
| 443 | Nginx (HTTPS) | Public |
| 8001 | CaseHub (uvicorn) | Internal only (proxied by Nginx) |
| 5432 | PostgreSQL | Internal only |
| 6379 | Redis | Internal only |
| 3001 | WhatsApp Bot | Internal only (proxied by CaseHub) |

### Outbound Connections

The server requires outbound access to:

| Destination | Purpose |
|---|---|
| `smtp.gmail.com:587` (or custom SMTP) | Sending emails |
| `imap.gmail.com:993` | Reading emails (IMAP) |
| `googleapis.com:443` | Google Drive, Calendar |
| `api.stripe.com:443` | Payment processing |
| `api.twilio.com:443` | SMS / WhatsApp |
| `api.callhippo.com:443` | VoIP |
| `api.notion.com:443` | Knowledge base |
| `api.perplexity.ai:443` | AI legal research |
| `generativelanguage.googleapis.com:443` | Gemini AI |
| `web.whatsapp.com:443` | WhatsApp Web (bot) |

### Firewall Rules

Allow inbound: 80/tcp, 443/tcp, 22/tcp (SSH).
Block inbound: 5432, 6379, 8001, 3001 (internal services).

---

## 6. Windows PC Compatibility

CaseHub can run on Windows using Docker Desktop with WSL2.

### Requirements

| Component | Version |
|---|---|
| Windows | 10 (build 19041+) or Windows 11 |
| Docker Desktop | 4.x with WSL2 backend |
| WSL2 | Ubuntu 22.04 or 24.04 distribution |
| RAM | 8 GB minimum (Docker uses WSL2 memory) |

### Setup Steps

1. Install WSL2: `wsl --install -d Ubuntu-24.04`
2. Install Docker Desktop and enable WSL2 integration.
3. Open the Ubuntu terminal in WSL2.
4. Clone the repo and follow the Docker Compose instructions from the Deployment guide.

```powershell
# In WSL2 terminal:
git clone git@github.com:mrfaillol/casehub.git /opt/casehub
cd /opt/casehub
cp .env.example .env
# Edit .env
docker compose up -d
```

### Windows-Specific Notes

- File system performance is better inside WSL2 (`/home/user/`) than on the Windows mount (`/mnt/c/`). Clone the repo inside WSL2.
- Docker Desktop allocates 50% of system RAM to WSL2 by default. For a 16 GB machine, Docker gets 8 GB. Adjust in `%USERPROFILE%\.wslconfig`:

```ini
[wsl2]
memory=8GB
processors=4
```

- Port forwarding works automatically: `localhost:8001` on Windows maps to the Docker container.
- For production on Windows Server, use Docker with Hyper-V isolation instead of WSL2.

---

## 7. Cloud Provider Recommendations

### DigitalOcean (Recommended for Small/Medium)

| Droplet | Specs | Price (approx.) | Best For |
|---|---|---|---|
| Basic 4GB | 2 vCPU, 4 GB, 80 GB SSD | $24/mo | Solo/small firm |
| Basic 8GB | 4 vCPU, 8 GB, 160 GB SSD | $48/mo | Mid-size firm |
| General 16GB | 4 vCPU, 16 GB, 100 GB NVMe | $84/mo | Multi-tenant |

Advantages: Simple, predictable pricing, managed PostgreSQL available, good datacenter coverage.

### AWS

| Instance | Specs | Price (approx.) | Best For |
|---|---|---|---|
| t3.medium | 2 vCPU, 4 GB | ~$30/mo | Dev/staging |
| t3.large | 2 vCPU, 8 GB | ~$60/mo | Small firm |
| m6i.xlarge | 4 vCPU, 16 GB | ~$140/mo | Multi-tenant |

Advantages: RDS for managed PostgreSQL, ElastiCache for Redis, S3 for file storage, global infrastructure.

Use **RDS PostgreSQL** instead of self-hosted PostgreSQL for automated backups, failover, and scaling.

### Oracle Cloud (Free Tier)

| Instance | Specs | Price |
|---|---|---|
| ARM A1.Flex | 4 cores, 24 GB, 200 GB | Free (Always Free tier) |

Oracle Cloud's Always Free tier offers an ARM instance with generous specs. CaseHub runs on ARM64 (the Docker image uses `python:3.12-slim` which supports ARM). Ideal for testing or very low-budget deployments.

### Hetzner (Budget-Friendly, EU)

| Server | Specs | Price (approx.) | Best For |
|---|---|---|---|
| CX22 | 2 vCPU, 4 GB, 40 GB | ~$4/mo | Testing |
| CX32 | 4 vCPU, 8 GB, 80 GB | ~$7/mo | Small firm |
| CX42 | 8 vCPU, 16 GB, 160 GB | ~$14/mo | Multi-tenant |

Advantages: Extremely competitive pricing, EU/US datacenters, solid performance.

### Recommendation Summary

| Use Case | Provider | Instance |
|---|---|---|
| Self-hosted, simple | DigitalOcean | Basic 8GB ($48/mo) |
| Enterprise, managed DB | AWS | t3.large + RDS |
| Budget / testing | Oracle Free Tier or Hetzner CX32 |
| Brazil-focused (Lite) | DigitalOcean or Oracle (Sao Paulo region) |

---

## 8. Resource Usage Breakdown

### Idle State (no active users)

| Process | CPU | RAM |
|---|---|---|
| CaseHub (uvicorn, 1 worker) | <1% | 150-300 MB |
| PostgreSQL | <1% | 100-200 MB |
| Redis | <1% | 10-30 MB |
| Nginx | <1% | 5-15 MB |
| WhatsApp Bot (Node.js) | <1% | 80-150 MB |
| **Total** | **<5%** | **~500 MB - 1 GB** |

### Under Load (10 concurrent users)

| Process | CPU | RAM |
|---|---|---|
| CaseHub (uvicorn, 1 worker) | 10-30% | 300-600 MB |
| PostgreSQL | 5-15% | 200-500 MB |
| Redis | <5% | 30-50 MB |
| Nginx | <5% | 15-30 MB |
| WhatsApp Bot (Node.js) | <5% | 100-200 MB |
| **Total** | **~30-60%** | **~1-1.5 GB** |

### Peak Operations

| Operation | CPU Spike | RAM Spike | Duration |
|---|---|---|---|
| AI content generation (LOR/PS) | 50-80% | +500 MB (model loading) | 5-30 seconds |
| PDF packet assembly | 30-50% | +200 MB | 10-60 seconds |
| USCIS form auto-fill | 20-40% | +100 MB | 5-15 seconds |
| Bulk email campaign | 10-20% | +50 MB | Varies |
| Google Drive sync (full) | 10-30% | +100 MB | Varies |

The `sentence-transformers` model (used by the legal assistant and document classifier) is the largest memory consumer. On first load it downloads ~400 MB of model weights and uses ~500 MB RAM. If you do not need AI features, this dependency can be removed from `requirements.txt` to significantly reduce memory usage.
