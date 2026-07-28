# Google Cloud Universal Ledger Escrow API

Enterprise RESTful API service built with FastAPI and integrated with Google Cloud Universal Ledger (`google.cloud.universalledger.v1`). Enables secure multi-party Escrow transactions featuring **Create Escrow**, **Buy (Fund)**, **Deliver**, **Return/Hold**, and **Sell or Auto-Release** operations.

---

## 🚀 Key Features

1. **Complete Escrow Lifecycle**:
   - **Create Escrow**: Initializes contract terms, assigns buyer/seller/arbiter accounts, and registers an Escrow Vault Account on Google Cloud Universal Ledger.
   - **Buy (Fund)**: Buyer transfers currency tokens into the Escrow Vault on Universal Ledger using atomic `Transfer` transactions.
   - **Deliver**: Marks the product as delivered and starts the 30-second return window.
   - **Auto-Release**: If escrow remains `DELIVERED` after the return window completes, funds are automatically released to the Seller.
   - **Hold**: Locks escrow during inspection, return, verification, or dispute using Universal Ledger contract state updates (`InvokeContractMethod`).
   - **Sell (Release)**: Releases vault funds directly to the Seller account on Universal Ledger (`Transfer`).
   - **Refund**: Resolves disputes by returning vault funds back to the Buyer.

2. **Google Cloud Universal Ledger (`google.cloud.universalledger.v1`) Integration**:
   - Built with Protobuf-compatible schema structures (`ClientTransaction`, `Transfer`, `CreateContract`, `InvokeContractMethod`, `QueryAccount`, `QueryTransactionState`).
   - Supports both real GCP Universal Ledger endpoints and a local ledger simulator for testing and development.
   - Audit history with cryptographic transaction digests and consensus execution round certificates.

---

## 🛠️ Installation & Setup

1. **Clone & Setup Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run API Server**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Access Interactive OpenAPI Documentation at: **http://localhost:8000/docs**

3. **Run Test Suite**:
   ```bash
   pytest -v
   ```

4. **Run End-to-End Demo Script**:
   ```bash
   python demo.py
   ```

---

## 📡 API Reference

### Escrow Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/escrows` | Create a new Escrow agreement and Vault account on Universal Ledger |
| `GET` | `/api/v1/escrows` | List all escrows and their statuses |
| `GET` | `/api/v1/escrows/{escrow_id}` | Get detailed Escrow state and ledger audit history |
| `POST` | `/api/v1/escrows/{escrow_id}/buy` | **Buy / Fund Escrow**: Buyer transfers funds to Escrow Vault |
| `POST` | `/api/v1/escrows/{escrow_id}/deliver` | **Deliver Escrow**: Mark product delivered and start the return window |
| `POST` | `/api/v1/escrows/{escrow_id}/request-return` | **Request Return**: Buyer requests return during the active return window |
| `POST` | `/api/v1/escrows/{escrow_id}/accept-early` | **Accept Early**: Buyer waives the remaining return window and releases funds |
| `POST` | `/api/v1/escrows/{escrow_id}/hold` | **Hold Escrow**: Lock escrow state during inspection |
| `POST` | `/api/v1/escrows/{escrow_id}/sell` | **Sell / Release**: Complete sale by transferring funds to Seller |
| `POST` | `/api/v1/escrows/{escrow_id}/refund` | Refund vault funds to Buyer |

---

## 📋 State Transitions & Operational Conditions

| Operation | HTTP Endpoint | Required Prerequisite State | Resulting State | Allowed Actor(s) (`requested_by`) | Key Validation Rules & Universal Ledger Actions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Create Escrow** | `POST /api/v1/escrows` | *None* (Initialization) | `CREATED` | Any Client Caller | • `amount > 0`<br>• Assigns `buyer_id`, `seller_id`, and `arbiter_id`<br>• Registers Escrow Vault Account (`acc_vault_<id>`) on Universal Ledger |
| **Buy (Fund)** | `POST /api/v1/escrows/{id}/buy` | `CREATED` | `FUNDED` | Designated `buyer_id` ONLY | • `request.buyer_id == escrow.buyer_id`<br>• Buyer ledger balance ≥ `escrow.amount`<br>• Submits atomic `Transfer` (Buyer → Vault) |
| **Deliver** | `POST /api/v1/escrows/{id}/deliver` | `FUNDED` | `DELIVERED` | Delivery actor, seller, buyer, or arbiter | • Records delivery details<br>• Starts `return_period_seconds` timer, default 30 seconds<br>• Sets `return_window_expires_at` |
| **Auto-Release After Delivery** | Background timer | `DELIVERED` for full return window | `RELEASED` | System timer using arbiter authorization | • Runs only after delivery timer completes<br>• Releases funds only if escrow is still `DELIVERED`<br>• Does not release if escrow moved to `HELD`, `REFUNDED`, or `RELEASED` |
| **Request Return** | `POST /api/v1/escrows/{id}/request-return` | `DELIVERED` within return window | `HELD` | Designated `buyer_id` ONLY | • Buyer must request before `return_window_expires_at`<br>• Cancels pending auto-release |
| **Hold (Freeze)** | `POST /api/v1/escrows/{id}/hold` | `CREATED`, `FUNDED`, or `DELIVERED` | `HELD` | `buyer_id`, `seller_id`, or `arbiter_id` | • Requires non-empty `reason`<br>• Submits `InvokeContractMethod` (`set_hold_status`) on Universal Ledger<br>• Cancels pending auto-release if called from `DELIVERED` |
| **Accept Early** | `POST /api/v1/escrows/{id}/accept-early` | `DELIVERED` | `RELEASED` | Designated `buyer_id` ONLY | • Buyer waives remaining return window<br>• Releases funds to seller immediately |
| **Sell (Release)**| `POST /api/v1/escrows/{id}/sell` | `DELIVERED` after return window, or `HELD` with buyer/arbiter authorization | `RELEASED` | `buyer_id`, `seller_id`, or `arbiter_id` | • Seller cannot release during active return window<br>• Vault balance ≥ `escrow.amount`<br>• Submits multi-signatory `Transfer` (Vault → Seller) |
| **Refund** | `POST /api/v1/escrows/{id}/refund` | `FUNDED`, `DELIVERED`, `HELD`, or `DISPUTED` | `REFUNDED` | `seller_id` or `arbiter_id` ONLY | • Buyer cannot self-refund<br>• Vault balance ≥ `escrow.amount`<br>• Cancels pending auto-release<br>• Submits multi-signatory `Transfer` (Vault → Buyer) |

