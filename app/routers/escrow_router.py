import logging
from typing import List
from fastapi import APIRouter, Depends, status
from app.models.escrow import (
    BuyEscrowRequest, CreateEscrowRequest, EscrowResponse, HoldEscrowRequest,
    RefundEscrowRequest, SellEscrowRequest
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
    print(f"   Title   : {request.title}")
    print(f"   Buyer   : {request.buyer_id}")
    print(f"   Seller  : {request.seller_id}")
    print(f"   Amount  : {request.amount} {request.currency}")
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

@router.post("/{escrow_id}/sell", response_model=EscrowResponse, summary="Sell / Release Escrow to Seller")
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
    print(f"↩️ [POST /api/v1/escrows/{escrow_id}/refund] REFUNDING ESCROW TO BUYER")
    print(f"   By      : {request.requested_by}")
    print(f"   Reason  : {request.reason}")
    print("="*80)
    return service.refund_escrow(escrow_id, request)
