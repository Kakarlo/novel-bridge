# NovelBridge — Deployment Guide

This guide covers deploying NovelBridge to AWS using free-tier eligible services:

- **Backend (FastAPI)** → AWS Elastic Beanstalk (EC2 `t3.micro`)
- **Frontend (Vite static build)** → Amazon S3 + CloudFront (free tier eligible)

The hosted app uses the **local-first (IndexedDB) storage** backend — no user data is written
to the server. The backend is pure stateless compute (translation, style extraction, NER).

---

## Architecture overview

```
Browser (S3/CloudFront)          AWS Elastic Beanstalk
┌──────────────────────┐         ┌───────────────────────┐
│  Vite + React (idb)  │ ──/api──▶  FastAPI + Uvicorn     │
│  VITE_STORAGE=idb    │◀────────│  stateless compute     │
└──────────────────────┘         │  spaCy en_core_web_sm  │
                                 └───────────────────────┘
                                          │
                                 User's own LLM (Gemini /
                                 OpenRouter / local Ollama)
```

The frontend sends all data in request bodies; the server never writes user content to disk.
`NB_DB_PATH` still points to a temp file but is only used if someone switches to the API
storage backend (not the hosted default).

---

## Prerequisites

- AWS account (free tier eligible for 12 months)
- AWS CLI installed and configured (`aws configure`)
- Docker installed (for building the backend image)
- Node.js 24 / npm 11

---

## Part 1 — Backend on Elastic Beanstalk

### 1.1 Create the EB application

```bash
# Install the EB CLI if you haven't
pip install awsebcli

cd backend/

# Initialise a new EB application (choose Docker platform, your region)
eb init novelbridge-backend --platform docker --region us-east-1

# Create the environment (t3.micro = free tier)
eb create novelbridge-production \
  --instance-type t3.micro \
  --single          # no load balancer = cheaper for low traffic
```

### 1.2 Set environment variables

In the AWS console → Elastic Beanstalk → Your environment → Configuration →
Software → Environment properties, set:

| Key | Value | Notes |
|-----|-------|-------|
| `NB_ENGINE` | `mock` | Start with mock; switch once tested |
| `NB_CORS_ORIGINS` | `https://your-cloudfront-domain.cloudfront.net` | Set after step 2.3 |
| `NB_MAX_CONCURRENT_TRANSLATIONS` | `3` | t3.micro provides 2 vCPUs; 3 is a conservative cap for low-traffic workloads |
| `NB_DB_PATH` | `/home/app/novelbridge.db` | Ephemeral; only used by the api-storage path |
| `NB_SOURCE_TERMS` | `false` | Requires zh/ja spaCy models; leave off |
| `NB_PRONOUN_CHECK` | `false` | Off by default |

For cloud LLM providers (optional — users can supply their own keys via the picker):

| Key | Value |
|-----|-------|
| `OPENROUTER_API_KEY` | *(leave blank — users supply their own)* |
| `GEMINI_API_KEY` | *(leave blank — users supply their own)* |

> **Security:** never set a shared API key on the server for a public deployment. Every
> user brings their own key via the model picker; the key lives in their browser session
> only and is sent on the `X-LLM-Api-Key` header per request.

For Ollama (only useful if your server can reach a shared Ollama host):

| Key | Value |
|-----|-------|
| `OLLAMA_BASE_URL` | `http://your-ollama-server:11434` |
| `OLLAMA_MODEL` | `qwen3.5:4b` |

If you're running a public deployment where users supply their own Ollama URL via the
picker, you can leave `NB_ENGINE=mock` as the server default — the picker's custom URL
overrides it per request.

### 1.3 Deploy

```bash
# From the backend/ directory:
eb deploy
```

EB builds the Docker image from `Dockerfile`, pushes it, and replaces the running
container. First deploy may take several minutes because the Docker image installs
Python dependencies and downloads the spaCy model during the build.

### 1.4 Verify

```bash
eb open
# Opens http://<your-eb-domain>.elasticbeanstalk.com

# Health check
curl https://<your-eb-domain>.elasticbeanstalk.com/api/health
# → {"status":"ok","reachable":true,"engine":"mock"}
```

Note the backend URL — you'll need it for the frontend build.

---

## Part 2 — Frontend on S3 + CloudFront

### 2.1 Build the frontend

```bash
cd frontend/

# The production build already sets VITE_STORAGE_BACKEND=idb (see .env.production).
# You only need to set the API URL if your backend isn't behind /api on the same domain.
# For S3+CloudFront + separate EB backend, set it:
echo "VITE_API_BASE_URL=https://<your-eb-domain>.elasticbeanstalk.com/api" > .env.production.local

npm run build
# Output: frontend/dist/
```

> If you set `VITE_API_BASE_URL`, you also need to update `src/api/client.ts` to read it:
> ```ts
> const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
> ```
> The simpler approach is to put CloudFront in front of BOTH the S3 bucket and the EB
> backend (section 2.4), so the frontend always hits `/api` on its own domain — no CORS
> issues, no env var needed.

### 2.2 Create an S3 bucket