### ⚠️ HTTP Error & Authorization Matrix

| HTTP Status | Trigger Condition | Underlying Cause |
| :--- | :--- | :--- |
| **`400 Bad Request`** | Invalid Lifecycle State | Calling `buy` when state is not `CREATED`, `deliver` before funding, or `sell` before delivery |
| **`400 Bad Request`** | Active Return Window | Seller tries to release funds before the 30-second delivery return window expires |
| **`400 Bad Request`** | Insufficient Ledger Balance | Payer balance on Universal Ledger is less than requested transaction `amount` |
| **`403 Forbidden`** | Unauthorized Role | Actor ID does not match allowed role (e.g. non-buyer funding, buyer self-refunding) |
| **`404 Not Found`** | Resource Missing | Invalid or non-existent `escrow_id` or ledger `account_id` |

---

### Universal Ledger Low-Level Introspection

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/ledger/accounts/{account_id}` | Query account balance, roles, sequence number, and round ID |
| `GET` | `/api/v1/ledger/transactions/{digest_hex}` | Query transaction status and round certificates |
| `GET` | `/api/v1/ledger/endpoints` | List Google Cloud Universal Ledger endpoints |

---

## 💡 Example Escrow Flow

### 1. Create Escrow
```json
POST /api/v1/escrows
{
  "buyer_id": "acc_buyer_001",
  "seller_id": "acc_seller_001",
  "arbiter_id": "acc_arbiter_001",
  "amount": 50000,
  "currency": "USD",
  "title": "MacBook Pro Purchase Escrow"
}
```

### 2. Buy / Fund Escrow
```json
POST /api/v1/escrows/{escrow_id}/buy
{
  "buyer_id": "acc_buyer_001",
  "payment_notes": "Funding $500.00 to vault"
}
```

### 3. Mark Product Delivered
```json
POST /api/v1/escrows/{escrow_id}/deliver
{
  "delivered_by": "acc_courier_001",
  "tracking_number": "TRK-889922",
  "delivery_notes": "Delivered to recipient address"
}
```

After delivery, the escrow status becomes `DELIVERED` and the 30-second return window starts.

### 4. Optional: Buyer Requests Return During Window
```json
POST /api/v1/escrows/{escrow_id}/request-return
{
  "buyer_id": "acc_buyer_001",
  "reason": "Item is damaged"
}
```

If a return is requested during the window, status becomes `HELD` and the automatic release is cancelled.

### 5. Optional: Buyer Accepts Delivery Early
```json
POST /api/v1/escrows/{escrow_id}/accept-early
{
  "buyer_id": "acc_buyer_001",
  "notes": "Product checked and accepted"
}
```

This releases funds immediately and changes status to `RELEASED`.

### 6. Automatic Release After 30 Seconds

If the escrow remains `DELIVERED` for the full 30-second return window, the background timer releases vault funds to the seller automatically. The final status becomes `RELEASED`.

Manual release is also allowed after the return window expires:

```json
POST /api/v1/escrows/{escrow_id}/sell
{
  "requested_by": "acc_seller_001",
  "settlement_notes": "Return window expired. Releasing funds to seller."
}
```

---

## 📁 Repository Structure

```
├── app/
│   ├── main.py              # FastAPI application entrypoint & middleware
│   ├── config.py            # Application settings (GCP project, endpoint, mock mode)
│   ├── models/
│   │   └── escrow.py        # Pydantic domain models & request/response schemas
│   ├── ledger/
│   │   ├── schemas.py       # google.cloud.universalledger.v1 Protobuf data models
│   │   └── client.py        # Universal Ledger Service client & state simulator
│   ├── services/
│   │   └── escrow_service.py # Escrow domain logic and Universal Ledger transaction generator
│   └── routers/
│       ├── escrow_router.py # REST endpoints for Escrow operations
│       └── ledger_router.py # Introspection endpoints for Universal Ledger
├── tests/
│   └── test_escrow_api.py   # Pytest suite covering full Create->Buy->Hold->Sell lifecycle
├── demo.py                  # Executable Python demonstration script
├── requirements.txt         # Dependencies
└── README.md                # Project documentation
```
