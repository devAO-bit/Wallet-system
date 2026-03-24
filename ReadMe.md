# Wallet Transaction System

A Django REST API that maintains a wallet for each client. Admin users can credit or debit wallet balances, and clients can create orders that deduct amounts from their wallets with external fulfillment integration.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Database Models](#database-models)
- [API Reference](#api-reference)
  - [Admin – Credit Wallet](#1-admin--credit-wallet)
  - [Admin – Debit Wallet](#2-admin--debit-wallet)
  - [Client – Create Order](#3-client--create-order)
  - [Client – Get Order Details](#4-client--get-order-details)
  - [Client – Wallet Balance](#5-client--wallet-balance)
- [Testing with Postman](#testing-with-postman)
- [Error Reference](#error-reference)
- [Design Decisions](#design-decisions)

---

## Tech Stack

- **Python** 3.10+
- **Django** 6.x
- **Django REST Framework** 3.x
- **SQLite** (default, can be swapped for PostgreSQL)
- **urllib (stdlib)** for external fulfillment API calls

---

## Project Structure

```
wallet_project/
├── wallet_project/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── wallet/
│   ├── migrations/
│   ├── management/
│   │   └── commands/
│   │       └── seed.py
│   ├── models.py
│   ├── serializers.py
│   ├── services.py
│   ├── views.py
│   ├── urls.py
│   └── admin.py
├── manage.py
└── requirements.txt
```

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd wallet_project
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# On macOS/Linux
source venv/bin/activate

# On Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install django djangorestframework
```

Or if you have a `requirements.txt`:

```bash
pip install -r requirements.txt
```

`requirements.txt`:
```
django
djangorestframework
```

### 4. Configure `settings.py`

Make sure the following are set in `wallet_project/settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',   # ← add this
    'wallet',           # ← add this
]

# Disable trailing slash redirects (important for POST APIs)
APPEND_SLASH = False

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # 'django.middleware.csrf.CsrfViewMiddleware',  # ← comment this out
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
}
```

### 5. Run migrations

```bash
python manage.py makemigrations wallet
python manage.py migrate
```

### 6. Create a test client

```bash
python manage.py shell
```

```python
from wallet.models import Client, Wallet
client = Client.objects.create(name="Test User", email="test@example.com")
Wallet.objects.create(client=client)
print(client.id)  # Copy this UUID — you will need it for all API calls
```

### 7. Start the server

```bash
python manage.py runserver
```

Server will be running at `http://127.0.0.1:8000`

---

## Database Models

### `Client`
Represents a user of the system.

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Auto-generated primary key |
| `name` | CharField | Client's full name |
| `email` | EmailField | Unique email address |
| `created_at` | DateTimeField | Timestamp of creation |

### `Wallet`
Each client has one wallet storing their balance.

| Field | Type | Description |
|---|---|---|
| `id` | AutoField | Primary key |
| `client` | OneToOneField | Linked client |
| `balance` | DecimalField | Current balance (12 digits, 2 decimal places) |
| `updated_at` | DateTimeField | Last updated timestamp |

### `LedgerEntry`
Immutable record of every credit and debit transaction.

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Auto-generated primary key |
| `wallet` | ForeignKey | Linked wallet |
| `transaction_type` | CharField | `credit` or `debit` |
| `amount` | DecimalField | Transaction amount |
| `balance_after` | DecimalField | Wallet balance after this transaction |
| `description` | CharField | Reason for the transaction |
| `created_at` | DateTimeField | Timestamp |

### `Order`
Represents a client's order linked to a wallet deduction.

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Auto-generated primary key |
| `client` | ForeignKey | Linked client |
| `idempotency_key` | CharField | Client-provided key for idempotent create-order retries |
| `amount` | DecimalField | Order amount |
| `status` | CharField | `pending`, `fulfilled`, or `failed` |
| `fulfillment_id` | CharField | ID returned by external fulfillment API |
| `refunded` | BooleanField | `true` when automatic refund is issued after terminal fulfillment failure |
| `created_at` | DateTimeField | Created timestamp |
| `updated_at` | DateTimeField | Last updated timestamp |

### `FulfillmentJob`
Asynchronous job record for processing order fulfillment.

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Auto-generated primary key |
| `order` | OneToOneField | Linked order |
| `status` | CharField | `pending`, `processing`, `completed`, or `failed` |
| `attempts` | PositiveIntegerField | Number of fulfillment attempts made |
| `last_error` | TextField | Last failure reason (if any) |
| `created_at` | DateTimeField | Created timestamp |
| `updated_at` | DateTimeField | Last updated timestamp |

### `OrderEvent`
Structured event log for order lifecycle observability.

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Auto-generated primary key |
| `order` | ForeignKey | Linked order |
| `event_type` | CharField | Event name (`order_created`, `fulfillment_attempt`, etc.) |
| `payload` | JSONField | Structured metadata for the event |
| `created_at` | DateTimeField | Timestamp |

---

## API Reference

### Base URL
```
http://127.0.0.1:8000
```

---

### 1. Admin – Credit Wallet

Credits a specified amount to a client's wallet and creates a ledger entry.

**Endpoint**
```
POST /admin/wallet/credit
```

**Headers**
```
Content-Type: application/json
```

**Request Body**
```json
{
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "amount": 500.00
}
```

**Success Response** `200 OK`
```json
{
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "balance": "500.00"
}
```

**Error Responses**

| Status | Reason | Response |
|---|---|---|
| `400` | Amount is zero or negative | `{"error": "Credit amount must be positive."}` |
| `400` | Missing or invalid fields | `{"amount": ["This field is required."]}` |
| `404` | Client not found | `{"error": "Client not found."}` |

---

### 2. Admin – Debit Wallet

Deducts a specified amount from a client's wallet if balance is sufficient.

**Endpoint**
```
POST /admin/wallet/debit
```

**Headers**
```
Content-Type: application/json
```

**Request Body**
```json
{
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "amount": 100.00
}
```

**Success Response** `200 OK`
```json
{
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "balance": "400.00"
}
```

**Error Responses**

| Status | Reason | Response |
|---|---|---|
| `400` | Insufficient balance | `{"error": "Insufficient wallet balance."}` |
| `400` | Amount is zero or negative | `{"error": "Debit amount must be positive."}` |
| `404` | Client not found | `{"error": "Client not found."}` |

---

### 3. Client – Create Order

Validates wallet balance, atomically deducts the amount, creates an order, enqueues asynchronous fulfillment, and returns immediately. Fulfillment status and `fulfillment_id` are updated in the background.

**Endpoint**
```
POST /orders
```

**Headers**
```
Content-Type: application/json
client-id: 3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx
idempotency-key: a-unique-key-generated-by-client
```

**Request Body**
```json
{
  "amount": 50.00
}
```

**Success Response** `201 Created`
```json
{
  "order_id": "a1b2c3d4-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "amount": "50.00",
  "status": "pending",
  "fulfillment_id": null,
  "refunded": false,
  "idempotent_replay": false
}
```

**Idempotent Replay Response** `200 OK` (same key + same client)
```json
{
  "order_id": "a1b2c3d4-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "amount": "50.00",
  "status": "pending",
  "fulfillment_id": null,
  "refunded": false,
  "idempotent_replay": true
}
```

> **Note:** `fulfillment_id` is stored after asynchronous fulfillment succeeds.

**Order Status Values**

| Status | Meaning |
|---|---|
| `pending` | Order created, fulfillment in progress |
| `fulfilled` | Fulfillment API responded successfully |
| `failed` | Fulfillment failed after retries (order is auto-refunded) |

**Error Responses**

| Status | Reason | Response |
|---|---|---|
| `400` | Missing `client-id` header | `{"error": "client-id header is required."}` |
| `400` | Missing `idempotency-key` header | `{"error": "idempotency-key header is required."}` |
| `400` | Insufficient balance | `{"error": "Insufficient wallet balance."}` |
| `400` | Invalid amount | `{"amount": ["Ensure this value is greater than or equal to 0.01."]}` |
| `404` | Client not found | `{"error": "Client not found."}` |

---

### 4. Client – Get Order Details

Returns full order information for a specific order belonging to the authenticated client.

**Endpoint**
```
GET /orders/{order_id}
```

**Headers**
```
client-id: 3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**URL Parameter**

| Parameter | Type | Description |
|---|---|---|
| `order_id` | UUID | The ID of the order to retrieve |

**Success Response** `200 OK`
```json
{
  "id": "a1b2c3d4-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "amount": "50.00",
  "status": "fulfilled",
  "fulfillment_id": "101",
  "refunded": false,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:05Z"
}
```

**Error Responses**

| Status | Reason | Response |
|---|---|---|
| `400` | Missing `client-id` header | `{"error": "client-id header is required."}` |
| `404` | Order not found or doesn't belong to client | `{"error": "Order not found."}` |

---

### 5. Client – Wallet Balance

Returns the current wallet balance for the authenticated client.

**Endpoint**
```
GET /wallet/balance
```

**Headers**
```
client-id: 3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Success Response** `200 OK`
```json
{
  "client_id": "3f6c2b1a-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "balance": "350.00"
}
```

**Error Responses**

| Status | Reason | Response |
|---|---|---|
| `400` | Missing `client-id` header | `{"error": "client-id header is required."}` |
| `404` | Wallet not found | `{"error": "Wallet not found."}` |

---

## Testing with Postman

### Initial Setup

1. Open Postman
2. Go to **Settings** (gear icon) → **General**
3. Turn **OFF** "Automatically follow redirects"

### Step-by-step Testing Flow

#### Step 1 — Get your Client ID
Run this in terminal before testing:
```bash
python manage.py shell -c "from wallet.models import Client; print(Client.objects.first().id)"
```
Copy the UUID printed. You will use it in every request.

#### Step 2 — Credit the wallet
- Method: `POST`
- URL: `http://127.0.0.1:8000/admin/wallet/credit`
- Headers: `Content-Type: application/json`
- Body → raw → JSON:
```json
{ "client_id": "<your-uuid>", "amount": 500 }
```

#### Step 3 — Check balance
- Method: `GET`
- URL: `http://127.0.0.1:8000/wallet/balance`
- Headers: `client-id: <your-uuid>`

#### Step 4 — Create an order
- Method: `POST`
- URL: `http://127.0.0.1:8000/orders`
- Headers:
  - `Content-Type: application/json`
  - `client-id: <your-uuid>`
  - `idempotency-key: <unique-key-per-create-request>`
- Body → raw → JSON:
```json
{ "amount": 50 }
```
Copy the `order_id` from the response. The initial status will usually be `pending`; fulfillment is processed asynchronously.

#### Step 5 — Get order details
- Method: `GET`
- URL: `http://127.0.0.1:8000/orders/<order-id-from-step-4>`
- Headers: `client-id: <your-uuid>`

---

### Full Test Checklist

| # | Test Case | Expected Result |
|---|---|---|
| 1 | Credit wallet with valid amount | `200` — balance increases |
| 2 | Credit with negative amount | `400` — validation error |
| 3 | Credit with invalid client_id | `404` — client not found |
| 4 | Debit wallet with valid amount | `200` — balance decreases |
| 5 | Debit more than available balance | `400` — insufficient funds |
| 6 | Check wallet balance | `200` — correct balance returned |
| 7 | Check balance without `client-id` header | `400` — header required |
| 8 | Create order within balance | `201` — order created (status starts as `pending`) |
| 9 | Create order exceeding balance | `400` — insufficient funds |
| 10 | Create order without `client-id` header | `400` — header required |
| 10a | Create order without `idempotency-key` header | `400` — header required |
| 11 | Get order details with correct client | `200` — full order info |
| 12 | Get order details with wrong client | `404` — not found |
| 13 | Get non-existent order | `404` — not found |

---

## Error Reference

| HTTP Status | Meaning |
|---|---|
| `200 OK` | Request succeeded |
| `201 Created` | Resource created successfully |
| `400 Bad Request` | Invalid input, missing fields, or business rule violation |
| `404 Not Found` | Resource does not exist |
| `500 Internal Server Error` | Unexpected server error |

---

## Design Decisions

### Atomic Wallet Deduction
Wallet balance checks and deductions use `select_for_update()` inside `transaction.atomic()`. This prevents race conditions where two simultaneous requests could both pass the balance check and double-spend the same funds.

### Ledger Pattern
Every credit and debit creates an immutable `LedgerEntry` record with the `balance_after` stored. This provides a full audit trail and allows balance reconciliation at any point in time.

### Async Fulfillment and Retry Strategy
Order creation commits quickly and enqueues a background fulfillment job. The fulfillment worker uses retry with exponential backoff and a lightweight circuit breaker to handle provider instability while keeping API latency low.

### Automatic Reconciliation on Terminal Failure
If fulfillment still fails after all retries, the order is marked `failed`, the wallet is automatically refunded inside a transaction, and a compensating credit ledger entry is written.

### Idempotent Order Creation
`POST /orders` requires an `idempotency-key` header. Repeating the same request with the same key for the same client returns the original order response and prevents duplicate wallet deductions.

### Structured Observability
`OrderEvent` records structured lifecycle events (`order_created`, `fulfillment_queued`, attempts, success/failure, and refund) for operational debugging and auditing.

### Client Isolation on Orders
`GET /orders/{order_id}` filters by both `order_id` AND `client-id` header simultaneously. This ensures clients cannot access or enumerate each other's orders.

### CSRF Disabled for API
CSRF protection is designed for browser-based form submissions. Since this is a stateless REST API using header-based client identification, CSRF middleware is disabled. All views are also decorated with `@csrf_exempt` as a secondary safeguard.

### Separation of Concerns
- **`models.py`** — data layer only
- **`services.py`** — all business logic (wallet operations, order creation, fulfillment calls)
- **`services.py`** — all business logic (wallet operations, order creation, async fulfillment processing, retries, refunds)
- **`views.py`** — HTTP request/response handling only
- **`serializers.py`** — input validation only

This makes the business logic independently testable without HTTP context.