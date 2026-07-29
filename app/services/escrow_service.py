import time
import threading
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
    AcceptDeliveryEarlyRequest, BuyEscrowRequest, CreateEscrowRequest,
    DeliverEscrowRequest, EscrowResponse, EscrowStatus, HoldEscrowRequest,
    LedgerEventLog, RefundEscrowRequest, RequestReturnRequest, SellEscrowRequest, TransitEscrowRequest
)

class EscrowService:
    def __init__(self, ledger_client: UniversalLedgerClient):
        self.ledger_client = ledger_client
        self._escrows: Dict[str, EscrowResponse] = {}
        self._delivery_release_timers: Dict[str, threading.Timer] = {}
        self._hold_release_timers: Dict[str, threading.Timer] = {}
        self._lock = threading.RLock()

    def _schedule_delivery_auto_release(self, escrow_id: str, delay_seconds: int) -> None:
        self._cancel_delivery_auto_release(escrow_id)

        timer = threading.Timer(
            delay_seconds,
            self._auto_release_delivered_escrow,
            args=(escrow_id,)
        )
        timer.daemon = True
        self._delivery_release_timers[escrow_id] = timer
        timer.start()

    def _cancel_delivery_auto_release(self, escrow_id: str) -> None:
        timer = self._delivery_release_timers.pop(escrow_id, None)
        if timer:
            timer.cancel()

    def _schedule_hold_auto_release(self, escrow_id: str, delay_seconds: int) -> None:
        self._cancel_hold_auto_release(escrow_id)

        timer = threading.Timer(
            delay_seconds,
            self._auto_release_held_escrow,
            args=(escrow_id,)
        )
        timer.daemon = True
        self._hold_release_timers[escrow_id] = timer
        timer.start()

    def _cancel_hold_auto_release(self, escrow_id: str) -> None:
        timer = self._hold_release_timers.pop(escrow_id, None)
        if timer:
            timer.cancel()

    def _auto_release_delivered_escrow(self, escrow_id: str) -> None:
        with self._lock:
            escrow = self._escrows.get(escrow_id)
            if not escrow or escrow.status != EscrowStatus.DELIVERED:
                self._delivery_release_timers.pop(escrow_id, None)
                return

            self._delivery_release_timers.pop(escrow_id, None)

            try:
                self.sell_escrow(
                    escrow_id,
                    SellEscrowRequest(
                        requested_by=escrow.arbiter_id,
                        settlement_notes="Auto-release after delivery return window completed"
                    )
                )
            except Exception as err:
                log_escrow_event(
                    action="AUTO_RELEASE_FAILED",
                    title=escrow.title,
                    escrow_id=escrow_id,
                    status=escrow.status.value,
                    details={"error": str(err)}
                )

    def _auto_release_held_escrow(self, escrow_id: str) -> None:
        with self._lock:
            escrow = self._escrows.get(escrow_id)
            if not escrow or escrow.status != EscrowStatus.HELD:
                self._hold_release_timers.pop(escrow_id, None)
                return

            self._hold_release_timers.pop(escrow_id, None)

            try:
                self.sell_escrow(
                    escrow_id,
                    SellEscrowRequest(
                        requested_by=escrow.arbiter_id,
                        settlement_notes="Auto-release after 59 seconds in HOLD state without refund"
                    )
                )
            except Exception as err:
                log_escrow_event(
                    action="HOLD_AUTO_RELEASE_FAILED",
                    title=escrow.title,
                    escrow_id=escrow_id,
                    status=escrow.status.value,
                    details={"error": str(err)}
                )

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
                    "title": request.title,
                    "return_period_days": request.return_period_days
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
            return_period_seconds=request.return_period_seconds or 30,
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

    def transit_escrow(self, escrow_id: str, request: TransitEscrowRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        if escrow.status != EscrowStatus.FUNDED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot mark escrow as IN_TRANSIT in '{escrow.status}' state. Must be in 'FUNDED' state."
            )

        now = time.time()

        tx = ClientTransaction(
            sender_id=request.updated_by,
            sequence_number=3,
            chained_unit=False,
            invoke_contract_method_transaction=InvokeContractMethod(
                contract_id=escrow.vault_account_id,
                method_name="mark_in_transit",
                method_arguments={
                    "updated_by": request.updated_by,
                    "tracking_number": request.tracking_number or "",
                    "transit_at": now
                }
            )
        )

        res = self.ledger_client.submit_transaction(
            SubmitTransactionRequest(
                endpoint=self.ledger_client.endpoint_name,
                transaction=SignedTransaction(
                    client_transaction=tx,
                    signature=f"sig_transit_{request.updated_by}"
                )
            )
        )

        event_log = LedgerEventLog(
            action="PRODUCT_IN_TRANSIT",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 102,
            timestamp=now,
            details={
                "updated_by": request.updated_by,
                "tracking_number": request.tracking_number or "N/A",
                "notes": request.transit_notes or ""
            }
        )

        escrow.status = EscrowStatus.IN_TRANSIT
        escrow.delivery_tracking_info = request.tracking_number
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)

        log_escrow_event(
            action="PRODUCT_IN_TRANSIT",
            title=escrow.title,
            escrow_id=escrow_id,
            status="IN_TRANSIT",
            details={
                "updated_by": request.updated_by,
                "tracking": request.tracking_number
            }
        )

        return escrow

    def deliver_escrow(self, escrow_id: str, request: DeliverEscrowRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        if escrow.status not in [EscrowStatus.FUNDED, EscrowStatus.IN_TRANSIT]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot mark escrow as delivered in '{escrow.status}' state. Must be in 'FUNDED' or 'IN_TRANSIT' state."
            )

        valid_actors = {escrow.seller_id, escrow.buyer_id, escrow.arbiter_id, request.delivered_by}
        if request.delivered_by not in valid_actors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account '{request.delivered_by}' is not authorized to update delivery status."
            )

        now = time.time()
        expires_at = now + (escrow.return_period_seconds or 30)

        tx = ClientTransaction(
            sender_id=request.delivered_by,
            sequence_number=3,
            chained_unit=False,
            invoke_contract_method_transaction=InvokeContractMethod(
                contract_id=escrow.vault_account_id,
                method_name="mark_delivered",
                method_arguments={
                    "delivered_by": request.delivered_by,
                    "tracking_number": request.tracking_number or "",
                    "delivered_at": now,
                    "return_expires_at": expires_at
                }
            )
        )

        res = self.ledger_client.submit_transaction(
            SubmitTransactionRequest(
                endpoint=self.ledger_client.endpoint_name,
                transaction=SignedTransaction(
                    client_transaction=tx,
                    signature=f"sig_deliver_{request.delivered_by}"
                )
            )
        )

        event_log = LedgerEventLog(
            action="PRODUCT_DELIVERED",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 102,
            timestamp=now,
            details={
                "delivered_by": request.delivered_by,
                "tracking_number": request.tracking_number or "N/A",
                "notes": request.delivery_notes or "",
                "return_expires_at": str(expires_at)
            }
        )

        escrow.status = EscrowStatus.DELIVERED
        escrow.delivered_at = now
        escrow.return_window_expires_at = expires_at
        escrow.delivery_tracking_info = request.tracking_number
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)
        self._schedule_delivery_auto_release(escrow_id, escrow.return_period_seconds or 30)

        # Emit GCP Cloud Log
        log_escrow_event(
            action="PRODUCT_DELIVERED",
            title=escrow.title,
            escrow_id=escrow_id,
            status="DELIVERED",
            details={
                "delivered_by": request.delivered_by,
                "tracking": request.tracking_number,
                "return_window_days": escrow.return_period_days
            }
        )

        return escrow

    def request_return(self, escrow_id: str, request: RequestReturnRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        if escrow.status != EscrowStatus.DELIVERED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot request product return in '{escrow.status}' state. Must be in 'DELIVERED' state."
            )

        if request.buyer_id != escrow.buyer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only designated buyer '{escrow.buyer_id}' can request a return."
            )

        now = time.time()
        return_expires = escrow.return_window_expires_at or ((escrow.delivered_at or now) + (escrow.return_period_seconds or 30))
        if now > return_expires:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The {escrow.return_period_seconds or 30}-second return period has expired. Return requests are no longer allowed."
            )

        tx = ClientTransaction(
            sender_id=request.buyer_id,
            sequence_number=4,
            chained_unit=False,
            invoke_contract_method_transaction=InvokeContractMethod(
                contract_id=escrow.vault_account_id,
                method_name="request_return",
                method_arguments={
                    "buyer_id": request.buyer_id,
                    "reason": request.reason
                }
            )
        )

        res = self.ledger_client.submit_transaction(
            SubmitTransactionRequest(
                endpoint=self.ledger_client.endpoint_name,
                transaction=SignedTransaction(
                    client_transaction=tx,
                    signature=f"sig_return_{request.buyer_id}"
                )
            )
        )

        event_log = LedgerEventLog(
            action="RETURN_REQUESTED",
            transaction_digest_hex=res.transaction_digest_hex,
            round_id=res.certificate.round_id if res.certificate else 103,
            timestamp=now,
            details={"buyer_id": request.buyer_id, "reason": request.reason}
        )

        escrow.status = EscrowStatus.REFUNDED
        escrow.hold_reason = f"Product Returned & Money Refunded: {request.reason}"
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)
        self._cancel_delivery_auto_release(escrow_id)
        self._schedule_hold_auto_release(escrow_id, escrow.return_period_seconds or 30)

        log_escrow_event(
            action="RETURN_REFUNDED",
            title=escrow.title,
            escrow_id=escrow_id,
            status="REFUNDED",
            details={"buyer_id": request.buyer_id, "reason": request.reason}
        )

        return escrow

    def accept_delivery_early(self, escrow_id: str, request: AcceptDeliveryEarlyRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        if escrow.status != EscrowStatus.DELIVERED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot accept delivery early in '{escrow.status}' state. Must be 'DELIVERED'."
            )

        if request.buyer_id != escrow.buyer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Only designated buyer '{escrow.buyer_id}' can accept delivery early."
            )

        # Trigger sell release
        return self.sell_escrow(
            escrow_id,
            SellEscrowRequest(
                requested_by=request.buyer_id,
                settlement_notes=request.notes or "Buyer accepted delivery early (waived return period)"
            )
        )

    def hold_escrow(self, escrow_id: str, request: HoldEscrowRequest) -> EscrowResponse:
        escrow = self.get_escrow(escrow_id)

        valid_actors = {escrow.buyer_id, escrow.seller_id, escrow.arbiter_id}
        if request.requested_by not in valid_actors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account '{request.requested_by}' is not authorized to hold this escrow."
            )

        if escrow.status not in [EscrowStatus.FUNDED, EscrowStatus.CREATED, EscrowStatus.DELIVERED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot put escrow on hold from '{escrow.status}' state."
            )

        now = time.time()

        tx = ClientTransaction(
            sender_id=request.requested_by,
            sequence_number=5,
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
            round_id=res.certificate.round_id if res.certificate else 104,
            timestamp=now,
            details={"requested_by": request.requested_by, "reason": request.reason}
        )

        escrow.status = EscrowStatus.HELD
        escrow.hold_reason = request.reason
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)
        self._cancel_delivery_auto_release(escrow_id)
        self._schedule_hold_auto_release(escrow_id, escrow.return_period_seconds or 30)

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

        # 1. Status MUST be DELIVERED or HELD (for dispute resolution)
        escrow_status_str = escrow.status.value if hasattr(escrow.status, 'value') else str(escrow.status)
        if escrow.status not in [EscrowStatus.DELIVERED, EscrowStatus.HELD]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot release/sell escrow in '{escrow_status_str}' state. Escrow status MUST be 'DELIVERED'."
            )

        valid_actors = {escrow.buyer_id, escrow.arbiter_id, escrow.seller_id}
        if request.requested_by not in valid_actors:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account '{request.requested_by}' is not authorized to release escrow funds."
            )

        now = time.time()
        is_buyer_or_arbiter = request.requested_by in {escrow.buyer_id, escrow.arbiter_id}

        # 2. If DELIVERED, Delivery Time & 30-Second Return Window MUST be checked
        if escrow.status == EscrowStatus.DELIVERED:
            return_sec = escrow.return_period_seconds if hasattr(escrow, "return_period_seconds") and escrow.return_period_seconds else 30
            return_expires = escrow.return_window_expires_at
            if not return_expires:
                delivered_time = escrow.delivered_at or now
                return_expires = delivered_time + return_sec

            if now < return_expires and not is_buyer_or_arbiter:
                secs_left = round(return_expires - now, 1)
                if secs_left <= 0:
                    secs_left = float(return_sec)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Money is held during the {return_sec}-second return window. Escrow funds cannot be released until the return period expires ({secs_left} seconds remaining). Use /accept-early to waive return window."
                )
        elif escrow.status == EscrowStatus.HELD and not is_buyer_or_arbiter:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rule Violation: Cannot release held funds without Buyer or Arbiter authorization."
            )

        tx = ClientTransaction(
            sender_id=escrow.vault_account_id,
            sequence_number=6,
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
            round_id=res.certificate.round_id if res.certificate else 105,
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
        self._cancel_delivery_auto_release(escrow_id)
        self._cancel_hold_auto_release(escrow_id)

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

        if escrow.status not in [EscrowStatus.FUNDED, EscrowStatus.DELIVERED, EscrowStatus.HELD, EscrowStatus.DISPUTED]:
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
            sequence_number=7,
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
            round_id=res.certificate.round_id if res.certificate else 106,
            timestamp=now,
            details={"requested_by": request.requested_by, "reason": request.reason}
        )

        escrow.status = EscrowStatus.REFUNDED
        escrow.hold_reason = None
        escrow.updated_at = now
        escrow.last_transaction_digest = res.transaction_digest_hex
        escrow.ledger_round_id = res.certificate.round_id if res.certificate else escrow.ledger_round_id
        escrow.ledger_history.append(event_log)
        self._cancel_delivery_auto_release(escrow_id)
        self._cancel_hold_auto_release(escrow_id)

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
