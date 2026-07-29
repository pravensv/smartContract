# Google Cloud Universal Ledger Escrow API

Enterprise RESTful API service built with FastAPI and integrated with Google Cloud Universal Ledger (`google.cloud.universalledger.v1`). It supports escrow flows for create, fund, delivery, return/hold handling, refund, and automatic release.

---

## Key Features

1. **Complete Escrow Lifecycle**
   - **Create Escrow**: Initializes buyer, seller, arbiter, amount, and vault account.
   - **Buy / Fund**: Transfers buyer funds into the escrow vault.
   - **Deliver**: Marks the product as delivered and starts the delivery return window.
   - **Auto-Release After Delivery**: If escrow remains `DELIVERED` after the return window, funds release to the seller automatically.
   - **Return / Hold**: Moves escrow to `HELD` for return, inspection, verification, or dispute review.
   - **Auto-Release From Hold**: If escrow remains `HELD` for 59 seconds and no refund is called, funds release to the seller automatically.
   - **Refund**: If refund is called while escrow is held, funds are refunded immediately, regardless of the 30-second held timer.

2. **Google Cloud Universal Ledger Integration**
   - Uses ledger-style transaction objects such as `ClientTransaction`, `Transfer`, `InvokeContractMethod`, `QueryAccount`, and `QueryTransactionState`.
   - Supports local fallback behavior for testing and development.
   - Keeps audit history with transaction digests and ledger event logs.

---

## Installation & Setup

1. Create and activate the virtual environment:

```powershell
cd C:\Users\Akshata\IdeaProjects\smartContract
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Run the API server:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open the API docs:

```text
http://localhost:8000/docs
```

3. Run tests:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

4. Run the demo:

```powershell
.\venv\Scripts\python.exe demo.py
```

---

## API Reference

### Escrow Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/escrows` | Create a new escrow and vault account |
| `GET` | `/api/v1/escrows` | List all escrows |
| `GET` | `/api/v1/escrows/{escrow_id}` | Get escrow details and audit history |
| `POST` | `/api/v1/escrows/{escrow_id}/buy` | Buyer funds the escrow vault |
| `POST` | `/api/v1/escrows/{escrow_id}/deliver` | Mark product delivered and start return timer |
| `POST` | `/api/v1/escrows/{escrow_id}/request-return` | Buyer requests return during delivery return window |
| `POST` | `/api/v1/escrows/{escrow_id}/accept-early` | Buyer accepts delivery early and releases funds |
| `POST` | `/api/v1/escrows/{escrow_id}/hold` | Put escrow on hold |
| `POST` | `/api/v1/escrows/{escrow_id}/sell` | Release funds to seller |
| `POST` | `/api/v1/escrows/{escrow_id}/refund` | Refund funds to buyer |

### Ledger Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/v1/ledger/accounts/{account_id}` | Query account balance and ledger account details |
| `GET` | `/api/v1/ledger/transactions/{digest_hex}` | Query transaction state |
| `GET` | `/api/v1/ledger/endpoints` | List configured ledger endpoints |

---

## State Transitions

| Operation | Endpoint | From State | To State | Who Can Call | Rules                                                                                                                    |
| :--- | :--- | :--- | :--- | :--- |:-------------------------------------------------------------------------------------------------------------------------|
| Create Escrow | `POST /api/v1/escrows` | None | `CREATED` | Any caller | Amount must be greater than 0. Creates vault account.                                                                    |
| Buy / Fund | `POST /api/v1/escrows/{id}/buy` | `CREATED` | `FUNDED` | Buyer only | Buyer transfers funds into vault.                                                                                        |
| Deliver | `POST /api/v1/escrows/{id}/deliver` | `FUNDED` | `DELIVERED` | Delivery actor, seller, buyer, or arbiter | Starts `return_period_seconds`, default 59 seconds.                                                                      |
| Auto-Release After Delivery | Background timer | `DELIVERED` | `RELEASED` | System timer using arbiter authorization | Runs only if escrow is still `DELIVERED` when the delivery return window completes.                                      |
| Request Return | `POST /api/v1/escrows/{id}/request-return` | `DELIVERED` | `HELD` | Buyer only | Must be called before the delivery return window expires. Cancels delivery auto-release and starts the held-state timer. |
| Hold | `POST /api/v1/escrows/{id}/hold` | `CREATED`, `FUNDED`, or `DELIVERED` | `HELD` | Buyer, seller, or arbiter | Cancels delivery auto-release if active and starts the held-state timer.                                                 |
| Auto-Release From Hold | Background timer | `HELD` | `RELEASED` | System timer using arbiter authorization | If no refund is called within 59 seconds of entering `HELD`, funds release to seller.                                    |
| Refund | `POST /api/v1/escrows/{id}/refund` | `FUNDED`, `DELIVERED`, `HELD`, or `DISPUTED` | `REFUNDED` | Seller or arbiter | Refund happens immediately. If escrow is `HELD`, refund wins even if the 30-second timer has not completed.              |
| Accept Early | `POST /api/v1/escrows/{id}/accept-early` | `DELIVERED` | `RELEASED` | Buyer only | Buyer waives the remaining delivery return window.                                                                       |
| Sell / Release | `POST /api/v1/escrows/{id}/sell` | `DELIVERED` after return window, or `HELD` with buyer/arbiter authorization | `RELEASED` | Buyer, seller, or arbiter | Seller cannot release during the active delivery return window.                                                          |

---

## Example Flow

### 1. Create Escrow

```json
POST /api/v1/escrows
{
  "buyer_id": "acc_buyer_001",
  "seller_id": "acc_seller_001",
  "arbiter_id": "acc_arbiter_001",
  "amount": 50000,
  "currency": "USD",
  "title": "MacBook Pro Purchase Escrow",
  "return_period_seconds": 30
}
```

### 2. Buyer Funds Escrow

```json
POST /api/v1/escrows/{escrow_id}/buy
{
  "buyer_id": "acc_buyer_001",
  "payment_notes": "Funding $500.00 to vault"
}
```

### 3. Product Is Delivered

```json
POST /api/v1/escrows/{escrow_id}/deliver
{
  "delivered_by": "acc_courier_001",
  "tracking_number": "TRK-889922",
  "delivery_notes": "Delivered to recipient address"
}
```

Status becomes `DELIVERED`. The delivery return timer starts.

### 4A. No Return Is Requested

If escrow stays `DELIVERED` until the delivery return timer completes, funds automatically release to the seller and status becomes `RELEASED`.

### 4B. Buyer Requests Return

```json
POST /api/v1/escrows/{escrow_id}/request-return
{
  "buyer_id": "acc_buyer_001",
  "reason": "Item is damaged"
}
```

Status becomes `HELD`. The delivery auto-release is cancelled. A new 30-second held-state timer starts.

### 5A. Refund Is Approved While Held

```json
POST /api/v1/escrows/{escrow_id}/refund
{
  "requested_by": "acc_arbiter_001",
  "reason": "Refund approved after review"
}
```

Funds are refunded to the buyer immediately and status becomes `REFUNDED`. This cancels the held-state timer.

### 5B. No Refund While Held

If escrow remains `HELD` for 59 seconds and no refund is called, funds automatically release to the seller and status becomes `RELEASED`.

---

## Repository Structure

```text
app/
  main.py
  config.py
  ledger/
  models/
  routers/
  services/
contracts/
tests/
demo.py
requirements.txt
README.md
```



 # Activate virtual environment
source venv/bin/activate

# Start the API server on port 8000
uvicorn app.main:app --reload --port 8000