import logging
from typing import Dict, Any, Optional
from app.config import settings

# Initialize GCP Cloud Logging client if available
gcp_logger = None

try:
    import google.auth
    import google.cloud.logging
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
        quota_project_id=settings.GCP_PROJECT
    )
    if hasattr(credentials, "with_quota_project"):
        credentials = credentials.with_quota_project(settings.GCP_PROJECT)
    client = google.cloud.logging.Client(project=settings.GCP_PROJECT, credentials=credentials)
    gcp_logger = client.logger("escrow-service-logs")
    print(f"🌲 [GCP Cloud Logging] Active for project '{settings.GCP_PROJECT}' -> logName 'escrow-service-logs'")
except Exception as e:
    print(f"⚠️ [GCP Cloud Logging] Local logger fallback: {e}")

def log_escrow_event(action: str, title: str, escrow_id: str, status: str, details: Optional[Dict[str, Any]] = None):
    """
    Emits structured JSON payload log directly to GCP Cloud Logging.
    Allows searching by title in Google Cloud Console:
        jsonPayload.title="MacBook Pro M3 Purchase"
        "MacBook Pro M3 Purchase"
    """
    payload = {
        "event": action,
        "title": title,
        "escrow_id": escrow_id,
        "status": status,
        "gcp_project": settings.GCP_PROJECT,
        "endpoint": settings.UL_ENDPOINT_NAME,
        "details": details or {}
    }
    
    # Print terminal output banner
    print(f"\n================================================================================")
    print(f"📢 [GCP CLOUD LOG] {action} -> Title: '{title}' (Status: {status})")
    print(f"   Escrow ID : {escrow_id}")
    print(f"   GCP Project: {settings.GCP_PROJECT}")
    print(f"================================================================================\n")

    # Write to GCP Cloud Logging
    global gcp_logger
    if gcp_logger:
        try:
            gcp_logger.log_struct(payload, severity="INFO")
        except Exception as err:
            if "logging.logEntries.create" in str(err) or "Permission" in str(err):
                print("⚠️ [GCP Cloud Logging] Insufficient IAM permissions ('roles/logging.logWriter' missing). Falling back to console logging.")
                gcp_logger = None  # Disable to avoid repeating error tracebacks
            else:
                print(f"Failed to push log to GCP: {err}")
