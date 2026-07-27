import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_healthcheck():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "gcp_project" in data

def test_create_escrow():
    payload = {
        "buyer_id": "acc_buyer_001",
        "seller_id": "acc_seller_001",
        "arbiter_id": "acc_arbiter_001",
        "amount": 50000,
        "currency": "USD",
        "title": "MacBook Pro Purchase",
        "description": "Mint condition 16-inch M3 Max"
    }
    response = client.post("/api/v1/escrows", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "CREATED"
    assert data["amount"] == 50000
    assert data["buyer_id"] == "acc_buyer_001"
    assert data["seller_id"] == "acc_seller_001"
    assert data["vault_account_id"].startswith("acc_vault_")
    assert len(data["ledger_history"]) == 1

def test_full_escrow_lifecycle_create_buy_hold_sell():
    # 1. Create Escrow
    create_payload = {
        "buyer_id": "acc_buyer_001",
        "seller_id": "acc_seller_001",
        "arbiter_id": "acc_arbiter_001",
        "amount": 100000,  # $1,000.00 USD
        "currency": "USD",
        "title": "Rolex Watch Purchase",
        "description": "Vintage Submariner"
    }
    res_create = client.post("/api/v1/escrows", json=create_payload)
    assert res_create.status_code == 201
    escrow = res_create.json()
    escrow_id = escrow["escrow_id"]
    vault_id = escrow["vault_account_id"]

    # Verify initial Buyer and Vault account balances on Ledger
    res_buyer_acc = client.get(f"/api/v1/ledger/accounts/{escrow['buyer_id']}")
    assert res_buyer_acc.status_code == 200
    initial_buyer_bal = res_buyer_acc.json()["account"]["currency_balances"].get("GBP", res_buyer_acc.json()["account"]["currency_balances"].get("USD", 500000))

    # 2. Buy / Fund Escrow
    buy_payload = {
        "buyer_id": "acc_buyer_001",
        "payment_notes": "Wiring £1,000 to vault"
    }
    res_buy = client.post(f"/api/v1/escrows/{escrow_id}/buy", json=buy_payload)
    assert res_buy.status_code == 200
    escrow_funded = res_buy.json()
    assert escrow_funded["status"] == "FUNDED"

    # Check updated balances on Universal Ledger
    res_buyer_after = client.get(f"/api/v1/ledger/accounts/{escrow['buyer_id']}")
    buyer_bal_after = res_buyer_after.json()["account"]["currency_balances"].get("GBP", res_buyer_after.json()["account"]["currency_balances"].get("USD", 0))
    assert buyer_bal_after == initial_buyer_bal - 100000

    res_vault_acc = client.get(f"/api/v1/ledger/accounts/{vault_id}")
    vault_bal = res_vault_acc.json()["account"]["currency_balances"].get("GBP", res_vault_acc.json()["account"]["currency_balances"].get("USD", 0))
    assert vault_bal == 100000

    # 3. Hold Escrow (Inspection Phase)
    hold_payload = {
        "requested_by": "acc_buyer_001",
        "reason": "Authenticating serial number with watchmaker"
    }
    res_hold = client.post(f"/api/v1/escrows/{escrow_id}/hold", json=hold_payload)
    assert res_hold.status_code == 200
    escrow_held = res_hold.json()
    assert escrow_held["status"] == "HELD"
    assert escrow_held["hold_reason"] == "Authenticating serial number with watchmaker"

    # 4. Sell / Release Escrow to Seller
    res_seller_acc_before = client.get(f"/api/v1/ledger/accounts/{escrow['seller_id']}")
    seller_bal_before = res_seller_acc_before.json()["account"]["currency_balances"].get("GBP", res_seller_acc_before.json()["account"]["currency_balances"].get("USD", 0))

    sell_payload = {
        "requested_by": "acc_buyer_001",
        "settlement_notes": "Watch authenticated. Release funds to seller."
    }
    res_sell = client.post(f"/api/v1/escrows/{escrow_id}/sell", json=sell_payload)
    assert res_sell.status_code == 200
    escrow_released = res_sell.json()
    assert escrow_released["status"] == "RELEASED"
    assert escrow_released["hold_reason"] is None

    # Verify final balances on Universal Ledger
    res_seller_acc_after = client.get(f"/api/v1/ledger/accounts/{escrow['seller_id']}")
    seller_bal_after = res_seller_acc_after.json()["account"]["currency_balances"].get("GBP", res_seller_acc_after.json()["account"]["currency_balances"].get("USD", 0))
    assert seller_bal_after == seller_bal_before + 100000

    res_vault_final = client.get(f"/api/v1/ledger/accounts/{vault_id}")
    assert res_vault_final.json()["account"]["currency_balances"].get("GBP", res_vault_final.json()["account"]["currency_balances"].get("USD", 0)) == 0

def test_invalid_buyer_cannot_fund():
    # Create escrow
    create_res = client.post("/api/v1/escrows", json={
        "buyer_id": "acc_buyer_001",
        "seller_id": "acc_seller_001",
        "amount": 20000,
        "title": "Camera Purchase"
    })
    escrow_id = create_res.json()["escrow_id"]

    # Attempt buy funding with wrong account
    res = client.post(f"/api/v1/escrows/{escrow_id}/buy", json={
        "buyer_id": "acc_random_person"
    })
    assert res.status_code == 403

def test_cannot_sell_before_funding():
    create_res = client.post("/api/v1/escrows", json={
        "buyer_id": "acc_buyer_001",
        "seller_id": "acc_seller_001",
        "amount": 20000,
        "title": "Laptop Escrow"
    })
    escrow_id = create_res.json()["escrow_id"]

    # Try selling unfunded escrow
    res = client.post(f"/api/v1/escrows/{escrow_id}/sell", json={
        "requested_by": "acc_buyer_001"
    })
    assert res.status_code == 400

def test_refund_flow():
    # Create & Fund
    c_res = client.post("/api/v1/escrows", json={
        "buyer_id": "acc_buyer_001",
        "seller_id": "acc_seller_001",
        "arbiter_id": "acc_arbiter_001",
        "amount": 30000,
        "title": "Defective item test"
    })
    escrow_id = c_res.json()["escrow_id"]
    client.post(f"/api/v1/escrows/{escrow_id}/buy", json={"buyer_id": "acc_buyer_001"})

    # Arbiter triggers refund
    refund_res = client.post(f"/api/v1/escrows/{escrow_id}/refund", json={
        "requested_by": "acc_arbiter_001",
        "reason": "Item failed inspection"
    })
    assert refund_res.status_code == 200
    assert refund_res.json()["status"] == "REFUNDED"
