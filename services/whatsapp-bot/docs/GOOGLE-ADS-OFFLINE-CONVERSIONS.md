# Google Ads - Complete Lead & Conversion Flow

## Overview

```
LEAD CLICKS GOOGLE AD
        |
        v
  Landing Page (immigrant.law/en/ or /en/free/)
  * gclid automatically captured from URL
  * Stored in browser localStorage
        |
        v
  FILLS OUT ELEMENTOR FORM
  * gclid injected as hidden field on submit
  * UTM params also captured
        |
        v
  WEBHOOK: POST /webhook/form (whatsapp-bot server)
  * Extracts: name, email, phone, message, gclid, UTMs
  * Calculates lead score
        |
        +-----> MOSKIT CRM (contact + deal created)
        |
        +-----> CASEHUB CRM (via /api/leads/webhook)
        |
        +-----> EMAIL NOTIFICATION (team notified)
        |
        +-----> CONVERSION TRACKING
                  |
                  +---> Google Ads API (Offline Conversion Upload)
                  |     * Uses gclid + hashed email/phone
                  |     * Google uses this to optimize bidding
                  |
                  +---> Facebook CAPI (Conversions API)
                        * Sends "Lead" event with hashed user data
```

---

## 1. Leads Arrive Automatically

### Where leads show up:

| Destination | Status | How |
|-------------|--------|-----|
| **Moskit CRM** | WORKING | Contact + Deal auto-created via API |
| **CaseHub** | WORKING | Dual-write via webhook `/api/leads/webhook` |
| **Email** | WORKING | Notification sent to team |
| **Notion** | NOT automatic | Notion only receives client emails, not form leads |

### Technical flow:
- File: `/var/www/immigrant.law/whatsapp-bot/server.js` (endpoint `/webhook/form`)
- Moskit: `/var/www/immigrant.law/whatsapp-bot/moskit.js` (createMoskitContact + createDeal)
- CaseHub: `/var/www/immigrant.law/whatsapp-bot/crm-sync.js` (sendToCRM)

---

## 2. SMS (CallHippo)

| Item | Status | Details |
|------|--------|---------|
| **Number** | +1 (442) 219-7512 | CallHippo number for SMS |
| **Webhook** | `/api/callhippo-webhook` | Receives inbound SMS |
| **Auto-reply** | ACTIVE | Automatic response to inbound SMS |
| **Lead -> Moskit** | ACTIVE | Inbound SMS creates lead in Moskit (source: "Google Ads Miami") |
| **Signatures** | NEEDS FIX | Logs show "Invalid signature" - needs to be resolved with CallHippo |

### CallHippo config (env vars):
```
CALLHIPPO_API_KEY=***
CALLHIPPO_FROM=+14422197512
CALLHIPPO_TO=+17272751816
CALLHIPPO_EMAIL=info@immigrant.law
CALLHIPPO_WEBHOOK_SECRET=***
```

---

## 3. Google Ads Offline Conversion Upload

### What it does:
When a Google Ads lead converts (schedules consultation, pays), we send that data back to Google. This way Google knows which clicks generated real clients and **automatically optimizes the campaign bidding**.

### Tracked events:

| Event | When it fires | Value | Env Var |
|-------|--------------|-------|---------|
| `lead` | Form submitted on site | $10 | GOOGLE_ADS_CONVERSION_LEAD |
| `consultation_scheduled` | Scheduled consultation | $50 | GOOGLE_ADS_CONVERSION_CONSULTATION |
| `payment_completed` | Paid $99 | $99 | GOOGLE_ADS_CONVERSION_PURCHASE |
| `qualified_lead` | High lead score | $25 | GOOGLE_ADS_CONVERSION_QUALIFIED |

### Current status:
- **Facebook CAPI**: ACTIVE (token and pixel configured)
- **Google Ads API**: CODE READY, needs credentials configured

---

## 4. What Alona Needs to Do

### Step 1: Create Conversion Actions in Google Ads
1. Go to Google Ads > Goals > Conversions > New conversion action
2. Type: "Import" > "Other data sources or CRMs"
3. Create 4 actions:
   - **Lead** (value $10)
   - **Consultation Scheduled** (value $50)
   - **Purchase** (value $99)
   - **Qualified Lead** (value $25)
4. Note down the resource name for each one (format: `customers/17815070319/conversionActions/XXXXXXXX`)

### Step 2: Set Up Google Ads API Access
1. **Developer Token**: Go to Google Ads > Tools & Settings > API Center > Request token
2. **OAuth2 Credentials**: Google Cloud Console > APIs & Services > Credentials
   - Create OAuth2 Client ID (type: Desktop app)
   - Note down client_id and client_secret
3. **Refresh Token**: Use OAuth2 Playground or a script to generate it
   - Scope: `https://www.googleapis.com/auth/adwords`

### Step 3: Send Us These Values
Once you have the credentials, send them to the dev team:

