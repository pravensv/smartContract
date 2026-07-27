from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.ledger.client import UniversalLedgerClient
from app.services.escrow_service import EscrowService
from app.routers.escrow_router import router as escrow_router, set_escrow_service
from app.routers.ledger_router import router as ledger_router, set_ledger_client

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "### Google Cloud Universal Ledger Escrow REST API\n"
            "Provides an enterprise API to manage full Escrow lifecycles (**Create**, **Buy**, **Hold**, **Sell**) "
            "backed by Google Cloud Universal Ledger (`google.cloud.universalledger.v1`).\n\n"
            "**Key Capabilities**:\n"
            "- **Create Escrow**: Deploys an Escrow Vault Account/Contract state on Universal Ledger.\n"
            "- **Buy (Fund)**: Buyer transfers currency tokens into Escrow Vault (`Transfer`).\n"
            "- **Hold**: Locks escrow during inspection/dispute via ledger contract state update.\n"
            "- **Sell (Release)**: Releases locked funds from Vault -> Seller (`Transfer`).\n"
            "- **Ledger Audit**: Directly inspect account balances, round certificates, and transaction digests."
        ),
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Enable CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize Universal Ledger client & Escrow service singletons
    ledger_client = UniversalLedgerClient()
    escrow_service = EscrowService(ledger_client)

    set_ledger_client(ledger_client)
    set_escrow_service(escrow_service)

    # Include routers
    app.include_router(escrow_router)
    app.include_router(ledger_router)

    @app.get("/", tags=["Health"])
    def root():
        return {
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "healthy",
            "gcp_project": settings.GCP_PROJECT,
            "endpoint": settings.UL_ENDPOINT_NAME,
            "docs": "/docs"
        }

    return app

app = create_app()
