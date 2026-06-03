# CaseHub Lite -- Deployment Guide (Client VPS)

> Version 3.0 | Last updated: 2026-03-30
>
> Step-by-step guide for deploying CaseHub Lite on a client's VPS.
> Based on lessons learned during the o cliente deployment.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Initial Server Setup](#2-initial-server-setup)
3. [Clone and Configure](#3-clone-and-configure)
4. [Environment Variables Reference](#4-environment-variables-reference)
5. [Docker Build and Start](#5-docker-build-and-start)
6. [Database Setup and Seeding](#6-database-setup-and-seeding)
7. [Nginx + HTTPS (SSL)](#7-nginx--https-ssl)
8. [Ollama / Maestro IA (Optional)](#8-ollama--maestro-ia-optional)
9. [Oracle Cloud Specifics](#9-oracle-cloud-specifics)
10. [Backups and Cron Jobs](#10-backups-and-cron-jobs)
11. [Monitoring and Health Checks](#11-monitoring-and-health-checks)
12. [Updating the Application](#12-updating-the-application)
13. [Troubleshooting](#13-troubleshooting)
14. [Known Issues and Gotchas](#14-known-issues-and-gotchas)

---

## 1. Prerequisites

### Hardware

| Spec | Minimum | Recommended (with Ollama) |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 20 GB | 50 GB |
| Architecture | x86_64 or ARM64 | x86_64 or ARM64 |

### Software

- **OS**: Ubuntu 22.04 LTS (tested on both x86 and ARM/Oracle)
- **Docker Engine** 24+ with Docker Compose v2
- **Git**
- **Nginx** (as reverse proxy)
- **Certbot** (for free Let's Encrypt HTTPS)

### Network

- A domain (or subdomain) with DNS A record pointing to the VPS IP
- Firewall / Security Group must allow inbound on:
  - **22** (SSH)
  - **80** (HTTP, for certbot and redirect)
  - **443** (HTTPS)
  - **8001** (CaseHub direct, optional for debugging)
  - **8002** (CaseHub Lite mapped port)

### Access

- SSH access to the VPS as `ubuntu` (or equivalent sudo user)
- GitHub access to clone `https://github.com/mrfaillol/casehub.git` (private repo -- requires deploy key or PAT)

---

## 2. Initial Server Setup

SSH into the VPS and run:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install -y docker.io docker-compose-v2 git nginx certbot python3-certbot-nginx

# Add your user to the docker group (avoids needing sudo for docker)
sudo usermod -aG docker $USER

# IMPORTANT: Log out and back in for group change to take effect
exit
# ssh back in

# Verify Docker works
docker compose version
# Expected: Docker Compose version v2.x.x
```

### Create directory structure

```bash
mkdir -p /home/ubuntu/backups
mkdir -p /opt/casehub
```

---

## 3. Clone and Configure

```bash
cd /home/ubuntu
git clone https://github.com/mrfaillol/casehub.git
cd casehub

# Create .env from template
cp .env.example .env
```

Edit `.env` with the client's values:

```bash
nano .env
```

At minimum, set these values:

```ini
# === REQUIRED ===
SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
ENCRYPTION_KEY=<generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
POSTGRES_PASSWORD=<strong random password>
ADMIN_EMAIL=admin@clientdomain.com

# === PRODUCT ===
CASEHUB_PRODUCT=lite
DEFAULT_LOCALE=pt-BR

# === ORGANIZATION ===
ORG_NAME=Nome do Escritorio
ORG_NAME_LITE=Nome do Escritorio
ORG_EMAIL=contato@escritorio.com
ORG_DOMAIN=escritorio.com
CASE_PREFIX=VS

# === SERVER ===
BASE_URL=https://sistema.escritorio.com
PREFIX=/casehub
PORT=8001
```

> **WARNING**: Never commit `.env` to git. The `.gitignore` already excludes it, but double-check.

---

## 4. Environment Variables Reference

### Required (app will not start without these)

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | JWT signing key, 32+ bytes hex | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ENCRYPTION_KEY` | Fernet key for PII encryption (SSN, CPF, etc.) | `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `POSTGRES_PASSWORD` | PostgreSQL password (used by Docker Compose) | Strong random string |
| `ADMIN_EMAIL` | Email for auto-created admin account on first run | `admin@firm.com` |

### Product Configuration

| Variable | Description | Default |
|---|---|---|
| `CASEHUB_PRODUCT` | Product mode: `lite` or `immigration` | `immigration` |
| `DEFAULT_LOCALE` | UI language | `en-US` (set `pt-BR` for Lite) |
| `DEFAULT_CURRENCY` | Currency for financial features | Auto: `BRL` for Lite, `USD` for Immigration |
| `DEFAULT_TIMEZONE` | Server timezone | Auto: `America/Sao_Paulo` for Lite |

### Organization

| Variable | Description | Default |
|---|---|---|
| `ORG_NAME` | Display name in UI, emails, documents | `CaseHub` |
| `ORG_NAME_LITE` | Display name specifically for Lite container | `CaseHub Lite` |
| `ORG_EMAIL` | Primary contact email | -- |
| `ORG_DOMAIN` | Domain for subdomain routing | -- |
| `CASE_PREFIX` | Prefix for case numbers (e.g., `VS` -> `VS-2026-0001`) | `CH` |
| `TEAM_MEMBERS` | Comma-separated names for assignment dropdowns | -- |

### Server

| Variable | Description | Default |
|---|---|---|
| `BASE_URL` | Public URL (used in emails, redirects) | `https://app.casehub.io` |
| `PREFIX` | Route prefix for all URLs | `/casehub` |
| `PORT` | Uvicorn bind port | `8001` |
| `UPLOAD_DIR` | Override upload directory | `./uploads` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session duration | `480` (8 hours) |
| `COOKIE_NAME` | Auth cookie name | `casehub_token` |

### Database and Cache

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Set by Docker Compose automatically |
| `POSTGRES_DB` | Database name | `casehub` |
| `POSTGRES_USER` | Database user | `casehub` |
| `POSTGRES_PASSWORD` | Database password | **Required** |
| `REDIS_URL` | Redis connection string | Set by Docker Compose automatically |

### Email SMTP (optional but recommended)

| Variable | Description |
|---|---|
| `SMTP_HOST` | SMTP server (e.g., `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (e.g., `587`) |
| `SMTP_USER` | SMTP login email |
| `SMTP_PASS` | SMTP password (for Gmail, use App Password) |
| `SMTP_FROM_NAME` | Display name in From field |

### Optional Integrations (Lite)

| Variable | Feature |
|---|---|
| `WHATSAPP_BOT_URL` | WhatsApp bot service |
| `ESCAVADOR_API_KEY` | Processo search (Escavador) |
| `JUSBRASIL_API_KEY` | JusBrasil consultation |
| `DATAJUD_API_KEY` | CNJ DataJud API |
| `STRIPE_SECRET_KEY` | Payment processing |
| `RESEND_API_KEY` | Transactional email |

### Alerts

| Variable | Description |
|---|---|
| `ALERT_PHONE` | Phone number for SMS alerts |
| `ALERT_WHATSAPP` | WhatsApp number for alerts |
| `GOOGLE_CHAT_WEBHOOK_FEEDBACK` | Google Chat webhook for user feedback |

---

## 5. Docker Build and Start

### Build the Lite image

```bash
cd /opt/casehub

# Build only the Lite image (uses Dockerfile.lite -- much smaller, no ML/NLP)
docker compose build casehub-lite

# Start PostgreSQL, Redis, and CaseHub Lite
docker compose --profile lite up -d
```

This starts three containers:

| Container | Port | Description |
|---|---|---|
| `casehub-db` | 5432 | PostgreSQL 15 |
| `casehub-redis` | 6379 | Redis 7 |
| `casehub-lite` | 8002 -> 8001 | CaseHub Lite (FastAPI/Uvicorn) |

### Verify containers are running

```bash
docker compose --profile lite ps
```

All three should show `Up (healthy)`.

### Check logs

```bash
docker compose logs -f casehub-lite
```

Look for: `Uvicorn running on http://0.0.0.0:8001` and no error tracebacks.

### Test access

```bash
curl http://localhost:8002/casehub/login
```

You should get HTML back. If you get a connection error, check `docker compose logs casehub-lite`.

---

## 6. Database Setup and Seeding

### Migrations

Migrations run **automatically** on container startup. The app calls `init_db()` which creates all tables.

If you need to run migrations manually:

```bash
docker compose exec casehub-lite python -c "from models import init_db; init_db()"
```

### Seed demo data

For a demo/test environment:

```bash
docker compose exec casehub-lite python scripts/seed_demo.py --product lite
```

### Seed client-specific data (o cliente example)

```bash
docker compose exec casehub-lite python scripts/seed_vieira_salles.py
```

### Admin credentials

On first startup, an admin account is created with the email from `ADMIN_EMAIL`. Check the container logs for the auto-generated password:

```bash
docker compose logs casehub-lite | grep -i "admin"
```

> **IMPORTANT**: Change the admin password immediately after first login.

---

## 7. Nginx + HTTPS (SSL)

### Copy the Nginx config

```bash
sudo cp /opt/casehub/deploy/nginx-casehub.conf /etc/nginx/sites-available/casehub
sudo ln -sf /etc/nginx/sites-available/casehub /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
```

### Edit for the client's domain

```bash
sudo nano /etc/nginx/sites-available/casehub
```

Replace all instances of `casehub.app` and `*.casehub.app` with the client's domain:

```nginx
server_name sistema.escritorio.com;
```

Update the upstream port to match the Lite container (8002):

```nginx
upstream casehub_backend {
    server 127.0.0.1:8002;
    keepalive 32;
}
```

Update the static file paths:

```nginx
location /static/ {
    alias /opt/casehub/static/;
    try_files $uri =404;
    access_log off;
    gzip_static on;
    sendfile on;
    etag on;

    set $casehub_static_expires 30d;
    set $casehub_static_cache_control "public, max-age=2592000";
    if ($arg_v != "") {
        set $casehub_static_expires 1y;
        set $casehub_static_cache_control "public, max-age=31536000, immutable";
    }

    expires $casehub_static_expires;
    add_header Cache-Control $casehub_static_cache_control always;
    add_header X-Content-Type-Options "nosniff" always;
}

location /uploads/ {
    alias /opt/casehub/uploads/;
    expires 7d;
}
```

### Test and start Nginx (HTTP only, for certbot)

```bash
sudo nginx -t
sudo systemctl start nginx
sudo systemctl enable nginx
```

### Get SSL certificate with Certbot

```bash
sudo certbot --nginx -d sistema.escritorio.com \
  --agree-tos -m admin@escritorio.com --non-interactive
```

Certbot will:
1. Obtain the certificate from Let's Encrypt
2. Automatically modify the Nginx config to add SSL directives
3. Set up auto-renewal (via systemd timer)

### Verify HTTPS

```bash
curl -I https://sistema.escritorio.com/casehub/login
```

Should return HTTP 200.

### CRITICAL: Static Asset Paths and Mixed Content

**This is the most common deployment issue.**

FastAPI's `url_for('static', path='...')` generates URLs using the internal Docker hostname (e.g., `http://localhost:8001/static/...`). When the site is served over HTTPS, browsers block these as **mixed content**.

**Solution**: All templates must reference static assets with hardcoded `/static/` paths, NOT `url_for('static')`:

```html
<!-- WRONG - generates http://localhost:8001/static/css/style.css -->
<link rel="stylesheet" href="{{ url_for('static', path='css/style.css') }}">

<!-- CORRECT - works behind Nginx/HTTPS -->
<link rel="stylesheet" href="/static/css/style.css">
```

This has already been fixed in the codebase, but if CSS/JS fails to load on HTTPS, check the template files for any remaining `url_for('static')` calls.

### Auto-renewal verification

```bash
sudo certbot renew --dry-run
```

---

## 8. Ollama / Maestro IA (Optional)

Maestro IA provides AI-powered features (document drafting, case analysis). It uses Ollama for local LLM inference -- no external API needed, no per-token cost.

### Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Pull the model

```bash
# Recommended for 4GB+ RAM
ollama pull llama3.2:3b

# For 8GB+ RAM (better quality)
ollama pull llama3.2:8b
```

### Verify Ollama is running

```bash
curl http://localhost:11434/api/tags
```

Should return JSON with available models.

### How it connects

CaseHub Lite connects to Ollama at `http://localhost:11434` by default. Inside Docker, it uses the `host.docker.internal` alias (configured via `extra_hosts` in `docker-compose.yml`).

No additional configuration needed -- if Ollama is running, Maestro IA detects it automatically.

### If Ollama is not installed

Maestro IA falls back gracefully. AI features will show as unavailable but the rest of the application works normally. No errors, no crashes.

### Ollama as a systemd service

Ollama installs its own systemd service automatically. Verify:

```bash
sudo systemctl status ollama
sudo systemctl enable ollama
```

---

## 9. Oracle Cloud Specifics

Oracle Cloud Free Tier provides up to 4 ARM OCPUs + 24GB RAM for free -- ideal for CaseHub Lite.

### Automated provisioning

The repository includes an Oracle Cloud deploy script:

```bash
bash scripts/oracle_deploy.sh
```

This creates a VM.Standard.A1.Flex instance (2 OCPU, 12GB RAM) with Ubuntu 22.04 ARM. It tries multiple regions automatically (sa-vinhedo-1, sa-santiago-1, us-ashburn-1, sa-saopaulo-1).

Requires: `oci-cli` configured with `~/.oci/config`.

### Security List (Firewall)

Oracle Cloud has TWO firewall layers. Both must allow traffic:

**Layer 1: Security List (Oracle Console)**

In the Oracle Cloud Console:
1. Go to Networking > Virtual Cloud Networks > your VCN > Security Lists
2. Add Ingress Rules for ports 22, 80, 443, 8001, 8002

| Source CIDR | Protocol | Port Range |
|---|---|---|
| 0.0.0.0/0 | TCP | 22 |
| 0.0.0.0/0 | TCP | 80 |
| 0.0.0.0/0 | TCP | 443 |
| 0.0.0.0/0 | TCP | 8001-8002 |

**Layer 2: iptables (on the VM)**

Oracle Ubuntu images have iptables rules that BLOCK ports by default, even if the Security List allows them:

```bash
# Open HTTP
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT

# Open HTTPS
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT

# Open CaseHub ports (for debugging, optional if using Nginx)
sudo iptables -I INPUT -p tcp --dport 8001 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 8002 -j ACCEPT

# Save iptables rules to persist across reboots
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

> **GOTCHA**: If the site works via `curl localhost` but not from the browser, it is almost certainly iptables. This catches everyone the first time.

### Free Tier ARM capacity issues

Oracle Free Tier ARM instances are often unavailable due to capacity constraints. The `oracle_deploy.sh` script handles this by trying multiple regions. If all fail:

- Wait 15-30 minutes and try again
- Try at off-peak hours (early morning US time)
- The script will eventually succeed

---

## 10. Backups and Cron Jobs

### Database backup

The backup script is at `scripts/backup_db.sh`. It dumps the database inside the Docker container and compresses it.

```bash
# Make executable
chmod +x /opt/casehub/scripts/backup_db.sh

# Test manually
/opt/casehub/scripts/backup_db.sh

# Check output
ls -la /home/ubuntu/backups/
```

### Set up daily cron

```bash
crontab -e
```

Add these lines:

```cron
# Database backup daily at 3:00 AM UTC (midnight Brasilia)
0 3 * * * cd /opt/casehub && /opt/casehub/scripts/backup_db.sh >> /home/ubuntu/backups/backup.log 2>&1

# Prazo (deadline) alerts daily at 10:00 UTC (7:00 AM Brasilia)
0 10 * * * /opt/casehub/scripts/prazo_alerts_cron.sh >> /home/ubuntu/backups/prazo-alerts.log 2>&1
```

### Backup retention

The backup script automatically deletes backups older than 30 days.

### Manual backup

```bash
# Via deploy.sh
cd /opt/casehub && ./deploy.sh backup

# Direct pg_dump
docker compose exec -T postgres pg_dump -U casehub casehub | gzip > /home/ubuntu/backups/manual_$(date +%Y%m%d).sql.gz
```

### Restore from backup

```bash
# Decompress if needed
gunzip /home/ubuntu/backups/casehub_20260330.sql.gz

# Restore
docker compose exec -T postgres psql -U casehub casehub < /home/ubuntu/backups/casehub_20260330.sql
```

### Off-site backup (recommended)

```bash
# Sync backups to another server
rsync -avz /home/ubuntu/backups/ user@backup-server:/backups/casehub-clientname/

# Or upload to S3-compatible storage
aws s3 sync /home/ubuntu/backups/ s3://bucket/casehub-clientname/
```

### ENCRYPTION_KEY backup

> **CRITICAL**: If you lose the `ENCRYPTION_KEY`, all encrypted PII data (CPF, passport numbers, etc.) is **permanently unrecoverable**. Store the key in a password manager or secure vault separate from the VPS.

---

## 11. Monitoring and Health Checks

### Health endpoint

```bash
curl http://localhost:8002/api/health
```

Response:

```json
{
  "status": "healthy",
  "service": "casehub",
  "product": "lite",
  "version": "2.0.0",
  "checks": {
    "db": true,
    "templates": true
  },
  "response_ms": 12.3
}
```

`status` is either `"healthy"` or `"degraded"`.

### Docker health checks

All containers have built-in health checks:

- **casehub-lite**: `curl -f http://localhost:8001/health`
- **postgres**: `pg_isready`
- **redis**: `redis-cli ping`

```bash
# Check all container health
docker compose --profile lite ps
```

### Log locations

| Log | Location |
|---|---|
| Application | `docker compose logs casehub-lite` |
| Nginx access | `/var/log/nginx/casehub_access.log` |
| Nginx error | `/var/log/nginx/casehub_error.log` |
| Backup | `/home/ubuntu/backups/backup.log` |
| Prazo alerts | `/home/ubuntu/backups/prazo-alerts.log` |
| App feedback | `logs/feedback.jsonl` (inside container, mounted at `./logs/`) |

### External monitoring (recommended)

Point an uptime monitor (UptimeRobot, Hetrix, etc.) at:

```
https://sistema.escritorio.com/api/health
```

Expected: HTTP 200 with `"status": "healthy"`.

---

## 12. Updating the Application

### Standard update

```bash
cd /opt/casehub

# Pull latest code
git pull origin main

# Rebuild the image (ALWAYS rebuild, never just restart)
docker compose build --no-cache casehub-lite

# Restart with new image
docker compose --profile lite up -d

# Verify
docker compose --profile lite ps
curl http://localhost:8002/api/health
```

### Using deploy.sh

```bash
cd /opt/casehub
./deploy.sh update
```

> **WARNING**: `docker compose restart` does NOT pick up code changes. It only restarts the existing container with the old image. You MUST run `docker compose build` to incorporate code updates.

---

## 13. Troubleshooting

### CSS/JS not loading

**Symptom**: Login page appears with no styling, or console shows 404 for static files.

**Cause**: Nginx is not serving the `/static/` directory, or the `alias` path is wrong.

**Fix**:
1. Verify the path in the Nginx config: `alias /opt/casehub/static/;` (trailing slash required)
2. Verify the directory exists: `ls /opt/casehub/static/css/`
3. Reload Nginx: `sudo nginx -t && sudo systemctl reload nginx`

Run the public static smoke before considering the deploy healthy:

```bash
python3 scripts/check_static_assets.py --base https://cliente.example.com
```

If old CSS such as `casehub-theme.css` works but new files such as `tokens.css`
or `themes/_tokens.css` return `404 text/html`, the server is usually serving a
stale static directory or an old Docker image. Confirm the live Nginx `alias`
matches the checkout that received the deploy, and rebuild/recreate the app
container instead of using `docker compose restart`.

For staging environments with self-signed certificates, add `--insecure` to the
static smoke command. Keep certificate verification enabled for production.

### Mixed content blocking (HTTPS)

**Symptom**: Site loads over HTTPS but CSS/JS is blocked. Browser console shows "Mixed Content" errors.

**Cause**: Templates using `url_for('static')` generate `http://` URLs from inside the Docker container.

**Fix**: All static asset references must use relative `/static/` paths, not `url_for('static')`. Search templates for remaining instances:

```bash
grep -r "url_for.*static" templates/
```

### Docker container keeps restarting

```bash
# Check what is crashing
docker compose logs --tail 50 casehub-lite

# Common causes:
# - DATABASE_URL wrong or postgres not healthy yet
# - Missing SECRET_KEY or POSTGRES_PASSWORD in .env
# - Port 8001 already in use inside the container
```

### Cannot connect from browser (Oracle Cloud)

**Symptom**: `curl localhost:8002` works, but browser at `http://VPS_IP:8002` times out.

**Fix**: Open iptables (see [Section 9](#9-oracle-cloud-specifics)):

```bash
sudo iptables -I INPUT -p tcp --dport 8002 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Also verify the Oracle Security List has the port open.

### Database connection errors

```bash
# Check if postgres is running
docker compose ps postgres

# Check postgres logs
docker compose logs postgres

# Test connection from inside the app container
docker compose exec casehub-lite python -c "from models import get_db; print('DB OK')"
```

### Certbot fails

**Symptom**: `certbot --nginx` returns an error.

Common causes:
- DNS not propagated yet (wait 1-24 hours after setting A record)
- Port 80 not open in firewall/iptables
- Nginx not running or misconfigured

```bash
# Verify DNS
dig +short sistema.escritorio.com
# Should return the VPS IP

# Verify port 80 is reachable
curl -I http://sistema.escritorio.com/
```

### Rate limiting (429 errors)

Nginx rate limits:
- **Login**: 5 requests/minute per IP (burst 3)
- **API**: 30 requests/second per IP (burst 50)

Application-level rate limits:
- **Pages**: 120 requests/minute
- **API**: 60 requests/minute

If a client is being rate-limited during normal use, check if a bot or misconfigured integration is hitting the server.

### Ollama not responding

```bash
# Check if running
sudo systemctl status ollama

# Restart
sudo systemctl restart ollama

# Test
curl http://localhost:11434/api/tags
```

If Ollama is down, Maestro IA features are simply unavailable. The rest of the app continues working normally.

### Docker disk space

```bash
# Check disk usage
df -h

# Clean old Docker images and build cache
docker system prune -a --volumes
```

> **WARNING**: `docker system prune --volumes` deletes data volumes. Only use if you have a database backup.

---

## 14. Known Issues and Gotchas

### url_for('static') generates internal URLs

FastAPI's `url_for('static', path='...')` resolves to the internal Docker hostname (e.g., `http://localhost:8001`). Behind Nginx/HTTPS, this causes mixed content blocking. All templates must use `/static/` paths directly. This is already fixed in the codebase but is the first thing to check if CSS breaks after deployment.

### docker restart does NOT update code

`docker compose restart` only stops and starts the existing container. It does NOT rebuild the image. If you changed code, you MUST run:

```bash
docker compose build --no-cache casehub-lite
docker compose --profile lite up -d
```

### Oracle iptables blocks everything by default

Oracle Cloud Ubuntu images ship with iptables rules that drop all inbound traffic except SSH. You must explicitly open ports 80, 443, and any others you need. The Security List in the Oracle Console is a separate layer -- both must allow the traffic.

### DNS propagation delay

After pointing a domain to the VPS IP, it can take 1-24 hours for DNS to propagate globally. During this time, certbot will fail. Use `dig +short domain.com` to check propagation.

### sentence-transformers removed

The `requirements-lite.txt` does not include `sentence-transformers` or other ML libraries. This saves approximately 4GB in the Docker image. If you accidentally use the main `Dockerfile` instead of `Dockerfile.lite`, the image will be much larger and slower to build.

### Lite container maps to port 8002

The `casehub-lite` service maps port `8002` on the host to `8001` inside the container. The Nginx upstream must point to `127.0.0.1:8002`, not `8001`.

### ENCRYPTION_KEY is irreversible

If the `ENCRYPTION_KEY` is lost or changed, all encrypted fields (CPF, passport numbers, alien numbers) become permanently unreadable. Back it up immediately after deployment.

### PostgreSQL data lives in a Docker volume

The database is stored in the `postgres_data` Docker volume, NOT on the host filesystem by default. Running `docker compose down -v` **destroys the database**. Always use `docker compose down` (without `-v`) for normal stops.

### Container startup order

CaseHub Lite depends on PostgreSQL and Redis being healthy before starting (configured via `depends_on` with `condition: service_healthy`). If postgres takes too long to initialize (first run), the app container may restart once or twice before succeeding. This is normal.

### Free Tier ARM capacity (Oracle)

Oracle's free ARM instances are allocated on a best-effort basis. You may get "Out of host capacity" errors. The `scripts/oracle_deploy.sh` tries multiple regions. Keep retrying at different times of day.

---

## Quick Reference: Full Deployment Checklist

```
[ ] 1. SSH into VPS
[ ] 2. apt update && apt upgrade
[ ] 3. Install Docker, Git, Nginx, Certbot
[ ] 4. Clone repo to /opt/casehub
[ ] 5. cp .env.example .env && edit .env
[ ] 6. docker compose build casehub-lite
[ ] 7. docker compose --profile lite up -d
[ ] 8. Verify: curl http://localhost:8002/casehub/login
[ ] 9. Configure Nginx (copy config, edit domain, set port 8002)
[ ] 10. sudo nginx -t && sudo systemctl start nginx
[ ] 11. sudo certbot --nginx -d domain.com
[ ] 12. Verify HTTPS: curl https://domain.com/casehub/login
[ ] 13. Seed data if needed
[ ] 14. Set up cron (backup + prazo alerts)
[ ] 15. (Optional) Install Ollama + pull model
[ ] 16. (Oracle only) Open iptables + Security List
[ ] 17. Back up ENCRYPTION_KEY to password manager
[ ] 18. Change admin password
[ ] 19. Set up external uptime monitor
[ ] 20. Done!
```
