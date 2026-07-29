# Google Cloud Universal Ledger Escrow API

Enterprise RESTful API service built with FastAPI and integrated with Google Cloud Universal Ledger (`google.cloud.universalledger.v1`). Enables secure multi-party Escrow transactions featuring **Create Escrow**, **Buy (Fund)**, **Hold (Freeze/Inspect)**, and **Sell (Release/Settle)** operations.

---

## 🚀 Key Features

1. **Complete Escrow Lifecycle**:
   - **Create Escrow**: Initializes contract terms, assigns buyer/seller/arbiter accounts, and registers an Escrow Vault Account on Google Cloud Universal Ledger.
   - **Buy (Fund)**: Buyer transfers currency tokens into the Escrow Vault on Universal Ledger using atomic `Transfer` transactions.
   - **Hold**: Locks escrow during inspection, verification, or dispute using Universal Ledger contract state updates (`InvokeContractMethod`).
   - **Sell (Release)**: Releases locked vault funds directly to the Seller account on Universal Ledger (`Transfer`).
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
| `POST` | `/api/v1/escrows/{escrow_id}/hold` | **Hold Escrow**: Lock escrow state during inspection |
| `POST` | `/api/v1/escrows/{escrow_id}/sell` | **Sell / Release**: Complete sale by transferring funds to Seller |
| `POST` | `/api/v1/escrows/{escrow_id}/refund` | Refund vault funds to Buyer |

---

## 📋 State Transitions & Operational Conditions

| Operation | HTTP Endpoint | Required Prerequisite State | Resulting State | Allowed Actor(s) (`requested_by`) | Key Validation Rules & Universal Ledger Actions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Create Escrow** | `POST /api/v1/escrows` | *None* (Initialization) | `CREATED` | Any Client Caller | • `amount > 0`<br>• Assigns `buyer_id`, `seller_id`, and `arbiter_id`<br>• Registers Escrow Vault Account (`acc_vault_<id>`) on Universal Ledger |
| **Buy (Fund)** | `POST /api/v1/escrows/{id}/buy` | `CREATED` | `FUNDED` | Designated `buyer_id` ONLY | • `request.buyer_id == escrow.buyer_id`<br>• Buyer ledger balance ≥ `escrow.amount`<br>• Submits atomic `Transfer` (Buyer → Vault) |
| **Hold (Freeze)** | `POST /api/v1/escrows/{id}/hold` | `CREATED` or `FUNDED` | `HELD` | `buyer_id`, `seller_id`, or `arbiter_id` | • Requires non-empty `reason`<br>• Submits `InvokeContractMethod` (`set_hold_status`) on Universal Ledger |
| **Sell (Release)**| `POST /api/v1/escrows/{id}/sell` | `FUNDED` or `HELD` | `RELEASED` | `buyer_id`, `seller_id`, or `arbiter_id` | • Vault balance ≥ `escrow.amount`<br>• Submits multi-signatory `Transfer` (Vault → Seller) |
| **Refund** | `POST /api/v1/escrows/{id}/refund` | `FUNDED`, `HELD`, or `DISPUTED` | `REFUNDED` | `seller_id` or `arbiter_id` ONLY | • Buyer cannot self-refund<br>• Vault balance ≥ `escrow.amount`<br>• Submits multi-signatory `Transfer` (Vault → Buyer) |

### ⚠️ HTTP Error & Authorization Matrix

| HTTP Status | Trigger Condition | Underlying Cause |
| :--- | :--- | :--- |
| **`400 Bad Request`** | Invalid Lifecycle State | Calling `buy` when state is not `CREATED`, or `sell` when un-funded |
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

### 3. Put Escrow on Hold
```json
POST /api/v1/escrows/{escrow_id}/hold
{
  "requested_by": "acc_buyer_001",
  "reason": "Inspection in progress"
}
```

### 4. Sell / Release Funds
```json
POST /api/v1/escrows/{escrow_id}/sell
{
  "requested_by": "acc_buyer_001",
  "settlement_notes": "Inspection passed. Releasing $500.00 to seller."
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



 # Activate virtual environment
source venv/bin/activate

# Start the API server on port 8000
uvicorn app.main:app --reload --port 8000