# CaseHub API Reference

> **Base URL:** `https://<your-domain>/casehub`
>
> **API Version:** v1
>
> **Last Updated:** 2026-03-25

---

## Table of Contents

1. [Authentication](#authentication)
2. [Common Patterns](#common-patterns)
3. [REST API Endpoints (api/v1)](#rest-api-endpoints)
   - [Dashboard](#dashboard)
   - [Clients](#clients)
   - [Cases](#cases)
   - [Tasks](#tasks)
   - [Documents](#documents)
   - [Users](#users)
   - [Lookup / Reference Data](#lookup--reference-data)
4. [Document Management API](#document-management-api)
   - [Document CRUD](#document-crud)
   - [Approval Workflow](#approval-workflow)
   - [Google Drive Sync](#google-drive-sync)
   - [Admin Endpoints](#admin-endpoints)
5. [Notifications API](#notifications-api)
6. [Webhooks](#webhooks)
7. [HTML Routes (Server-Rendered)](#html-routes-server-rendered)
8. [Error Handling](#error-handling)
9. [Rate Limiting](#rate-limiting)
10. [Code Examples](#code-examples)

---

## Authentication

CaseHub supports two authentication methods:

### 1. Bearer Token (API)

Obtain a JWT token by posting credentials to the login endpoint, then include it in the `Authorization` header.

**Login:**

```
POST /casehub/api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

email=user@example.com&password=secretpass
```

**Response:**

```json
{
  "access_token": "ACCESS_TOKEN_EXAMPLE",
  "refresh_token": "REFRESH_TOKEN_EXAMPLE",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": 1,
    "name": "John Doe",
    "email": "user@example.com",
    "user_type": "admin"
  }
}
```

Use the access token in subsequent requests:

```
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
```

- **Access token lifetime:** 30 minutes
- **Refresh token lifetime:** 7 days
- **Algorithm:** HS256

### 2. Cookie Authentication (Browser)

When logged in via the web UI, a `casehub_token` cookie is set. API endpoints also accept this cookie as authentication. This is primarily used by the frontend JavaScript.

### Token Refresh

```
POST /casehub/auth/refresh

# Via cookie: casehub_refresh cookie is read automatically
# Via JSON body:
Content-Type: application/json
{"refresh_token": "REFRESH_TOKEN_EXAMPLE"}
```

Returns a new access token.

---

## Common Patterns

### Pagination

List endpoints support pagination via query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip` | int | 0 | Number of records to skip (offset) |
| `limit` | int | 50 | Number of records to return (max 100) |

**Response format:**

```json
{
  "total": 142,
  "skip": 0,
  "limit": 50,
  "data": [...]
}
```

### Multi-Tenancy

All data is scoped to the authenticated user's organization (`org_id`). This is handled automatically via the `tenant_query` middleware. You cannot access data from other tenants.

### Date Format

All dates are returned in ISO 8601 format: `"2026-03-25"` (date) or `"2026-03-25T14:30:00"` (datetime). When sending dates, use `YYYY-MM-DD` format.

### PII Encryption

Sensitive client fields (`ssn`, `alien_number`, `passport_number`) are encrypted at rest. The API returns decrypted values automatically for authorized users.

---

## REST API Endpoints

All endpoints under `/api/v1/` require Bearer token or cookie authentication.

**Router prefix:** `/casehub/api/v1`

### Dashboard

#### GET /api/v1/dashboard/stats

Get aggregate dashboard statistics.

**Response:**

```json
{
  "stats": {
    "total_clients": 85,
    "total_cases": 120,
    "active_cases": 67,
    "total_documents": 1543,
    "pending_tasks": 23,
    "overdue_tasks": 5
  },
  "charts": {
    "cases_by_status": {
      "intake": 12,
      "drafting": 8,
      "filed": 30,
      "approved": 45,
      "denied": 5
    },
    "cases_by_visa_type": {
      "EB-2 NIW": 25,
      "H-1B": 18,
      "EB-1A": 12
    }
  }
}
```

---

### Clients

#### GET /api/v1/clients

List all clients with pagination and search.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `skip` | int | Offset (default: 0) |
| `limit` | int | Limit 1-100 (default: 50) |
| `search` | string | Search by first name, last name, email, or phone |
| `status` | string | Filter by status (`active`, `lead`, `archived`, etc.) |

**Response:**

```json
{
  "total": 85,
  "skip": 0,
  "limit": 50,
  "data": [
    {
      "id": 1,
      "first_name": "PessoaDemo",
      "last_name": "Santos",
      "full_name": "PessoaDemo Santos",
      "email": "pessoa_demo@example.com",
      "phone": "+1234567890",
      "whatsapp": "+5511999999999",
      "date_of_birth": "1990-05-15",
      "country_of_origin": "Brazil",
      "ssn": "123-45-6789",
      "alien_number": "A123456789",
      "passport_number": "BR1234567",
      "address": "123 Main St, City, ST 12345",
      "status": "active",
      "notes": "Referred by existing client",
      "created_at": "2026-01-15T10:30:00",
      "updated_at": "2026-03-20T14:00:00"
    }
  ]
}
```

#### GET /api/v1/clients/{client_id}

Get a single client with related cases, documents, and tasks.

**Response:** Client object plus:

```json
{
  "...client fields...",
  "cases": [...],
  "documents": [...],
  "tasks": [...]
}
```

#### POST /api/v1/clients

Create a new client.

**Request Body (JSON):**

```json
{
  "first_name": "PessoaDemo",
  "last_name": "Santos",
  "email": "pessoa_demo@example.com",
  "phone": "+1234567890",
  "whatsapp": "+5511999999999",
  "date_of_birth": "1990-05-15",
  "country_of_origin": "Brazil",
  "ssn": "123-45-6789",
  "alien_number": "A123456789",
  "passport_number": "BR1234567",
  "address": "123 Main St",
  "status": "active",
  "notes": "New client"
}
```

Required fields: `first_name`, `last_name`. All others are optional.

**Response:** Created client object.

#### PUT /api/v1/clients/{client_id}

Update an existing client. Only provided fields are updated.

**Request Body (JSON):** Same as create, all fields optional.

**Response:** Updated client object.

#### DELETE /api/v1/clients/{client_id}

Delete a client.

**Response:**

```json
{"message": "Client deleted successfully"}
```

---

### Cases

#### GET /api/v1/cases

List all cases with pagination and filters.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `skip` | int | Offset (default: 0) |
| `limit` | int | Limit 1-100 (default: 50) |
| `search` | string | Search by case number, case name, or receipt number |
| `status` | string | Filter by status |
| `client_id` | int | Filter by client |
| `visa_type` | string | Filter by visa type |

**Response:**

```json
{
  "total": 120,
  "skip": 0,
  "limit": 50,
  "data": [
    {
      "id": 1,
      "client_id": 1,
      "case_number": "CASE-2026-001",
      "case_name": "Santos EB-2 NIW",
      "receipt_number": "WAC2690012345",
      "visa_type": "EB-2 NIW",
      "status": "filed",
      "priority": "high",
      "application_date": "2026-02-01",
      "processing_date": null,
      "expiration_date": null,
      "case_value": 5000.00,
      "amount_paid": 2500.00,
      "notes": "Strong case",
      "created_at": "2026-01-20T09:00:00",
      "updated_at": "2026-03-15T11:30:00"
    }
  ]
}
```

**Case Statuses:** `intake`, `document_collection`, `drafting`, `review`, `filed`, `rfe`, `approved`, `denied`, `closed`

**Priority Values:** `low`, `medium`, `high`, `urgent`

#### GET /api/v1/cases/{case_id}

Get a single case with client info, documents, tasks, and billing items.

**Response:**

```json
{
  "...case fields...",
  "client": { "...client object..." },
  "documents": [...],
  "tasks": [...],
  "billing_items": [
    {
      "id": 1,
      "description": "Filing fee",
      "amount": 750.00,
      "item_type": "fee",
      "status": "paid",
      "due_date": "2026-02-15"
    }
  ]
}
```

#### POST /api/v1/cases

Create a new case.

**Request Body (JSON):**

```json
{
  "client_id": 1,
  "case_number": "CASE-2026-002",
  "case_name": "Santos H-1B",
  "receipt_number": null,
  "visa_type": "H-1B",
  "status": "intake",
  "priority": "medium",
  "application_date": "2026-04-01",
  "processing_date": null,
  "expiration_date": null,
  "case_value": 3000.00,
  "notes": "Employer: ACME Corp"
}
```

Required fields: `client_id`. Returns 404 if client does not exist.

**Response:** Created case object.

#### PUT /api/v1/cases/{case_id}

Update an existing case.

**Response:** Updated case object.

#### DELETE /api/v1/cases/{case_id}

Delete a case.

**Response:** `{"message": "Case deleted successfully"}`

---

### Tasks

#### GET /api/v1/tasks

List all tasks with pagination and filters.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `skip` | int | Offset (default: 0) |
| `limit` | int | Limit 1-100 (default: 50) |
| `status` | string | Filter by status (`todo`, `in_progress`, `completed`) |
| `case_id` | int | Filter by case |
| `client_id` | int | Filter by client |
| `assigned_to` | int | Filter by assigned user ID |
| `priority` | string | Filter by priority |

**Response:**

```json
{
  "total": 23,
  "skip": 0,
  "limit": 50,
  "data": [
    {
      "id": 1,
      "title": "Collect passport copy",
      "description": "Need certified copy",
      "case_id": 1,
      "client_id": 1,
      "task_type": "document_collection",
      "status": "todo",
      "priority": "high",
      "assigned_to": 2,
      "due_date": "2026-04-01",
      "completed_at": null,
      "created_at": "2026-03-20T10:00:00"
    }
  ]
}
```

#### GET /api/v1/tasks/{task_id}

Get a single task by ID.

#### POST /api/v1/tasks

Create a new task.

**Request Body (JSON):**

```json
{
  "title": "Draft cover letter",
  "description": "For EB-2 NIW petition",
  "case_id": 1,
  "client_id": 1,
  "task_type": "drafting",
  "status": "todo",
  "priority": "high",
  "assigned_to": 2,
  "due_date": "2026-04-05"
}
```

Required fields: `title`.

#### PUT /api/v1/tasks/{task_id}

Update a task. Setting `status` to `"completed"` automatically sets `completed_at`.

#### DELETE /api/v1/tasks/{task_id}

Delete a task.

---

### Documents

#### GET /api/v1/documents

List documents with pagination and filters.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `skip` | int | Offset (default: 0) |
| `limit` | int | Limit 1-100 (default: 50) |
| `case_id` | int | Filter by case |
| `client_id` | int | Filter by client |
| `document_type` | string | Filter by document type |

**Response:**

```json
{
  "total": 1543,
  "skip": 0,
  "limit": 50,
  "data": [
    {
      "id": 1,
      "client_id": 1,
      "case_id": 1,
      "name": "passport_santos.pdf",
      "document_type": "Passport",
      "status": "received",
      "file_path": "/data/uploads/abc123.pdf",
      "file_size": 245760,
      "mime_type": "application/pdf",
      "expiration_date": "2028-05-15",
      "notes": null,
      "uploaded_by": 1,
      "created_at": "2026-03-01T09:15:00"
    }
  ]
}
```

#### GET /api/v1/documents/{document_id}

Get a single document by ID.

---

### Users

#### GET /api/v1/users

List all users in the organization.

**Query Parameters:** `skip`, `limit`

**Response:**

```json
{
  "total": 5,
  "skip": 0,
  "limit": 50,
  "data": [
    {
      "id": 1,
      "name": "Admin User",
      "email": "admin@firm.com",
      "user_type": "admin",
      "enabled": true,
      "created_at": "2025-12-01T00:00:00"
    }
  ]
}
```

---

### Lookup / Reference Data

These endpoints return static reference data. No parameters required.

#### GET /api/v1/lookup/visa-types

```json
{
  "visa_types": [
    "EB-1A", "EB-1B", "EB-1C", "EB-2", "EB-2 NIW", "EB-3",
    "H-1B", "H-2A", "H-2B", "L-1A", "L-1B", "O-1A", "O-1B",
    "F-1", "J-1", "K-1", "K-3",
    "IR-1", "IR-2", "CR-1", "F2A", "F2B",
    "Asylum", "TPS", "DACA", "U Visa", "T Visa",
    "Naturalization", "Green Card Renewal", "Other"
  ]
}
```

#### GET /api/v1/lookup/case-statuses

Returns status objects with `value`, `label`, and `color` fields.

#### GET /api/v1/lookup/task-priorities

Returns priority objects with `value`, `label`, and `color` fields.

#### GET /api/v1/lookup/document-types

Returns list of common document types (Passport, I-94, Visa, Birth Certificate, etc.).

---

## Document Management API

Advanced document management with approval workflows and Google Drive sync.

**Router prefix:** `/casehub/api/documents`

All endpoints require Bearer token or cookie authentication.

### Document CRUD

#### GET /api/documents

List documents with advanced filters.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `client_id` | int | Filter by client |
| `case_id` | int | Filter by case |
| `status` | string | Filter by status (`PENDING_APPROVAL`, `APPROVED`, `REJECTED`) |
| `doc_type` | string | Filter by document type |
| `visa_category` | string | Filter by visa category (`EB1A`, `EB2-NIW`, etc.) |
| `uploaded_via` | string | Filter by upload source (`staff_upload`, `client_portal`, `google_drive`, `drive_share`) |
| `limit` | int | Max results (default: 50, max: 200) |
| `offset` | int | Offset (default: 0) |

**Response:** Array of document objects.

#### GET /api/documents/{doc_id}

Get document details including Drive sync info and classification data.

**Response:**

```json
{
  "id": 1,
  "name": "passport_santos.pdf",
  "doc_type": "Passport",
  "status": "APPROVED",
  "file_size": 245760,
  "mime_type": "application/pdf",
  "client_id": 1,
  "case_id": 1,
  "drive_link": "https://drive.google.com/file/d/abc123/view",
  "visa_category": "EB2-NIW",
  "llm_classified": true,
  "classification_confidence": 0.95,
  "uploaded_via": "client_portal",
  "created_at": "2026-03-01T09:15:00"
}
```

#### PUT /api/documents/{doc_id}

Update document metadata.

**Request Body (JSON):**

```json
{
  "name": "Updated Name.pdf",
  "doc_type": "Passport",
  "status": "APPROVED",
  "visa_category": "EB1A",
  "notes": "Verified"
}
```

#### GET /api/documents/client/{client_id}

Get all documents for a specific client. Optional `status` filter.

#### GET /api/documents/case/{case_id}

Get all documents for a specific case.

#### GET /api/documents/pending

List documents pending approval (status = `PENDING_APPROVAL`).

#### GET /api/documents/stats/summary

Document statistics summary.

**Response:**

```json
{
  "total": 1543,
  "pending_approval": 12,
  "approved": 1400,
  "rejected": 31,
  "by_visa_category": {
    "EB1A": 450,
    "EB2-NIW": 380
  },
  "synced_to_drive": 1200
}
```

### Approval Workflow

#### POST /api/documents/{doc_id}/approve

Approve a pending document. Triggers Google Drive sync and client email notification.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `user_id` | int | Yes | ID of the reviewing user |

**Response:**

```json
{
  "success": true,
  "status": "APPROVED",
  "document_id": 1,
  "drive_sync": {"success": true, "web_link": "https://..."},
  "email_notification": {"success": true}
}
```

#### POST /api/documents/{doc_id}/reject

Reject a pending document with reason.

**Parameters:**

| Parameter | Type | Source | Required | Description |
|-----------|------|--------|----------|-------------|
| `user_id` | int | Query | Yes | ID of the reviewing user |
| `reason` | string | Form | Yes | Rejection reason |

**Response:**

```json
{
  "success": true,
  "status": "REJECTED",
  "document_id": 1,
  "reason": "Image too blurry, please resubmit",
  "email_notification": {"success": true}
}
```

#### POST /api/documents/batch-approve

Approve multiple documents at once.

**Request Body (JSON):** Array of document IDs.

**Query Parameters:** `user_id` (int, required)

**Response:**

```json
{
  "success": true,
  "approved": [1, 2, 3],
  "not_found": [99],
  "total_approved": 3
}
```

### Upload

#### POST /api/documents/upload-local

Upload a document to local storage for processing.

**Form Data:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | The file to upload |
| `client_id` | int | Yes | Client ID |
| `doc_type` | string | No | Document type |

**Response:**

```json
{
  "success": true,
  "document_id": 42,
  "filename": "Santos_PessoaDemo_a1b2c3d4.pdf",
  "message": "File uploaded successfully. Document-watcher will process it shortly."
}
```

#### POST /api/documents/share-from-drive

Share a Google Drive file with a client via the portal (no download needed).

**Request Body (JSON):**

```json
{
  "client_id": 1,
  "drive_file_id": "1abc123def456",
  "file_name": "approval_notice.pdf",
  "doc_type": "Approval Notice",
  "mime_type": "application/pdf",
  "file_size": 102400
}
```

### Google Drive Sync

#### GET /api/documents/drive/status

Get Google Drive sync statistics.

**Response:**

```json
{
  "total_documents": 1543,
  "synced_to_drive": 1200,
  "hashed_locally": 1500,
  "duplicates_detected": 15,
  "storage_by_visa": [
    {"visa_category": "EB1A", "document_count": 450, "total_size_mb": 2340.50}
  ]
}
```

#### POST /api/documents/drive/sync

Sync documents FROM Google Drive TO CaseHub.

**Request Body (JSON):**

```json
{
  "client_id": 1,
  "skip_existing": true,
  "max_clients": null
}
```

If `client_id` is null, syncs all active clients (bulk operation).

#### POST /api/documents/drive/sync-client/{client_id}

Sync documents for a specific client from Google Drive.

**Query Parameters:** `skip_existing` (bool, default: true)

#### GET /api/documents/drive/all-files

List all files across all client folders in Google Drive (reads directly from Drive API).

#### POST /api/documents/drive/download-to-casehub

Download a specific file from Google Drive and create a Document record.

**Form Data:** `file_id`, `client_id`, `file_name`, `mime_type`, `file_size`

### Admin Endpoints

#### POST /api/documents/admin/reprocess-client-emails/{client_id}

Reprocess emails from a specific client.

**Query Parameters:** `days_back` (int, default: 7, max: 30)

#### POST /api/documents/admin/retry-drive-sync

Retry failed Google Drive syncs.

**Query Parameters:** `max_retries` (int, default: 3, max: 5)

#### POST /api/documents/admin/sync-client-to-drive/{client_id}

Sync all unsynced documents for a client TO Google Drive.

---

## Notifications API

**Router prefix:** `/casehub/notifications`

#### GET /notifications/unread-count

Get unread notification count.

#### GET /notifications/recent

Get recent notifications.

#### POST /notifications/mark-read

Mark notifications as read.

#### POST /notifications/whatsapp-message

Send a WhatsApp notification message.

---

## Webhooks

CaseHub supports outgoing webhooks for entity events. Configure webhooks via the UI (`/casehub/webhooks`) or the form-based API.

### Supported Event Types

| Event | Description |
|-------|-------------|
| `client.created` | New client created |
| `client.updated` | Client data updated |
| `client.deleted` | Client deleted |
| `case.created` | New case created |
| `case.updated` | Case data updated |
| `case.deleted` | Case deleted |
| `case.status_changed` | Case status changed |
| `document.uploaded` | Document uploaded |
| `document.deleted` | Document deleted |
| `task.created` | Task created |
| `task.completed` | Task marked complete |
| `billing.payment_received` | Payment received |

### Webhook Payload Format

All webhook payloads follow this structure:

```json
{
  "event_type": "case.status_changed",
  "entity_type": "case",
  "entity_id": 42,
  "timestamp": "2026-03-25T14:30:00",
  "data": {
    "id": 42,
    "from_status": "filed",
    "to_status": "approved",
    "case_number": "CASE-2026-001"
  }
}
```

### Webhook Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhooks/{webhook_id}/test` | Send a test payload to the webhook URL |
| GET | `/webhooks/{webhook_id}/logs` | View execution history (last 50) |

### Webhook Configuration Fields

| Field | Type | Description |
|-------|------|-------------|
| `entity_type` | string | `client`, `case`, `document`, `task`, `billing` |
| `event_type` | string | One of the supported event types |
| `webhook_url` | string | The URL to POST to |
| `headers` | JSON | Custom headers (e.g., `{"Authorization": "Bearer xyz"}`) |
| `enabled` | bool | Whether the webhook is active |
| `entity_id` | int | Optional: only trigger for a specific entity ID |

### Delivery

- Webhooks are delivered via HTTP POST with `Content-Type: application/json`
- Timeout: 30 seconds
- Failed deliveries are logged with response code and error message
- Consecutive failures increment `failure_count` on the webhook record
- Successful delivery resets `failure_count` to 0

---

## HTML Routes (Server-Rendered)

These routes return HTML pages and are used by the web UI. They use cookie authentication (`casehub_token`). Listed here for completeness.

### Client Management (`/casehub/clients`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/clients` | Client list page |
| GET | `/clients/new` | New client form |
| POST | `/clients/new` | Create client (form) |
| GET | `/clients/{id}` | Client detail page |
| GET | `/clients/{id}/edit` | Edit client form |
| POST | `/clients/{id}/edit` | Update client (form) |
| POST | `/clients/{id}/delete` | Delete client |
| GET | `/clients/{id}/drive-folder` | Get Google Drive folder link (JSON) |
| GET | `/clients/{id}/drive-files` | List client's Drive files (JSON) |

### Case Management (`/casehub/cases`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/cases` | Case list page |
| GET | `/cases/new` | New case form |
| POST | `/cases/new` | Create case (form) |
| GET | `/cases/{id}` | Case detail page |
| GET | `/cases/{id}/edit` | Edit case form |
| POST | `/cases/{id}/edit` | Update case (form) |
| POST | `/cases/{id}/delete` | Delete case |
| POST | `/cases/{id}/status` | Quick status update (supports JSON response) |

### Document Management (`/casehub/documents`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/documents` | Document list / tree view |
| GET | `/documents/upload` | Upload form |
| POST | `/documents/upload` | Upload document (multipart, max 50MB) |
| GET | `/documents/{id}` | Document detail |
| GET | `/documents/{id}/download` | Download file |
| GET | `/documents/{id}/preview` | Inline preview (PDF/image) |
| POST | `/documents/{id}/delete` | Delete document |
| POST | `/documents/{id}/rename` | Rename document (JSON) |
| GET | `/documents/api/by-client/{id}` | Documents by client (JSON, lazy-load) |
| POST | `/documents/bulk/delete` | Bulk delete (JSON) |
| POST | `/documents/bulk/move` | Bulk move to client (JSON) |
| POST | `/documents/bulk/update-type` | Bulk update doc type (JSON) |

**Allowed file extensions:** `.pdf`, `.doc`, `.docx`, `.jpg`, `.jpeg`, `.png`, `.gif`, `.tiff`, `.tif`, `.bmp`, `.xls`, `.xlsx`, `.txt`, `.rtf`, `.csv`, `.zip`, `.rar`, `.msg`, `.eml`

**Max file size:** 50 MB

### Task Management (`/casehub/tasks`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tasks` | Redirects to `/tasks/notion` |
| GET | `/tasks/local` | Local tasks list |
| GET | `/tasks/new` | New task form |
| POST | `/tasks/new` | Create local task |
| GET | `/tasks/{id}` | Task detail |
| GET | `/tasks/{id}/edit` | Edit task form |
| POST | `/tasks/{id}/edit` | Update task |
| POST | `/tasks/{id}/complete` | Mark task complete |
| POST | `/tasks/{id}/delete` | Delete task |

**Notion Integration:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tasks/notion` | Notion tasks view |
| GET | `/tasks/notion/new` | New Notion task form |
| POST | `/tasks/notion/create` | Create task in Notion |
| POST | `/tasks/notion/{page_id}/status` | Update Notion task status (JSON) |
| POST | `/tasks/notion/{page_id}/archive` | Archive Notion task (JSON) |
| GET | `/tasks/api/notion/tasks` | Get Notion tasks (JSON API) |
| GET | `/tasks/api/notion/databases` | Get Notion databases config (JSON) |
| POST | `/tasks/api/notion/task` | Create Notion task (JSON API) |
| PATCH | `/tasks/api/notion/task/{page_id}` | Update Notion task (JSON API) |

### Billing (`/casehub/billing`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/billing` | Billing dashboard |
| GET | `/billing/items/new` | New billing item form |
| POST | `/billing/items/new` | Create billing item |
| GET | `/billing/items/{id}/edit` | Edit billing item form |
| POST | `/billing/items/{id}/edit` | Update billing item |
| POST | `/billing/items/{id}/delete` | Delete billing item |
| POST | `/billing/items/{id}/mark-paid` | Mark item as paid |
| GET | `/billing/time/new` | New time entry form |
| POST | `/billing/time/new` | Create time entry |
| POST | `/billing/time/{id}/delete` | Delete time entry |

### Invoices (`/casehub/invoices`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/invoices` | Invoice list |
| GET | `/invoices/new` | New invoice form |
| POST | `/invoices/new` | Create invoice |
| GET | `/invoices/{number}` | View invoice |
| GET | `/invoices/{number}/print` | Printable invoice |
| GET | `/invoices/{number}/pdf` | Download invoice PDF |
| POST | `/invoices/{number}/mark-paid` | Mark invoice paid |
| POST | `/invoices/{number}/send` | Send invoice via email (JSON) |

### Other Route Modules

| Prefix | Description |
|--------|-------------|
| `/admin` | Admin panel |
| `/alerts` | Alert management |
| `/audit` | Audit log |
| `/branding` | White-label branding settings |
| `/calendar` | Calendar / scheduling |
| `/checklist` | Document checklists |
| `/communications` | Communication hub |
| `/contacts` | Contact management |
| `/custom-fields` | Custom field definitions |
| `/deadlines` | Deadline tracking |
| `/efiling` | E-filing management |
| `/emails` | Email integration |
| `/intake` | Client intake forms |
| `/leads` | Lead management |
| `/letters` | Letter generation |
| `/messaging-hub` | Messaging hub |
| `/notes` | Case/client notes |
| `/onboarding` | Client onboarding |
| `/packets` | Document packets |
| `/payments` | Payment processing |
| `/portal` | Client portal management |
| `/processes` | Process/workflow management |
| `/questionnaires` | Client questionnaires |
| `/referrals` | Referral tracking |
| `/reports` | Reporting |
| `/settings` | System settings |
| `/signatures` | E-signatures |
| `/sso` | Single sign-on (Google/Microsoft) |
| `/subscription` | Subscription management |
| `/superadmin` | Super admin panel |
| `/templates` | Document templates |
| `/tickets` | Support tickets |
| `/triggers` | Automation triggers |
| `/uscis` | USCIS status tracking |
| `/versions` | Version management |
| `/whatsapp` | WhatsApp integration |
| `/workflow` | Workflow automation |

---

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 302 | Redirect (HTML routes after form submission) |
| 400 | Bad request (invalid parameters, disallowed file type) |
| 401 | Not authenticated |
| 404 | Resource not found |
| 413 | File too large (exceeds 50MB limit) |
| 429 | Rate limited (too many login attempts) |
| 500 | Internal server error |
| 503 | Service unavailable (e.g., Google Drive not connected) |

### Error Response Format

```json
{
  "detail": "Client not found"
}
```

For validation errors (Pydantic):

```json
{
  "detail": [
    {
      "loc": ["body", "first_name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Rate Limiting

### Login Rate Limiting

The login endpoint (`/api/v1/auth/login`) enforces rate limiting per IP address:

- Failed login attempts are tracked per IP
- After exceeding the threshold, the IP is locked out temporarily
- The lockout duration is returned in the error response
- Successful login resets the counter

There is no general rate limiting on other API endpoints.

---

## Code Examples

### Python (httpx)

```python
import httpx

BASE_URL = "https://your-domain.com/casehub"

# Authenticate
response = httpx.post(f"{BASE_URL}/api/v1/auth/login", data={
    "email": "user@firm.com",
    "password": "secret"
})
tokens = response.json()
access_token = tokens["access_token"]

headers = {"Authorization": f"Bearer {access_token}"}

# List clients
clients = httpx.get(f"{BASE_URL}/api/v1/clients", headers=headers, params={
    "search": "Santos",
    "limit": 10
}).json()
print(f"Found {clients['total']} clients")

# Create a case
new_case = httpx.post(f"{BASE_URL}/api/v1/cases", headers=headers, json={
    "client_id": 1,
    "case_name": "Santos EB-2 NIW",
    "visa_type": "EB-2 NIW",
    "status": "intake",
    "priority": "high",
    "case_value": 5000.00
}).json()
print(f"Created case ID: {new_case['id']}")

# Get dashboard stats
stats = httpx.get(f"{BASE_URL}/api/v1/dashboard/stats", headers=headers).json()
print(f"Active cases: {stats['stats']['active_cases']}")

# Upload a document
with open("passport.pdf", "rb") as f:
    response = httpx.post(f"{BASE_URL}/api/documents/upload-local", headers=headers, data={
        "client_id": "1",
        "doc_type": "Passport"
    }, files={
        "file": ("passport.pdf", f, "application/pdf")
    })
print(response.json())

# Approve a document
response = httpx.post(
    f"{BASE_URL}/api/documents/42/approve",
    headers=headers,
    params={"user_id": 1}
)
print(response.json())
```

### cURL

```bash
# Login and get token
TOKEN=$(curl -s -X POST https://your-domain.com/casehub/api/v1/auth/login \
  -d "email=user@firm.com" \
  -d "password=secret" | jq -r '.access_token')

# List clients
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://your-domain.com/casehub/api/v1/clients?limit=10" | jq .

# Get a specific case
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://your-domain.com/casehub/api/v1/cases/1" | jq .

# Create a client
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"first_name":"PessoaDemo","last_name":"Santos","email":"pessoa_demo@example.com","status":"active"}' \
  "https://your-domain.com/casehub/api/v1/clients" | jq .

# Update case status
curl -s -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"approved"}' \
  "https://your-domain.com/casehub/api/v1/cases/1" | jq .

# Delete a task
curl -s -X DELETE -H "Authorization: Bearer $TOKEN" \
  "https://your-domain.com/casehub/api/v1/tasks/5" | jq .

# Get dashboard stats
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://your-domain.com/casehub/api/v1/dashboard/stats" | jq .

# Upload document
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@passport.pdf" \
  -F "client_id=1" \
  -F "doc_type=Passport" \
  "https://your-domain.com/casehub/api/documents/upload-local" | jq .

# Test a webhook
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "https://your-domain.com/casehub/webhooks/1/test" | jq .
```

### JavaScript (fetch)

```javascript
const BASE_URL = '/casehub';

// Login
const loginRes = await fetch(`${BASE_URL}/api/v1/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: 'email=user@firm.com&password=secret'
});
const { access_token } = await loginRes.json();

const headers = {
  'Authorization': `Bearer ${access_token}`,
  'Content-Type': 'application/json'
};

// List cases
const cases = await fetch(`${BASE_URL}/api/v1/cases?status=filed`, { headers })
  .then(r => r.json());

// Create task
const task = await fetch(`${BASE_URL}/api/v1/tasks`, {
  method: 'POST',
  headers,
  body: JSON.stringify({
    title: 'Review petition draft',
    case_id: 1,
    priority: 'high',
    due_date: '2026-04-01'
  })
}).then(r => r.json());
```
