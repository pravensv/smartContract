# 📘 Developer & Testing Guide: Delivery, Return, & Smart Contract API Integration

This guide explains **where** the delivery and return APIs are developed in the codebase, **how** they interact with the smart contract on Google Cloud Universal Ledger, and **how to test** them step-by-step.

---

## 🏗️ 1. Architecture & File Structure

The API architecture consists of 4 main layers:

```
                  ┌───────────────────────────────┐
                  │   FastAPI Web Router          │
                  │   app/routers/escrow_router.py│
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │   Escrow Service Layer        │
                  │   app/services/escrow_service.py
                  └──────────────┬────────────────┘
                                 │
                                 ▼
                  ┌───────────────────────────────┐
                  │   GCP Universal Ledger Client │
                  │   app/ledger/client.py        │
                  └──────────────┬────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│   Smart Contract / Ledger State                                  │
│   contracts/UniversalEscrowRules.sol / UniversalEscrow.sol       │
│   State: CREATED ➔ FUNDED ➔ DELIVERED (5-Day Window) ➔ RELEASED  │
└──────────────────────────────────────────────────────────────────┘
```

### Key Files & Locations:

1. **Data Models** ([app/models/escrow.py](file:///Users/praveenvoruganti/Documents/Hackthon/app/models/escrow.py)):
   - `DeliverEscrowRequest`: Payload for delivery confirmation (`delivered_by`, `tracking_number`, `delivery_notes`).
   - `RequestReturnRequest`: Payload for buyer return request (`buyer_id`, `reason`).
   - `AcceptDeliveryEarlyRequest`: Payload for waiving return period (`buyer_id`, `notes`).
   - `EscrowStatus`: Enum including `CREATED`, `FUNDED`, `DELIVERED`, `HELD`, `RELEASED`, `REFUNDED`, `DISPUTED`.

2. **Service Logic & Smart Contract Invocations** ([app/services/escrow_service.py](file:///Users/praveenvoruganti/Documents/Hackthon/app/services/escrow_service.py)):
   - Constructs `InvokeContractMethod` transactions for Google Cloud Universal Ledger.
   - Calculates delivery timestamp and `return_window_expires_at` (5 days post-delivery).
   - Enforces return window locks (rejecting merchant release attempts while inside the 5-day window).

3. **FastAPI Endpoints** ([app/routers/escrow_router.py](file:///Users/praveenvoruganti/Documents/Hackthon/app/routers/escrow_router.py)):
   - `POST /api/v1/escrows/{escrow_id}/deliver`
   - `POST /api/v1/escrows/{escrow_id}/request-return`
   - `POST /api/v1/escrows/{escrow_id}/accept-early`
   - `POST /api/v1/escrows/{escrow_id}/sell`

4. **Smart Contracts** ([contracts/UniversalEscrowRules.sol](file:///Users/praveenvoruganti/Documents/Hackthon/contracts/UniversalEscrowRules.sol) / [contracts/UniversalEscrow.sol](file:///Users/praveenvoruganti/Documents/Hackthon/contracts/UniversalEscrow.sol)):
   - Contains state modifiers (`onlyBuyer`, `onlyAuthorizedActor`, `inState`).
   - Stores `deliveredAt` timestamp and 5-day return duration (`DEFAULT_RETURN_PERIOD = 5 days`).

---

## ⚡ 2. How the API Hits the Smart Contract

When an API request is sent (e.g. Delivery Boy marks item delivered):

1. **API Call Received**: FastAPI receives `POST /api/v1/escrows/{escrow_id}/deliver`.
2. **Contract Method Invocation Created**: `EscrowService` constructs a signed ledger transaction:
   ```python
   tx = ClientTransaction(
       sender_id=request.delivered_by,
       invoke_contract_method_transaction=InvokeContractMethod(
           contract_id=vault_account_id,
           method_name="mark_delivered",
           method_arguments={
               "delivered_by": request.delivered_by,
               "tracking_number": request.tracking_number,
               "delivered_at": now,
               "return_expires_at": now + (5 * 86400)
           }
       )
   )
   ```
3. **Consensus Round & State Execution**: Universal Ledger verifies signatories, executes the `markDelivered` method in `UniversalEscrowRules.sol`, and emits a cryptographic `round_id` and `transaction_digest_hex`.
4. **Return Period Lock Activated**: Money in vault remains locked for 5 days.

---

## 🧪 3. Step-by-Step Testing Guide

### Option A: Testing via Automated Pytest Suite
Run the test suite via shell:
```bash
./venv/bin/pytest -v tests/test_escrow_api.py
```

### Option B: Interactive Swagger UI
1. Start API server:
   ```bash
   ./venv/bin/uvicorn app.main:app --reload --port 8000
   ```
2. Open browser at: **http://localhost:8000/docs**

---

### Option C: Testing via cURL Commands

#### 1️⃣ Create Escrow (Setting 5-Day Return Period)
```bash
curl -X POST "http://localhost:8000/api/v1/escrows" \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_id": "acc_buyer_001",
    "seller_id": "acc_seller_001",
    "arbiter_id": "acc_arbiter_001",
    "amount": 50000,
    "currency": "USD",
    "title": "MacBook Pro Purchase",
    "return_period_days": 5
  }'
```

#### 2️⃣ Buy / Fund Escrow
```bash
curl -X POST "http://localhost:8000/api/v1/escrows/escrow_<ID>/buy" \
  -H "Content-Type: application/json" \
  -d '{
    "buyer_id": "acc_buyer_001",
    "payment_notes": "Deposit funded to vault"
  }'
```

#### 3️⃣ Delivery Boy / Courier Marks Product Delivered
```bash
curl -X POST "http://localhost:8000/api/v1/escrows/escrow_<ID>/deliver" \
  -H "Content-Type: application/json" \
  -d '{
    "delivered_by": "acc_courier_001",
    "tracking_number": "TRK-990011",
    "delivery_notes": "Handed to recipient at door"
  }'
```
*Response state updates to `DELIVERED` and calculates `return_window_expires_at`.*

#### 4️⃣ Test Rule: Merchant Tries to Claim Funds During 5-Day Window (Fails)
```bash
curl -X POST "http://localhost:8000/api/v1/escrows/escrow_<ID>/sell" \
  -H "Content-Type: application/json" \
  -d '{
    "requested_by": "acc_seller_001",
    "settlement_notes": "Claiming early"
  }'
```
*Returns `HTTP 400 Bad Request`: "Money is held during the 5-day return window. Merchant cannot claim funds..."*

#### 5️⃣ Buyer Accepts Delivery Early OR Requests Return
- **To Request Return (within 5 days)**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/escrows/escrow_<ID>/request-return" \
    -H "Content-Type: application/json" \
    -d '{
      "buyer_id": "acc_buyer_001",
      "reason": "Screen cracked during shipping"
    }'
  ```

- **To Accept Delivery Early (Waiving Return Period)**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/escrows/escrow_<ID>/accept-early" \
    -H "Content-Type: application/json" \
    -d '{
      "buyer_id": "acc_buyer_001",
      "notes": "Verified laptop works perfectly"
    }'
  ```

---

## 📊 Summary of Lifecycle Statuses

| Action | API Endpoint | Prerequisite State | Resulting State |
| :--- | :--- | :--- | :--- |
| Create | `POST /api/v1/escrows` | None | `CREATED` |
| Fund | `POST /api/v1/escrows/{id}/buy` | `CREATED` | `FUNDED` |
| Deliver | `POST /api/v1/escrows/{id}/deliver` | `FUNDED` | `DELIVERED` |
| Request Return | `POST /api/v1/escrows/{id}/request-return` | `DELIVERED` (< 5 days) | `HELD` |
| Accept Early | `POST /api/v1/escrows/{id}/accept-early` | `DELIVERED` | `RELEASED` |
| Merchant Release | `POST /api/v1/escrows/{id}/sell` | `DELIVERED` (> 5 days) | `RELEASED` |
| Refund | `POST /api/v1/escrows/{id}/refund` | `HELD` / `DELIVERED` | `REFUNDED` |
