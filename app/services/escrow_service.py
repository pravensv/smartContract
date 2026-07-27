import time
import uuid
from typing import Dict, List, Optional
from fastapi import HTTPException, status
from app.config import settings
from app.ledger.client import UniversalLedgerClient
from app.ledger.logger import log_escrow_event
from app.ledger.schemas import (
    ClientTransaction, CurrencyValue, InvokeContractMethod, SignedTransaction,
    SubmitTransactionRequest, Transfer
)
from app.models.escrow import (
    BuyEscrowRequest, CreateEscrowRequest, EscrowResponse, EscrowStatus,
    HoldEscrowRequest, LedgerEventLog, RefundEscrowRequest, SellEscrowRequest
)

class EscrowService:
    def __init__(self, ledger_client: UniversalLedgerClient):
        self.ledger_client = ledger_client
        self._escrows: Dict[str, EscrowResponse] = {}

    def create_escrow(self, request: CreateEscrowRequest) -> EscrowResponse:
        escrow_uuid = str(uuid.uuid4())[:8]
        escrow_id = f"escrow_{escrow_uuid}"
        vault_account_id = f"acc_vault_{escrow_uuid}"

        # 1. Register Escrow Vault Account on Google Cloud Universal Ledger
        self.ledger_client.register_account(
            account_id=vault_account_id,
            comment=f"Escrow Vault for '{request.title}' ({escrow_id})",
            initial_balance=0,
            currency=request.currency
        )

        now = time.time()
        
        # 2. Record creation transaction on Universal Ledger
        tx = ClientTransaction(
            sender_id=request.buyer_id,
            sequence_number=1,
            chained_unit=False,
            invoke_contract_method_transaction=InvokeContractMethod(
                contract_id=vault_account_id,
                method_name="initialize_escrow",
                method_arguments={
                    "buyer_id": request.buyer_id,
                    "seller_id": request.seller_id,
                    "arbiter_id": request.arbiter_id,
                    "amount": request.amount,
                    "currency": request.currency,
                    "title": request.title
                }
            )
        )
        
        res = self.ledger_client.submit_transaction(
            SubmitTransactionRequest(
                endpoint=self.ledger_client.endpoint_name,
                transaction=SignedTransaction(client_transaction=tx, signature="sig_create_escrow")
            )
        )

        initial_log = LedgerEventLog(
            action="CREATE_ESCROW",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 100,
            timestamp=now,
            details={"title": request.title, "amount": str(request.amount), "vault": vault_account_id}
        )

        escrow_response = EscrowResponse(
            escrow_id=escrow_id,
            buyer_id=request.buyer_id,
            seller_id=request.seller_id,
            arbiter_id=request.arbiter_id or "acc_arbiter_001",
            vault_account_id=vault_account_id,
            amount=request.amount,
            currency=request.currency,
            status=EscrowStatus.CREATED,
            title=request.title,
            description=request.description or "",
            created_at=now,
            updated_at=now,
            last_transaction_digest=res.transaction_digest_hex,
            ledger_round_id=res.certificate.round_id if res.certificate else 100,
            ledger_history=[initial_log]
        )

        self._escrows[escrow_id] = escrow_response
        
        # Emit GCP Cloud Log
        log_escrow_event(
            action="CREATE_ESCROW",
            title=request.title,
            escrow_id=escrow_id,
            status="CREATED",
            details={"amount": request.amount, "currency": request.currency, "buyer": request.buyer_id, "seller": request.seller_id}
        )

        return escrow_response

    def buy_escrow(self, escrow_id: str, request: BuyEscrowRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        if escrow.status != EscrowStatus.CREATED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot buy escrow in '{escrow.status}' state. Must be in 'CREATED' state."
            )

        if request.buyer_id != escrow.buyer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only designated buyer '{escrow.buyer_id}' can perform buy funding. Provided: '{request.buyer_id}'"
            )

        now = time.time()

        tx = ClientTransaction(
            sender_id=escrow.buyer_id,
            sequence_number=2,
            chained_unit=False,
            transfer_transaction=Transfer(
                payer_id=escrow.buyer_id,
                beneficiary_id=escrow.vault_account_id,
                amount=CurrencyValue(value=escrow.amount)
            )
        )

        try:
            res = self.ledger_client.submit_transaction(
                SubmitTransactionRequest(
                    endpoint=self.ledger_client.endpoint_name,
                    transaction=SignedTransaction(
                        client_transaction=tx,
                        signature=f"sig_buy_funding_{escrow.buyer_id}"
                    )
                )
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

        event_log = LedgerEventLog(
            action="BUY_FUNDED",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 101,
            timestamp=now,
            details={"buyer_id": request.buyer_id, "amount": str(escrow.amount), "notes": request.payment_notes or ""}
        )

        escrow.status = EscrowStatus.FUNDED
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)

        # Emit GCP Cloud Log
        log_escrow_event(
            action="BUY_FUNDED",
            title=escrow.title,
            escrow_id=escrow_id,
            status="FUNDED",
            details={"buyer_id": request.buyer_id, "amount": escrow.amount, "notes": request.payment_notes or ""}
        )

        return escrow

    def hold_escrow(self, escrow_id: str, request: HoldEscrowRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        valid_actors = {escrow.buyer_id, escrow.seller_id, escrow.arbiter_id}
        if request.requested_by not in valid_actors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account '{request.requested_by}' is not authorized to hold this escrow."
            )

        if escrow.status not in [EscrowStatus.FUNDED, EscrowStatus.CREATED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot put escrow on hold from '{escrow.status}' state."
            )

        now = time.time()

        tx = ClientTransaction(
            sender_id=request.requested_by,
            sequence_number=3,
            chained_unit=False,
            invoke_contract_method_transaction=InvokeContractMethod(
                contract_id=escrow.vault_account_id,
                method_name="set_hold_status",
                method_arguments={
                    "requested_by": request.requested_by,
                    "reason": request.reason,
                    "hold_active": True
                }
            )
        )

        res = self.ledger_client.submit_transaction(
            SubmitTransactionRequest(
                endpoint=self.ledger_client.endpoint_name,
                transaction=SignedTransaction(
                    client_transaction=tx,
                    signature=f"sig_hold_{request.requested_by}"
                )
            )
        )

        event_log = LedgerEventLog(
            action="HOLD_LOCKED",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 102,
            timestamp=now,
            details={"requested_by": request.requested_by, "reason": request.reason}
        )

        escrow.status = EscrowStatus.HELD
        escrow.hold_reason = request.reason
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)

        # Emit GCP Cloud Log
        log_escrow_event(
            action="HOLD_LOCKED",
            title=escrow.title,
            escrow_id=escrow_id,
            status="HELD",
            details={"requested_by": request.requested_by, "reason": request.reason}
        )

        return escrow

    def sell_escrow(self, escrow_id: str, request: SellEscrowRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        if escrow.status not in [EscrowStatus.FUNDED, EscrowStatus.HELD]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot release/sell escrow in '{escrow.status}' state. Must be 'FUNDED' or 'HELD'."
            )

        valid_actors = {escrow.buyer_id, escrow.arbiter_id, escrow.seller_id}
        if request.requested_by not in valid_actors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account '{request.requested_by}' is not authorized to release escrow funds."
            )

        now = time.time()

        tx = ClientTransaction(
            sender_id=escrow.vault_account_id,
            sequence_number=4,
            chained_unit=False,
            other_signatory_ids=[request.requested_by],
            transfer_transaction=Transfer(
                payer_id=escrow.vault_account_id,
                beneficiary_id=escrow.seller_id,
                amount=CurrencyValue(value=escrow.amount)
            )
        )

        try:
            res = self.ledger_client.submit_transaction(
                SubmitTransactionRequest(
                    endpoint=self.ledger_client.endpoint_name,
                    transaction=SignedTransaction(
                        client_transaction=tx,
                        signature=f"sig_sell_release_{request.requested_by}",
                        signatories=[request.requested_by]
                    )
                )
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

        event_log = LedgerEventLog(
            action="SELL_RELEASED",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 103,
            timestamp=now,
            details={
                "requested_by": request.requested_by,
                "seller_id": escrow.seller_id,
                "amount": str(escrow.amount),
                "notes": request.settlement_notes or ""
            }
        )

        escrow.status = EscrowStatus.RELEASED
        escrow.hold_reason = None
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)

        # Emit GCP Cloud Log
        log_escrow_event(
            action="SELL_RELEASED",
            title=escrow.title,
            escrow_id=escrow_id,
            status="RELEASED",
            details={"requested_by": request.requested_by, "seller_id": escrow.seller_id, "amount": escrow.amount}
        )

        return escrow

    def refund_escrow(self, escrow_id: str, request: RefundEscrowRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        if escrow.status not in [EscrowStatus.FUNDED, EscrowStatus.HELD, EscrowStatus.DISPUTED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot refund escrow in '{escrow.status}' state."
            )

        valid_actors = {escrow.seller_id, escrow.arbiter_id}
        if request.requested_by not in valid_actors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account '{request.requested_by}' is not authorized to refund buyer."
            )

        now = time.time()

        tx = ClientTransaction(
            sender_id=escrow.vault_account_id,
            sequence_number=5,
            chained_unit=False,
            other_signatory_ids=[request.requested_by],
            transfer_transaction=Transfer(
                payer_id=escrow.vault_account_id,
                beneficiary_id=escrow.buyer_id,
                amount=CurrencyValue(value=escrow.amount)
            )
        )

        try:
            res = self.ledger_client.submit_transaction(
                SubmitTransactionRequest(
                    endpoint=self.ledger_client.endpoint_name,
                    transaction=SignedTransaction(
                        client_transaction=tx,
                        signature=f"sig_refund_{request.requested_by}",
                        signatories=[request.requested_by]
                    )
                )
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

        event_log = LedgerEventLog(
            action="REFUNDED",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 104,
            timestamp=now,
            details={"requested_by": request.requested_by, "reason": request.reason}
        )

        escrow.status = EscrowStatus.REFUNDED
        escrow.hold_reason = None
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)

        # Emit GCP Cloud Log
        log_escrow_event(
            action="REFUNDED",
            title=escrow.title,
            escrow_id=escrow_id,
            status="REFUNDED",
            details={"requested_by": request.requested_by, "reason": request.reason}
        )

        return escrow

    def get_escrow(self, escrow_id: str) -> EscrowResponse:
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Escrow with ID '{escrow_id}' not found."
            )
        return escrow

    def list_escrows(self, title: Optional[str] = None) -> List[EscrowResponse]:
        if title:
            return [e for e in self._escrows.values() if title.lower() in e.title.lower()]
        return list(self._escrows.values())
