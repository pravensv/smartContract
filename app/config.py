# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "Google Cloud Universal Ledger Escrow API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # GCP Universal Ledger settings
    GCP_PROJECT: str = "ltc-hack2026-team23"
    GCP_LOCATION: str = "us-central1"
    UL_ENDPOINT_NAME: str = "projects/ltc-hack2026-team23/locations/us-central1/endpoints/ul-endpoint-main"
    
    # Base URL for Google Cloud Universal Ledger API
    GCUL_BASE_URL: str = "https://universalledger.googleapis.com/v1"
    
    # Universal Ledger Manager IDs
    TOKEN_MANAGER_ID: str = "1:TKN:GBP:42445hd66brJdaXfLkULnKdZYXVvzZjjpHqbqoCsHKoca"
    ACCOUNT_MANAGER_ID: str = "1:ACT:GBP:424DvgEQUgcw91swqbKTiYWu1Ek9z5vkWE3FBB7DgHZ50"
    
    # Default currency
    DEFAULT_CURRENCY: str = "GBP"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
