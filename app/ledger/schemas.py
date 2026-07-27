from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, ConfigDict

class AccountStatus(str, Enum):
    ACCOUNT_STATUS_UNSPECIFIED = "ACCOUNT_STATUS_UNSPECIFIED"
    ACCOUNT_STATUS_ACTIVE = "ACCOUNT_STATUS_ACTIVE"
    ACCOUNT_STATUS_INACTIVE = "ACCOUNT_STATUS_INACTIVE"

class Role(str, Enum):
    ROLE_UNSPECIFIED = "ROLE_UNSPECIFIED"
    ROLE_PAYER = "ROLE_PAYER"
    ROLE_RECEIVER = "ROLE_RECEIVER"
    ROLE_CONTRACT_CREATOR = "ROLE_CONTRACT_CREATOR"
    ROLE_CONTRACT_PARTICIPANT = "ROLE_CONTRACT_PARTICIPANT"

class KeyFormat(str, Enum):
    KEY_FORMAT_UNSPECIFIED = "KEY_FORMAT_UNSPECIFIED"
    KEY_FORMAT_TINK_WIRE_FORMAT = "KEY_FORMAT_TINK_WIRE_FORMAT"
    KEY_FORMAT_PEM_EC_P256_SHA256 = "KEY_FORMAT_PEM_EC_P256_SHA256"

class KeySlot(str, Enum):
    KEY_SLOT_UNSPECIFIED = "KEY_SLOT_UNSPECIFIED"
    KEY_SLOT_PRIMARY = "KEY_SLOT_PRIMARY"
    KEY_SLOT_ALTERNATE = "KEY_SLOT_ALTERNATE"

class ContractPermission(str, Enum):
    CONTRACT_PERMISSION_UNSPECIFIED = "CONTRACT_PERMISSION_UNSPECIFIED"
    CONTRACT_PERMISSION_STORAGE = "CONTRACT_PERMISSION_STORAGE"

class CurrencyValue(BaseModel):
    value: int = Field(..., description="Minor units of the currency (e.g. cents for USD)")

class QualifiedCurrencyValue(BaseModel):
    operator_id: str
    currency_code: Optional[str] = "USD"

class AmountValue(BaseModel):
    currency: QualifiedCurrencyValue
    amount_value: int

class Transfer(BaseModel):
    payer_id: str
    beneficiary_id: str
    amount: CurrencyValue

class CreateContract(BaseModel):
    contract_bytes: bytes = b""
    init_arguments: Dict[str, Any] = Field(default_factory=dict)
    contract_comment: Optional[str] = ""

class InvokeContractMethod(BaseModel):
    contract_id: str
    method_name: str
    method_arguments: Dict[str, Any] = Field(default_factory=dict)
    payment: Optional[CurrencyValue] = None

class GrantContractPermissions(BaseModel):
    contract_id: str
    permissions: List[ContractPermission] = Field(default_factory=list)
    delegate_contract_id: Optional[str] = None

class CreateAccount(BaseModel):
    public_key: bytes = b"dummy_pub_key"
    key_format: KeyFormat = KeyFormat.KEY_FORMAT_PEM_EC_P256_SHA256
    roles: List[Role] = Field(default_factory=list)
    account_status: AccountStatus = AccountStatus.ACCOUNT_STATUS_ACTIVE
    account_comment: Optional[str] = ""
    token_manager_id: Optional[str] = None

class ClientTransaction(BaseModel):
    sender_id: str
    sequence_number: int = 0
    chained_unit: bool = False
    other_signatory_ids: List[str] = Field(default_factory=list)
    
    # Kind fields (only one populated per transaction)
    transfer_transaction: Optional[Transfer] = None
    create_contract_transaction: Optional[CreateContract] = None
    invoke_contract_method_transaction: Optional[InvokeContractMethod] = None
    grant_contract_permissions_transaction: Optional[GrantContractPermissions] = None
    create_account_transaction: Optional[CreateAccount] = None

class SignedTransaction(BaseModel):
    client_transaction: ClientTransaction
    signature: str = "valid_signature_placeholder"
    signatories: List[str] = Field(default_factory=list)

class SubmitTransactionRequest(BaseModel):
    endpoint: str
    transaction: SignedTransaction

class TransactionCertificate(BaseModel):
    transaction_digest_hex: str
    round_id: int
    status: str = "COMMITTED"

class SubmitTransactionResponse(BaseModel):
    transaction_digest_hex: str
    certificate: Optional[TransactionCertificate] = None

class QueryAccountRequest(BaseModel):
    endpoint: str
    account_id: str
    round_id: Optional[int] = None

class UserDetails(BaseModel):
    roles: List[Role] = Field(default_factory=list)

class Account(BaseModel):
    account_id: str
    sequence_number: int = 0
    public_key: bytes = b""
    round_id: int = 1
    comment: str = ""
    account_status: AccountStatus = AccountStatus.ACCOUNT_STATUS_ACTIVE
    user_details: Optional[UserDetails] = None
    currency_balances: Dict[str, int] = Field(default_factory=dict, description="Currency balances in minor units")

class QueryAccountResponse(BaseModel):
    account: Account

class QueryTransactionStateRequest(BaseModel):
    endpoint: str
    transaction_digest_hex: str

class TransactionAttempt(BaseModel):
    transaction_digest_hex: str
    status: str = "FINALIZED"
    round_id: int = 1

class QueryTransactionStateResponse(BaseModel):
    transaction_attempts: List[TransactionAttempt] = Field(default_factory=list)

class Endpoint(BaseModel):
    name: str

class ListEndpointsRequest(BaseModel):
    parent: str
    page_size: Optional[int] = 50
    page_token: Optional[str] = None

class ListEndpointsResponse(BaseModel):
    endpoints: List[Endpoint] = Field(default_factory=list)
    next_page_token: Optional[str] = None
