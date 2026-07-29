import logging
from typing import List
from fastapi import APIRouter, Depends, status
from app.models.escrow import (
    AcceptDeliveryEarlyRequest, BuyEscrowRequest, CreateEscrowRequest,
    DeliverEscrowRequest, EscrowResponse, HoldEscrowRequest,
    RefundEscrowRequest, RequestReturnRequest, SellEscrowRequest, TransitEscrowRequest
)
from app.services.escrow_service import EscrowService

logger = logging.getLogger("escrow_router")
router = APIRouter(prefix="/api/v1/escrows", tags=["Escrow Operations"])

_escrow_service_instance: EscrowService = None

def get_escrow_service() -> EscrowService:
    if _escrow_service_instance is None:
        raise RuntimeError("EscrowService instance is not initialized.")
    return _escrow_service_instance

def set_escrow_service(service: EscrowService):
    global _escrow_service_instance
    _escrow_service_instance = service

@router.post("", response_model=EscrowResponse, status_code=status.HTTP_201_CREATED, summary="Create a new Escrow")
def create_escrow(
    request: CreateEscrowRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"🚀 [POST /api/v1/escrows] CREATING ESCROW")
    print(f"   Title        : {request.title}")
    print(f"   Buyer        : {request.buyer_id}")
    print(f"   Seller       : {request.seller_id}")
    print(f"   Amount       : {request.amount} {request.currency}")
    print(f"   Return Period: {getattr(request, 'return_period_seconds', 30)} Seconds")
    print("="*80)
    return service.create_escrow(request)

@router.get("", response_model=List[EscrowResponse], summary="List all Escrows")
def list_escrows(
    service: EscrowService = Depends(get_escrow_service)
) -> List[EscrowResponse]:
    return service.list_escrows()

@router.get("/{escrow_id}", response_model=EscrowResponse, summary="Get Escrow Details")
def get_escrow(
    escrow_id: str,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    return service.get_escrow(escrow_id)

@router.post("/{escrow_id}/buy", response_model=EscrowResponse, summary="Buy / Fund Escrow")
def buy_escrow(
    escrow_id: str,
    request: BuyEscrowRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"💰 [POST /api/v1/escrows/{escrow_id}/buy] FUNDING ESCROW")
    print(f"   Buyer   : {request.buyer_id}")
    print(f"   Notes   : {request.payment_notes}")
    print("="*80)
    return service.buy_escrow(escrow_id, request)

@router.post("/{escrow_id}/transit", response_model=EscrowResponse, summary="Mark Product as In Transit (Merchant / Courier)")
def transit_escrow(
    escrow_id: str,
    request: TransitEscrowRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"🚚 [POST /api/v1/escrows/{escrow_id}/transit] MARKING PRODUCT IN TRANSIT")
    print(f"   Updated By      : {request.updated_by}")
    print(f"   Tracking Number : {request.tracking_number}")
    print(f"   Transit Notes   : {request.transit_notes}")
    print("="*80)
    return service.transit_escrow(escrow_id, request)

@router.post("/{escrow_id}/deliver", response_model=EscrowResponse, summary="Mark Product as Delivered (Delivery Boy / Courier)")
def deliver_escrow(
    escrow_id: str,
    request: DeliverEscrowRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"📦 [POST /api/v1/escrows/{escrow_id}/deliver] MARKING PRODUCT DELIVERED")
    print(f"   Delivered By    : {request.delivered_by}")
    print(f"   Tracking Number : {request.tracking_number}")
    print(f"   Courier Notes   : {request.delivery_notes}")
    print("="*80)
    return service.deliver_escrow(escrow_id, request)

@router.post("/{escrow_id}/request-return", response_model=EscrowResponse, summary="Buyer Request Product Return (Within 5-day window)")
def request_return(
    escrow_id: str,
    request: RequestReturnRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"↩️ [POST /api/v1/escrows/{escrow_id}/request-return] REQUESTING PRODUCT RETURN")
    print(f"   Buyer   : {request.buyer_id}")
    print(f"   Reason  : {request.reason}")
    print("="*80)
    return service.request_return(escrow_id, request)

@router.post("/{escrow_id}/accept-early", response_model=EscrowResponse, summary="Buyer Accept Delivery Early (Waive return period)")
def accept_delivery_early(
    escrow_id: str,
    request: AcceptDeliveryEarlyRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"✨ [POST /api/v1/escrows/{escrow_id}/accept-early] ACCEPTING DELIVERY EARLY")
    print(f"   Buyer   : {request.buyer_id}")
    print(f"   Notes   : {request.notes}")
    print("="*80)
    return service.accept_delivery_early(escrow_id, request)

@router.post("/{escrow_id}/hold", response_model=EscrowResponse, summary="Put Escrow on Hold")
def hold_escrow(
    escrow_id: str,
    request: HoldEscrowRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"🔒 [POST /api/v1/escrows/{escrow_id}/hold] LOCKING ESCROW ON HOLD")
    print(f"   By      : {request.requested_by}")
    print(f"   Reason  : {request.reason}")
    print("="*80)
    return service.hold_escrow(escrow_id, request)

@router.post("/{escrow_id}/sell", response_model=EscrowResponse, summary="Sell / Release Escrow to Seller (Merchant)")
def sell_escrow(
    escrow_id: str,
    request: SellEscrowRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"✅ [POST /api/v1/escrows/{escrow_id}/sell] SELLING / RELEASING FUNDS TO SELLER")
    print(f"   By      : {request.requested_by}")
    print(f"   Notes   : {request.settlement_notes}")
    print("="*80)
    return service.sell_escrow(escrow_id, request)

@router.post("/{escrow_id}/refund", response_model=EscrowResponse, summary="Refund Escrow to Buyer")
def refund_escrow(
    escrow_id: str,
    request: RefundEscrowRequest,
    service: EscrowService = Depends(get_escrow_service)
) -> EscrowResponse:
    print("\n" + "="*80)
    print(f"💸 [POST /api/v1/escrows/{escrow_id}/refund] REFUNDING ESCROW TO BUYER")
    print(f"   By      : {request.requested_by}")
    print(f"   Reason  : {request.reason}")
    print("="*80)
    return service.refund_escrow(escrow_id, request)
