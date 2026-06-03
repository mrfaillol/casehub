# CaseHub White-Label -- Tenant Configuration Guide

> Version 2.0 | Last updated: 2026-03-25

This guide covers how to create and configure a new tenant (organization) in CaseHub White-Label.

---

## 1. Creating an Organization

### Via SQL

Insert a row into the `organizations` table:

```sql
INSERT INTO organizations (
    uuid, name, slug, domain,
    email, phone, website,
    product_type, plan, case_prefix, currency,
    timezone, locale,
    is_active
) VALUES (
    uuid_generate_v4(),
    'Acme Legal Group',
    'acme',                              -- URL slug: acme.casehub.app
    NULL,                                -- Custom domain (set later)
    'contact@acmelegal.com',
    '+1-555-0100',
    'https://acmelegal.com',
    'immigration',                       -- or 'lite'
    'professional',                      -- starter | professional | enterprise
    'ALG',                               -- Case number prefix: ALG-2026-0001
    'USD',
    'America/New_York',
    'en',                                -- or 'pt-BR' for Lite clients
    TRUE
);
```

### Via Superadmin Panel

Navigate to `/casehub/superadmin/organizations` (requires superadmin role) to create and manage organizations through the web interface.

### Via API

```bash
curl -X POST https://app.casehub.io/api/v1/organizations \
  -H "Authorization: Bearer <superadmin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Legal Group",
    "slug": "acme",
    "email": "contact@acmelegal.com",
    "product_type": "immigration",
    "plan": "professional"
  }'
```

---

## 2. Setting Branding

Each organization can customize its visual identity.

### Database Fields

| Field | Description | Example |
|---|---|---|
| `logo_url` | URL to the organization logo (header, login page) | `/uploads/orgs/acme/logo.png` |
| `favicon_url` | URL to the favicon | `/uploads/orgs/acme/favicon.ico` |
| `primary_color` | Hex color for buttons, links, active states | `#1a56db` |
| `secondary_color` | Hex color for accents and highlights | `#7c3aed` |
| `name` | Displayed in the header, emails, and documents | `Acme Legal Group` |

### Updating Branding

```sql
UPDATE organizations SET
    logo_url = '/uploads/orgs/acme/logo.png',
    favicon_url = '/uploads/orgs/acme/favicon.ico',
    primary_color = '#0d4f8b',
    secondary_color = '#e67e22'
WHERE slug = 'acme';
```

Or use the Branding settings page at `/casehub/settings/branding` (admin role required).

### Logo Requirements

- **Format**: PNG or SVG recommended (transparent background).
- **Size**: Maximum 500x200px for the header logo.
- **Favicon**: 32x32 or 64x64 ICO/PNG.
- **Upload location**: Place files in `uploads/orgs/<slug>/` on the server.

---

## 3. Configuring a Custom Domain

By default, tenants are accessed via subdomain: `acme.casehub.app`. To use a custom domain:

### Step 1: Update the Organization

```sql
UPDATE organizations SET domain = 'cases.acmelegal.com' WHERE slug = 'acme';
```

### Step 2: DNS Configuration

The client must create a DNS record:

| Type | Name | Value |
|---|---|---|
| CNAME | `cases` | `casehub.app` |

Or for apex domains, an A record pointing to the server IP.

### Step 3: Nginx Server Block

Add a server block for the custom domain (see `deploy/nginx-casehub.conf` for the template):

```nginx
server {
    listen 443 ssl http2;
    server_name cases.acmelegal.com;

    ssl_certificate /etc/letsencrypt/live/cases.acmelegal.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cases.acmelegal.com/privkey.pem;

    location / {
        proxy_pass http://casehub_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Step 4: SSL Certificate

```bash
sudo certbot certonly --nginx -d cases.acmelegal.com
sudo nginx -t && sudo systemctl reload nginx
```

### Step 5: Clear Tenant Cache

The TenantMiddleware caches domain-to-org mappings. After adding a custom domain, restart the app or call the cache clear endpoint.

---

## 4. Setting Up Email (SMTP per Tenant)

Each organization can use its own SMTP server for outbound emails.

### Database Fields

| Field | Description | Default |
|---|---|---|
| `smtp_host` | SMTP server hostname | Falls back to global `SMTP_HOST` |
| `smtp_port` | SMTP server port | `587` |
| `smtp_user` | SMTP username/email | Falls back to global `SMTP_USER` |
| `smtp_pass` | SMTP password | Falls back to global `SMTP_PASS` |
| `smtp_from_name` | Display name in From header | Falls back to org `name` |

### Configuration

```sql
UPDATE organizations SET
    smtp_host = 'smtp.gmail.com',
    smtp_port = 587,
    smtp_user = 'noreply@acmelegal.com',
    smtp_pass = 'app-password-here',
    smtp_from_name = 'Acme Legal Group'