```bash
# Replace with a globally unique name
BUCKET=novelbridge-frontend-YOUR_ACCOUNT_ID

aws s3 mb s3://$BUCKET --region us-east-1

# Block all public access (CloudFront will serve it, not S3 directly)
aws s3api put-public-access-block \
  --bucket $BUCKET \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

### 2.3 Upload the build

```bash
aws s3 sync frontend/dist/ s3://$BUCKET --delete
```

### 2.4 Create a CloudFront distribution (recommended setup)

Using a single CloudFront domain avoids cross-origin browser requests
between the frontend and API. Keep NB_CORS_ORIGINS set to your
CloudFront domain so FastAPI can validate requests correctly.

In the AWS Console → CloudFront → Create distribution:

**Origin 1 — S3 (frontend)**
- Origin domain: `<BUCKET>.s3.us-east-1.amazonaws.com`
- Origin access: Origin Access Control (OAC) — let CloudFront create it
- Default root object: `index.html`

**Origin 2 — EB backend (API)**
- Origin domain: `<your-eb-domain>.elasticbeanstalk.com`
- Protocol: HTTP only (EB default is HTTP; add HTTPS to EB separately if needed)

**Behaviours**
- `/api/*` → Origin 2 (EB), cache policy: Caching Disabled, allowed methods: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE
- `*` (default) → Origin 1 (S3), cache policy: CachingOptimized

**Error pages** (for React client-side routing):
- 403 → `/index.html`, response code 200
- 404 → `/index.html`, response code 200

After creating the distribution, note the CloudFront domain (e.g.
`d1234abcdef.cloudfront.net`).

Update the S3 bucket policy to allow CloudFront OAC (the console will prompt you).

### 2.5 Update CORS on the backend

In EB → Configuration → Software → Environment properties:

```
NB_CORS_ORIGINS=https://d1234abcdef.cloudfront.net
```

Then redeploy: `eb deploy` (from `backend/`).

### 2.6 Verify the full stack

```
https://d1234abcdef.cloudfront.net          → frontend loads
https://d1234abcdef.cloudfront.net/api/health → {"status":"ok",...}
```

---

## Part 3 — Connecting a local Ollama to the hosted app

Users of the hosted app can translate with their own local Ollama (running on their
machine or LAN). No tunnels needed — the browser makes the request directly.

### Simple path (localhost)

1. Install Ollama: https://ollama.com/download
2. Pull a model: `ollama pull qwen3.5:4b`
3. Allow cross-origin requests (Ollama blocks them by default):
   ```bash
   # macOS / Linux
   OLLAMA_ORIGINS="https://d1234abcdef.cloudfront.net" ollama serve

   # Windows PowerShell
   $env:OLLAMA_ORIGINS="https://d1234abcdef.cloudfront.net"
   ollama serve
   ```
4. In NovelBridge → click the model picker → set **Ollama server URL** to
   `http://localhost:11434`

> **Why OLLAMA_ORIGINS is needed:** Ollama's HTTP server restricts cross-origin requests
> (CORS). The browser app at your CloudFront domain needs to be listed as an allowed
> origin. Setting `OLLAMA_ORIGINS` to your CloudFront URL (or `*` for any origin)
> enables this. Without it, the browser's CORS policy blocks the request.

### Advanced path (LAN server)

If Ollama runs on another machine on your network (e.g. a home server):

1. Start Ollama with binding on all interfaces:
   ```bash
   OLLAMA_HOST=0.0.0.0 OLLAMA_ORIGINS="https://d1234abcdef.cloudfront.net" ollama serve
   ```
2. In NovelBridge → model picker → Ollama server URL:
   `http://192.168.1.X:11434` (your server's LAN IP)

> **Security note:** exposing Ollama on `0.0.0.0` makes it reachable by anyone on your
> LAN. Do not expose port 11434 to the public internet. Use a firewall rule to restrict
> it to your LAN subnet.

---

## Cost estimate (AWS free tier, 12 months)

| Service | Free tier | Typical usage |
|---------|-----------|---------------|
| EC2 `t3.micro` | 750 hrs/month | ~$0 for 12 months |
| S3 storage | 5 GB | ~$0 for a small static build |
| CloudFront | 1 TB egress, 10M requests | ~$0 for low traffic |
| Data transfer | 1 GB out free | ~$0 |

After 12 months, a `t3.micro` typically costs several dollars per month,
depending on region and usage. A `t3a.nano` may be sufficient for a
low-traffic stateless backend if costs become a concern.

---

## Updating the deployment

**Backend** (code change):
```bash
cd backend/
eb deploy
```

**Frontend** (code change):
```bash
cd frontend/
npm run build
aws s3 sync dist/ s3://$BUCKET --delete
# Invalidate CloudFront cache so users get the new build immediately:
aws cloudfront create-invalidation --distribution-id YOUR_CF_ID --paths "/*"
```

---

## Local self-hosted alternative

If you prefer to run everything on your own machine (no AWS), see the root `README.md`.
The `api` storage backend keeps all data in SQLite locally; no cloud account needed.