```
GOOGLE_ADS_DEVELOPER_TOKEN=your_token
GOOGLE_ADS_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_ADS_CLIENT_SECRET=your_client_secret
GOOGLE_ADS_REFRESH_TOKEN=your_refresh_token
GOOGLE_ADS_CUSTOMER_ID=17815070319
GOOGLE_ADS_LOGIN_CUSTOMER_ID=  (only if using MCC account)

# Conversion Actions (fill in with resource names from Step 1):
GOOGLE_ADS_CONVERSION_LEAD=customers/17815070319/conversionActions/XXXXXXXX
GOOGLE_ADS_CONVERSION_CONSULTATION=customers/17815070319/conversionActions/XXXXXXXX
GOOGLE_ADS_CONVERSION_PURCHASE=customers/17815070319/conversionActions/XXXXXXXX
GOOGLE_ADS_CONVERSION_QUALIFIED=customers/17815070319/conversionActions/XXXXXXXX
```

### Step 4: We Activate It
Once we receive the credentials:
```bash
# Add to .env on VPS
# Restart service
pm2 restart whatsapp-bot

# Verify it's working:
pm2 logs whatsapp-bot --lines 20 --nostream | grep GADS
# Expected: [GADS] Google Ads Offline Conversions ACTIVE
```

---

## 5. Frontend Tracking (GTM/gtag)

### Configured by Alona in GTM:
- **Main tag**: AW-17815070319 (gtag.js loaded on site)
- **GTM container**: GTM-MHSR6PNR
- **Primary conversion**: Form submission
- **Secondary microconversion**: WhatsApp button click

### gclid Capture (frontend):
- **File**: `/var/www/immigrant.law/wp-content/mu-plugins/ilc-gclid-capture.php`
- **What it does**: Captures gclid from URL, saves in localStorage, injects into Elementor forms
- **Persistence**: gclid persists across pages (localStorage)

---

## 6. Failed Conversions Queue

If the Google Ads API is not configured or returns an error, conversions are saved to:
```
/var/www/immigrant.law/whatsapp-bot/data/failed-conversions.json
```

Once credentials are configured, retry failed conversions:
```bash
cd /var/www/immigrant.law/whatsapp-bot
node -e "const ct = require('./conversion-tracking'); ct.retryFailedConversions().then(r => console.log(r))"
```

---

## 7. Quick Status Check

### Via code:
```bash
cd /var/www/immigrant.law/whatsapp-bot
node -e "const ct = require('./conversion-tracking'); console.log(JSON.stringify(ct.getStatus(), null, 2))"
```

### Quick checklist:
```bash
# Google Tag on site?
curl -s https://immigrant.law/en/ | grep -o 'AW-[0-9]*'
# Expected: AW-17815070319

# Facebook CAPI active?
pm2 logs whatsapp-bot --lines 50 --nostream | grep "Facebook CAPI"
# Expected: [OK] Conversion Tracking active (Facebook CAPI)

# Webhook working?
curl -s -X POST https://immigrant.law/webhook/form \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test","email":"test@test.com","phone":"3051234567","message":"test"}'
# Expected: {"success":true,...}

# gclid capture on frontend?
curl -s https://immigrant.law/en/ | grep 'ilc_gclid'
# Expected: JavaScript capture code present
```

---

## 8. Key Files

| File | Description |
|------|-------------|
| `/var/www/immigrant.law/whatsapp-bot/conversion-tracking.js` | Main module (Google Ads API + Facebook CAPI) |
| `/var/www/immigrant.law/whatsapp-bot/server.js` | Webhook `/webhook/form` (receives leads) |
| `/var/www/immigrant.law/whatsapp-bot/moskit.js` | Moskit CRM integration |
| `/var/www/immigrant.law/whatsapp-bot/crm-sync.js` | Dual-write to CaseHub |
| `/var/www/immigrant.law/whatsapp-bot/callhippo.js` | CallHippo SMS integration |
| `/var/www/immigrant.law/wp-content/mu-plugins/ilc-gclid-capture.php` | Frontend: gclid capture |
| `/var/www/immigrant.law/whatsapp-bot/data/failed-conversions.json` | Failed conversions queue |

---

## 9. Summary: What Works vs What's Missing

| Item | Status | Action Needed |
|------|--------|---------------|
| Form leads -> Moskit | OK | None |
| Form leads -> CaseHub | OK | None |
| Form leads -> Email notification | OK | None |
| Facebook CAPI | OK | None |
| Google Tag frontend (gtag) | OK | None |
| GTM conversions (form submit / WA click) | OK (Alona configured) | None |
| gclid capture (frontend) | OK (mu-plugin) | None |
| gclid capture (webhook) | OK (server.js v11.1) | None |
| **Google Ads Offline Conversions API** | CODE READY | **Needs: Alona's API credentials (see Section 4)** |
| **SMS CallHippo -> Moskit** | PARTIAL | **Needs: fix webhook signatures with CallHippo** |
| Form leads -> Notion | Not implemented | Decide if needed |

---

*Updated: Feb 10, 2026*
*Module: conversion-tracking.js v2.0*