WHERE slug = 'acme';
```

### Gmail Configuration

For Gmail SMTP, the tenant must:

1. Enable 2FA on their Google account.
2. Generate an App Password at https://myaccount.google.com/apppasswords.
3. Use the App Password as `smtp_pass` (not the account password).

### Email Resolution

The system resolves email settings in this order:

1. Per-org SMTP fields in `organizations` table.
2. Global SMTP settings from `.env` (fallback).

The `from_email` property on the Organization model constructs the formatted sender: `"Acme Legal Group <noreply@acmelegal.com>"`.

---

## 5. Enabling/Disabling Features via Feature Flags

### Feature Resolution

Features are resolved in this order:

1. **Plans table** -- `SELECT features FROM plans WHERE name = :plan_name`.
2. **Organization `features` JSON column** -- per-org overrides.
3. **Hardcoded fallback** -- based on plan name.

### Plan-Level Features

| Plan | Features |
|---|---|
| `starter` | Core features only (cases, clients, documents, tasks, billing, etc.) |
| `professional` | Core + product-specific (USCIS/eFiling for immigration, PJE/tribunais for lite) + AI + CRM + WhatsApp |
| `enterprise` | Everything in professional + custom domain + API access + priority support |

### Per-Organization Feature Overrides

Use the `features` JSON column to enable or disable specific features for an org:

```sql
-- Enable AI letter generation for a starter-plan org
UPDATE organizations SET
    features = '["ai_lor", "ai_ps"]'::jsonb
WHERE slug = 'acme';

-- Or as a key-value map (also supported)
UPDATE organizations SET
    features = '{"ai_lor": true, "whatsapp": false}'::jsonb
WHERE slug = 'acme';
```

### Available Feature Keys

**Core features** (all plans):

```
cases, clients, documents, drive_sync, email, tasks, billing, calendar,
contacts, notes, reports, workflow, triggers, deadlines, versions,
signatures, doc_templates, notifications, audit, two_factor, sso,
custom_fields, webhooks, portal, invoices, payments, team_chat,
legal_assistant, communications, branding, onboarding
```

**Immigration features**:

```
uscis, uscis_forms, uscis_status, efiling, case_wizard, packets,
shipments, intake, case_archive, ilc_tools, lor_maker, ps_maker,
package_builder
```

**Lite features**:

```
pje, tribunais, prazos, oab
```

**Premium features**:

```
ai_lor, ai_ps, crm, whatsapp, custom_domain, api_access, priority_support
```

### Enforcing Feature Gates in Routes

```python
from middleware.features import require_feature

@router.post("/ai/lor/generate")
async def generate_lor(
    request: Request,
    _f=Depends(require_feature("ai_lor")),
    db: Session = Depends(get_db),
):
    # Only reachable if the org's plan includes "ai_lor"
    ...
```

Returns HTTP 402 (Payment Required) with a message prompting a plan upgrade.

---

## 6. Product Type Selection

The `product_type` field on the organization determines which features are available:

| Product Type | Target Market | Key Modules |
|---|---|---|
| `immigration` | US immigration law firms | USCIS forms, case status tracking, eFiling, intake, packets, shipments |
| `lite` | General law firms (Brazil focus) | PJE integration, tribunal tracking, OAB, prazos |

### Setting Product Type

```sql
UPDATE organizations SET product_type = 'lite' WHERE slug = 'acme';
```

The product type is also used at the application level via the `CASEHUB_PRODUCT` environment variable, which determines which router modules are loaded. For multi-tenant deployments serving both product types, run `CASEHUB_PRODUCT=immigration` (loads all routers) and rely on the `require_product()` dependency to hide immigration-specific endpoints from lite orgs.

---

## 7. Subscription Plan Configuration

### Database Fields

| Field | Description | Default |
|---|---|---|
| `plan` | Plan name: `starter`, `professional`, `enterprise` | `starter` |
| `max_users` | Maximum user accounts | 5 |
| `max_clients` | Maximum client records | 100 |
| `max_storage_gb` | Maximum file storage in GB | 10 |
| `stripe_customer_id` | Stripe customer ID | NULL |
| `stripe_subscription_id` | Stripe subscription ID | NULL |
| `subscription_status` | Status: `active`, `past_due`, `canceled`, `trialing` | `active` |

### Setting Plan Limits

```sql
UPDATE organizations SET
    plan = 'professional',
    max_users = 25,
    max_clients = 1000,
    max_storage_gb = 50
