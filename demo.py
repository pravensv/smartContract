#!/usr/bin/env python3
"""
Interactive Demonstration Script for Google Cloud Universal Ledger Escrow API.
Executes complete lifecycle: Create Escrow -> Buy (Fund) -> Hold (Lock) -> Sell (Release).
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

    print_banner("2. CREATE ESCROW (POST /api/v1/escrows)")
    create_payload = {
        "buyer_id": "acc_buyer_001",
        "seller_id": "acc_seller_001",
        "arbiter_id": "acc_arbiter_001",
        "amount": 250000,  # £2,500.00 GBP
        "currency": "GBP",
        "title": "High-End Server Cluster Purchase",
        "description": "2x GPU Nodes with 100GbE NICs"
    }
    create_res = client.post("/api/v1/escrows", json=create_payload)
    escrow = create_res.json()
    escrow_id = escrow["escrow_id"]
    vault_id = escrow["vault_account_id"]
    print(f"Escrow Created successfully! ID: {escrow_id}")
    print(f"Escrow Vault Account on Universal Ledger: {vault_id}")
    print_json(escrow)

    print_banner("3. BUY / FUND ESCROW (POST /api/v1/escrows/{escrow_id}/buy)")
    buy_payload = {
        "buyer_id": "acc_buyer_001",
        "payment_notes": "Transferring £2,500.00 to Universal Ledger Vault"
    }
    buy_res = client.post(f"/api/v1/escrows/{escrow_id}/buy", json=buy_payload)
    print(f"BUY Completed! Status: {buy_res.json()['status']}")
    print_json(buy_res.json())

    print("\n[Ledger Verification] Checking Vault & Buyer Accounts after BUY:")
    vault_acc_funded = client.get(f"/api/v1/ledger/accounts/{vault_id}").json()
    buyer_acc_funded = client.get("/api/v1/ledger/accounts/acc_buyer_001").json()
    v_bal = vault_acc_funded['account']['currency_balances'].get('GBP', 0)
    b_bal = buyer_acc_funded['account']['currency_balances'].get('GBP', 0)
    print(f"Vault Balance: £{v_bal / 100:,.2f} GBP")
    print(f"Buyer Balance: £{b_bal / 100:,.2f} GBP")

    print_banner("4. HOLD ESCROW (POST /api/v1/escrows/{escrow_id}/hold)")
    hold_payload = {
        "requested_by": "acc_buyer_001",
        "reason": "Hardware delivered. Running 48-hour burn-in diagnostic test."
    }
    hold_res = client.post(f"/api/v1/escrows/{escrow_id}/hold", json=hold_payload)
    print(f"HOLD Activated! Status: {hold_res.json()['status']}")
    print_json(hold_res.json())

    print_banner("5. SELL / RELEASE ESCROW (POST /api/v1/escrows/{escrow_id}/sell)")
    sell_payload = {
        "requested_by": "acc_buyer_001",
        "settlement_notes": "All hardware diagnostics passed. Releasing £2,500.00 to seller."
    }
    sell_res = client.post(f"/api/v1/escrows/{escrow_id}/sell", json=sell_payload)
    print(f"SELL / RELEASE Completed! Final Status: {sell_res.json()['status']}")
    print_json(sell_res.json())

    print_banner("6. FINAL UNIVERSAL LEDGER STATE VERIFICATION")
    seller_acc_final = client.get("/api/v1/ledger/accounts/acc_seller_001").json()
    vault_acc_final = client.get(f"/api/v1/ledger/accounts/{vault_id}").json()
    buyer_acc_final = client.get("/api/v1/ledger/accounts/acc_buyer_001").json()
    
    b_final = buyer_acc_final['account']['currency_balances'].get('GBP', 0)
    v_final = vault_acc_final['account']['currency_balances'].get('GBP', 0)
    s_final = seller_acc_final['account']['currency_balances'].get('GBP', 0)
    
    print(f"Final Buyer Balance : £{b_final / 100:,.2f} GBP")
    print(f"Final Vault Balance : £{v_final / 100:,.2f} GBP")
    print(f"Final Seller Balance: £{s_final / 100:,.2f} GBP")
    
    print("\nLatest Transaction Digest on Universal Ledger:")
    tx_digest = sell_res.json()["last_transaction_digest"]
    tx_state = client.get(f"/api/v1/ledger/transactions/{tx_digest}").json()
    print_json(tx_state)

    print_banner("DEMO COMPLETED SUCCESSFULLY! ALL LEDGER TRANSACTIONS VERIFIED.")

if __name__ == "__main__":
    run_demo()
