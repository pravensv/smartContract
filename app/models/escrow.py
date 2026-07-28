from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

class EscrowStatus(str, Enum):
    CREATED = "CREATED"
    FUNDED = "FUNDED"
    DELIVERED = "DELIVERED"  # Product delivered by courier, 5-day return window active
    HELD = "HELD"
    RELEASED = "RELEASED"    # Completed Sell operation (Funds released to merchant)
    REFUNDED = "REFUNDED"
    DISPUTED = "DISPUTED"

class CreateEscrowRequest(BaseModel):
    buyer_id: str = Field(..., description="Ledger account ID of the buyer (e.g. acc_buyer_001)", json_schema_extra={"example": "acc_buyer_001"})
    seller_id: str = Field(..., description="Ledger account ID of the seller (e.g. acc_seller_001)", json_schema_extra={"example": "acc_seller_001"})
    arbiter_id: Optional[str] = Field("acc_arbiter_001", description="Ledger account ID of neutral escrow arbiter/agent")
    amount: int = Field(..., gt=0, description="Escrow amount in minor units (e.g. 50000 = $500.00 USD)", json_schema_extra={"example": 50000})
    currency: str = Field("USD", description="3-letter currency code (ISO 4217)")
    title: str = Field(..., description="Title of item or agreement", json_schema_extra={"example": "MacBook Pro Purchase Escrow"})
    description: Optional[str] = Field("", description="Additional terms or contract details")
    return_period_days: int = Field(5, description="Return period window in days (default 5 days)")

class BuyEscrowRequest(BaseModel):
    buyer_id: str = Field(..., description="Ledger account ID of the buyer funding the escrow")
    payment_notes: Optional[str] = Field(None, description="Optional payment memo or purchase order reference")

class DeliverEscrowRequest(BaseModel):
    delivered_by: str = Field(..., description="Account ID of delivery agent / courier / seller marking product delivered")
    tracking_number: Optional[str] = Field(None, description="Package tracking number (e.g. TRK-88902)")
    delivery_notes: Optional[str] = Field("Delivered to recipient address", description="Proof of delivery or courier notes")

class RequestReturnRequest(BaseModel):
    buyer_id: str = Field(..., description="Buyer account ID requesting product return during 5-day window")
    reason: str = Field(..., description="Reason for product return (e.g. Defective item, wrong size, item not as described)")

class AcceptDeliveryEarlyRequest(BaseModel):
    buyer_id: str = Field(..., description="Buyer account ID approving early settlement (waiving remaining 5-day return window)")
    notes: Optional[str] = Field(None, description="Buyer feedback or approval notes")

class HoldEscrowRequest(BaseModel):
    requested_by: str = Field(..., description="Account ID requesting to put funds on hold (buyer, seller, or arbiter)")
    reason: str = Field(..., description="Reason for holding escrow (e.g. Inspection pending, item damaged in transit)")

class SellEscrowRequest(BaseModel):
    requested_by: str = Field(..., description="Account ID approving/triggering the release of funds to seller (seller, buyer, or arbiter)")
    settlement_notes: Optional[str] = Field(None, description="Optional fulfillment/delivery reference")

class RefundEscrowRequest(BaseModel):
    requested_by: str = Field(..., description="Account ID authorizing refund to buyer (seller or arbiter)")
    reason: str = Field(..., description="Reason for refund")

class LedgerEventLog(BaseModel):
    action: str
    transaction_digest_hex: str
    round_id: int
    timestamp: float
    details: Dict[str, str] = Field(default_factory=dict)

class EscrowResponse(BaseModel):
    escrow_id: str
    buyer_id: str
    seller_id: str
    arbiter_id: str
    vault_account_id: str
    amount: int
    currency: str
    status: EscrowStatus
    title: str
    description: str
    created_at: float
    updated_at: float
    delivered_at: Optional[float] = None
    return_period_days: int = 5
    return_window_expires_at: Optional[float] = None
    delivery_tracking_info: Optional[str] = None
    hold_reason: Optional[str] = None
    last_transaction_digest: Optional[str] = None
    ledger_round_id: Optional[int] = None
    ledger_history: List[LedgerEventLog] = Field(default_factory=list)
