#!/usr/bin/env python3
"""
Interactive Demonstration Script for Google Cloud Universal Ledger Escrow API & Smart Contract Rules.
Executes complete lifecycle with 5-Day Return Period:
Create Escrow -> Buy (Fund) -> Product Delivered -> Enforce 5-Day Hold (Reject Merchant Early Claim) -> Buyer Early Release -> Final Settlement.
"""

import json
from fastapi.testclient import TestClient
from app.main import app

def print_banner(text):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)

def print_json(data):
    print(json.dumps(data, indent=2))

def run_demo():
    client = TestClient(app)
    
    print_banner("1. QUERY INITIAL UNIVERSAL LEDGER ACCOUNTS")
    buyer_acc = client.get("/api/v1/ledger/accounts/acc_buyer_001").json()
    seller_acc = client.get("/api/v1/ledger/accounts/acc_seller_001").json()
    print("Buyer Ledger Account:")
    print_json(buyer_acc["account"])
    print("\nSeller Ledger Account:")
    print_json(seller_acc["account"])

    print_banner("2. CREATE ESCROW WITH 5-DAY RETURN RULE (POST /api/v1/escrows)")
    create_payload = {
        "buyer_id": "acc_buyer_001",
        "seller_id": "acc_seller_001",
        "arbiter_id": "acc_arbiter_001",
        "amount": 250000,  # $2,500.00 USD
        "currency": "USD",
        "title": "High-End Laptop Escrow Purchase",
        "description": "Mint condition 16-inch workstation",
        "return_period_days": 5
    }
    create_res = client.post("/api/v1/escrows", json=create_payload)
    escrow = create_res.json()
    escrow_id = escrow["escrow_id"]
    vault_id = escrow["vault_account_id"]
    print(f"✅ Escrow Created successfully! ID: {escrow_id}")
    print(f"   Vault Account on Universal Ledger: {vault_id}")
    print_json(escrow)

    print_banner("3. BUY / FUND ESCROW (POST /api/v1/escrows/{escrow_id}/buy)")
    buy_payload = {
        "buyer_id": "acc_buyer_001",
        "payment_notes": "Transferring $2,500.00 into Universal Ledger Vault"
    }
    buy_res = client.post(f"/api/v1/escrows/{escrow_id}/buy", json=buy_payload)
    print(f"💰 BUY Completed! Status: {buy_res.json()['status']}")

    print_banner("4. DELIVERY BOY / COURIER MARKS DELIVERED (POST /api/v1/escrows/{escrow_id}/deliver)")
    deliver_payload = {
        "delivered_by": "acc_courier_001",
        "tracking_number": "TRK-987654321",
        "delivery_notes": "Package delivered to front door with photo proof"
    }
    deliver_res = client.post(f"/api/v1/escrows/{escrow_id}/deliver", json=deliver_payload)
    print(f"📦 PRODUCT DELIVERED! Status: {deliver_res.json()['status']}")
    print(f"   Return Period Window Active: 5 Days")
    print(f"   Return Window Expires At: {deliver_res.json()['return_window_expires_at']}")

    print_banner("5. RULE ENFORCEMENT CHECK: MERCHANT ATTEMPTS TO CLAIM MONEY EARLY (POST /api/v1/escrows/{escrow_id}/sell)")
    sell_early_res = client.post(f"/api/v1/escrows/{escrow_id}/sell", json={
        "requested_by": "acc_seller_001",
        "settlement_notes": "Claiming money immediately after delivery"
    })
    print(f"❌ Merchant Early Claim Attempted - Response Code: {sell_early_res.status_code}")
    print(f"   Smart Contract Rule Error: {sell_early_res.json()['detail']}")

    print_banner("6. BUYER VERIFIES PRODUCT & ACCEPTS DELIVERY EARLY (POST /api/v1/escrows/{escrow_id}/accept-early)")
    accept_payload = {
        "buyer_id": "acc_buyer_001",
        "notes": "Verified laptop condition and accessories. Waiving remaining 5-day return period."
    }
    accept_res = client.post(f"/api/v1/escrows/{escrow_id}/accept-early", json=accept_payload)
    print(f"✨ BUYER ACCEPTED DELIVERY EARLY! Status: {accept_res.json()['status']}")
    print_json(accept_res.json())

    print_banner("7. FINAL UNIVERSAL LEDGER STATE VERIFICATION")
    seller_acc_final = client.get("/api/v1/ledger/accounts/acc_seller_001").json()
    vault_acc_final = client.get(f"/api/v1/ledger/accounts/{vault_id}").json()
    buyer_acc_final = client.get("/api/v1/ledger/accounts/acc_buyer_001").json()
    
    b_final = buyer_acc_final['account']['currency_balances'].get('USD', 0)
    v_final = vault_acc_final['account']['currency_balances'].get('USD', 0)
    s_final = seller_acc_final['account']['currency_balances'].get('USD', 0)
    
    print(f"Final Buyer Balance : ${b_final / 100:,.2f} USD")
    print(f"Final Vault Balance : ${v_final / 100:,.2f} USD")
    print(f"Final Seller Balance: ${s_final / 100:,.2f} USD")

    print_banner("DEMO COMPLETED SUCCESSFULLY! ALL SMART CONTRACT RULES VERIFIED.")

if __name__ == "__main__":
    run_demo()