WHERE slug = 'acme';
```

### Limit Enforcement

The `check_org_limits()` function verifies whether an org has reached its quota:

```python
from models.tenant import check_org_limits

if not check_org_limits(db, org, Client):
    raise HTTPException(403, "Client limit reached. Upgrade your plan.")
```

Currently enforced for `users` and `clients` tables. Storage limits are checked at the upload layer.

### Stripe Integration

For automated billing:

1. Create a Stripe customer for the org.
2. Set `stripe_customer_id` and `stripe_subscription_id`.
3. Configure the Stripe webhook to point to `/casehub/payments/webhook`.
4. Set `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, and `STRIPE_WEBHOOK_SECRET` in `.env`.

The `routes/subscription.py` and `services/stripe_service.py` modules handle plan changes, invoice generation, and webhook processing.

---

## 8. Google Drive Integration per Tenant

Each organization can connect its own Google Drive for document storage.

### Database Fields

| Field | Description |
|---|---|
| `google_drive_root_id` | Root folder ID in Drive (e.g., the "Active Clients" folder) |
| `google_credentials_path` | Path to the OAuth2 credentials JSON for this org |

### Setup Steps

1. **Create a Google Cloud project** for the tenant (or use a shared one).
2. **Enable the Google Drive API**.
3. **Create OAuth2 credentials** (Desktop App type).
4. **Download the credentials JSON** and place it on the server.
5. **Run the initial auth flow** to generate a token:

```bash
python3 complete_google_auth.py --credentials /path/to/credentials.json
```

6. **Update the organization record**:

```sql
UPDATE organizations SET
    google_drive_root_id = '1ABC123...',
    google_credentials_path = '/opt/casehub/credentials/acme_drive.json'
WHERE slug = 'acme';
```

### How Drive Sync Works

- When a client is created, CaseHub creates a subfolder under the org's root Drive folder.
- Documents uploaded to CaseHub are synced to the client's Drive folder.
- The `drive_folder_id` on the Client model stores the Google Drive folder ID.
- Sync is handled by `services/google_drive_handler.py` and `services/document_sync.py`.

### Global vs Per-Org Drive

- **Global**: Set `GOOGLE_DRIVE_ROOT_ID` and `GOOGLE_DRIVE_CREDENTIALS_PATH` in `.env`. Used for all orgs without their own Drive config.
- **Per-org**: Set `google_drive_root_id` and `google_credentials_path` on the Organization record. Overrides the global config.

---

## 9. Creating the First Admin User

When the app starts, if no user with the `ADMIN_EMAIL` exists, it auto-creates one:

```
Default admin user created: admin@acmelegal.com / <random-16-char-password> (must change on first login)
```

The password is printed to stdout (visible in `pm2 logs` or `docker compose logs`). The user is forced to change it on first login (`must_change_password = True`).

### Creating Additional Users

Use the Admin panel at `/casehub/admin/users` to create users with roles:

- `admin` -- Full administrative access.
- `attorney` -- Case and billing management.
- `paralegal` / `case_worker` -- Case editing and document management.
- `assistant` -- Read-only access with task management.

Each user is scoped to their organization via the `org_id` foreign key.

---

## 10. Tenant Onboarding Checklist

Use this checklist when setting up a new tenant:

- [ ] Create the Organization record (name, slug, email, product_type, plan).
- [ ] Set branding (logo, colors, favicon).
- [ ] Configure SMTP (or verify global SMTP is acceptable).
- [ ] Set plan limits (max_users, max_clients, max_storage_gb).
- [ ] Start the app and note the auto-generated admin password.
- [ ] Log in and change the admin password.
- [ ] (Optional) Configure custom domain + SSL.
- [ ] (Optional) Set up Google Drive integration.
- [ ] (Optional) Connect Stripe for automated billing.
- [ ] (Optional) Enable additional features via feature flags.
- [ ] (Optional) Set up WhatsApp bot for the tenant.
- [ ] Verify by logging in at `https://<slug>.casehub.app/casehub/login`.
