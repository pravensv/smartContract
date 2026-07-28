# ☁️ Google Cloud Universal Ledger (GCUL) Deployment Guide

This guide provides step-by-step instructions to deploy the **Escrow Smart Contract & FastAPI Service** onto **Google Cloud Platform (GCP)** and connect to **Google Cloud Universal Ledger (`google.cloud.universalledger.v1`)**.

---

## 🏛️ Deployment Architecture Overview

```
 ┌────────────────────────────────────────────────────────┐
 │                   Google Cloud Platform                │
 │                                                        │
 │   ┌────────────────────────────────────────────────┐   │
 │   │   GCP Cloud Run (Serverless API Service)       │   │
 │   │   FastAPI Web App (Container Image)            │   │
 │   └───────────────────────┬────────────────────────┘   │
 │                           │ Authenticated ADC / OAuth2 │
 │                           ▼                            │
 │   ┌────────────────────────────────────────────────┐   │
 │   │   GCP Universal Ledger Network                 │   │
 │   │   Endpoint: projects/.../endpoints/ul-endpoint │   │
 │   │   Smart Contract: UniversalEscrowRules.sol     │   │
 │   └────────────────────────────────────────────────┘   │
 └────────────────────────────────────────────────────────┘
```

---

## 📋 Prerequisites

Before deploying, ensure you have installed:
1. **Google Cloud SDK (`gcloud` CLI)**: [Install Guide](https://cloud.google.com/sdk/docs/install)
2. **Docker Desktop**: [Install Guide](https://www.docker.com/products/docker-desktop/)
3. Active **Google Cloud Account & Project** (`ltc-hack2026-team23`).

---

## 🚀 Step 1: Initialize Google Cloud Project & APIs

Run the following commands in your shell:

```bash
# 1. Login to Google Cloud
gcloud auth login

# 2. Set your active Google Cloud Project
gcloud config set project ltc-hack2026-team23

# 3. Enable required GCP APIs
gcloud services enable \
  universalledger.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  logging.googleapis.com
```

---

## 🔐 Step 2: Configure Service Account & IAM Permissions

Create a dedicated GCP Service Account for the API service:

```bash
# 1. Create Service Account
gcloud iam service-accounts create gcul-escrow-sa \
    --description="Service account for Universal Ledger Escrow API" \
    --display-name="GCUL Escrow SA"

# 2. Grant Universal Ledger Client & Cloud Logging Roles
gcloud projects add-iam-policy-binding ltc-hack2026-team23 \
    --member="serviceAccount:gcul-escrow-sa@ltc-hack2026-team23.iam.gserviceaccount.com" \
    --role="roles/universalledger.admin"

gcloud projects add-iam-policy-binding ltc-hack2026-team23 \
    --member="serviceAccount:gcul-escrow-sa@ltc-hack2026-team23.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter"
```

---

## 📦 Step 3: Containerize Application & Push to GCP Artifact Registry

Build and submit the container image using **Google Cloud Build**:

```bash
# 1. Create Docker Repository in Artifact Registry (us-central1)
gcloud artifacts repositories create escrow-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Docker repository for Escrow API"

# 2. Build and submit image to GCP Artifact Registry
gcloud builds submit --tag us-central1-docker.pkg.dev/ltc-hack2026-team23/escrow-repo/escrow-api:v1 .
```

---

## 🌐 Step 4: Deploy API Service to GCP Cloud Run

Deploy the container image to **GCP Cloud Run**:

```bash
gcloud run deploy escrow-api-service \
    --image us-central1-docker.pkg.dev/ltc-hack2026-team23/escrow-repo/escrow-api:v1 \
    --platform managed \
    --region us-central1 \
    --service-account gcul-escrow-sa@ltc-hack2026-team23.iam.gserviceaccount.com \
    --set-env-vars GCP_PROJECT="ltc-hack2026-team23",GCP_LOCATION="us-central1",UL_ENDPOINT_NAME="projects/ltc-hack2026-team23/locations/us-central1/endpoints/ul-endpoint-main" \
    --allow-unauthenticated \
    --port 8000
```

Upon successful deployment, Cloud Run will output your live URL, e.g.:
`https://escrow-api-service-xxxxxx-uc.a.run.app`

---

## 📜 Step 5: Deploy Smart Contract to GCUL Endpoint

To register `UniversalEscrowRules.sol` on Google Cloud Universal Ledger:

```bash
# Register contract transaction on Universal Ledger endpoint
curl -X POST "https://universalledger.googleapis.com/v1/projects/ltc-hack2026-team23/locations/us-central1/endpoints/ul-endpoint-main:submitTransaction" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  -d '{
    "endpoint": "projects/ltc-hack2026-team23/locations/us-central1/endpoints/ul-endpoint-main",
    "signedTransaction": {
      "clientTransaction": {
        "senderId": "acc_admin_001",
        "createContractTransaction": {
          "contractBytecode": "<COMPILED_BYTECODE_HEX>",
          "contractName": "UniversalEscrowRules"
        }
      }
    }
  }'
```

---

## 🔍 Step 6: Verify Live Deployment & GCP Cloud Logging

1. Open your live Cloud Run URL interactive API docs:
   **`https://<YOUR-CLOUD-RUN-URL>/docs`**

2. View live Cloud Logging entries for GCUL transactions:
   ```bash
   gcloud logging read "resource.type=cloud_run_revision AND jsonPayload.app='escrow_service'" --limit 20
   ```

---

## ⚙️ Summary of Environment Variables (`.env`)

| Variable | Description | Example Value |
| :--- | :--- | :--- |
| `GCP_PROJECT` | Google Cloud Project ID | `ltc-hack2026-team23` |
| `GCP_LOCATION` | Region location | `us-central1` |
| `UL_ENDPOINT_NAME` | GCUL Network Endpoint Name | `projects/ltc-hack2026-team23/locations/us-central1/endpoints/ul-endpoint-main` |
| `GCUL_BASE_URL` | Universal Ledger REST Base URL | `https://universalledger.googleapis.com/v1` |
| `TOKEN_MANAGER_ID` | Token Manager Account ID | `1:TKN:GBP:42445hd66brJdaXfLkULnKdZYXVvzZjjpHqbqoCsHKoca` |
