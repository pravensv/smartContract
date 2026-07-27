from fastapi import APIRouter, Depends, HTTPException, status
from app.ledger.client import UniversalLedgerClient
from app.ledger.schemas import (
    ListEndpointsRequest, ListEndpointsResponse, QueryAccountRequest,
    QueryAccountResponse, QueryTransactionStateRequest, QueryTransactionStateResponse
)

router = APIRouter(prefix="/api/v1/ledger", tags=["Universal Ledger Low-Level API"])

_ledger_client_instance: UniversalLedgerClient = None

def get_ledger_client() -> UniversalLedgerClient:
    if _ledger_client_instance is None:
        raise RuntimeError("UniversalLedgerClient is not initialized.")
    return _ledger_client_instance

def set_ledger_client(client: UniversalLedgerClient):
    global _ledger_client_instance
    _ledger_client_instance = client

@router.get("/accounts/{account_id}", response_model=QueryAccountResponse, summary="Query Account on Universal Ledger")
def query_account(
    account_id: str,
    client: UniversalLedgerClient = Depends(get_ledger_client)
) -> QueryAccountResponse:
    """
    **QueryAccount**: Queries all details of an account on the Universal Ledger (sequence_number, public_key, round_id, currency_balances, account_status).
    """
    req = QueryAccountRequest(
        endpoint=client.endpoint_name,
        account_id=account_id
    )
    try:
        return client.query_account(req)
    except KeyError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))

@router.get("/transactions/{transaction_digest_hex}", response_model=QueryTransactionStateResponse, summary="Query Transaction State")
def query_transaction(
    transaction_digest_hex: str,
    client: UniversalLedgerClient = Depends(get_ledger_client)
) -> QueryTransactionStateResponse:
    """
    **QueryTransactionState**: Queries transaction inclusion state and consensus round certificates on the Universal Ledger.
    """
    req = QueryTransactionStateRequest(
        endpoint=client.endpoint_name,
        transaction_digest_hex=transaction_digest_hex
    )
    return client.query_transaction_state(req)

@router.get("/endpoints", response_model=ListEndpointsResponse, summary="List Universal Ledger Endpoints")
def list_endpoints(
    client: UniversalLedgerClient = Depends(get_ledger_client)
) -> ListEndpointsResponse:
    """
    **ListEndpoints**: Lists available regional Google Cloud Universal Ledger endpoints.
    """
    req = ListEndpointsRequest(parent=f"projects/{client.endpoint_name.split('/')[1]}/locations/{client.endpoint_name.split('/')[3]}")
    return client.list_endpoints(req)
