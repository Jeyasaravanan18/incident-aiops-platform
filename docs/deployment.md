# Production Deployment Guide

This guide covers deploying the **Incident AIOps & SRE Reliability Platform** across the modern decoupled cloud stack:

- **Frontend**: [Vercel](https://vercel.com/) (Next.js 16 App Router on Global Edge CDN)
- **Backend API**: [Render](https://render.com/) (FastAPI Docker Container)
- **Database**: [Render PostgreSQL 16](https://render.com/) (Managed PostgreSQL with pgvector support)
- **Cache & Event Bus**: Redis 7 (or Upstash / built-in in-memory fallback)
- **AI / LLM Engine**: [Google Gemini 2.5 Flash](https://ai.google.dev/)

---

## 1. Backend & Database Deployment (Render)

### Step 1: Automated Blueprint Deployment (Recommended)

1. Push your latest code to GitHub (`main` branch).
2. Go to the [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** > **Blueprint**.
4. Select your repository: `incident-aiops-platform`.
5. Render reads `render.yaml` and provisions:
   - **PostgreSQL Database** (`incident-aiops-db`)
   - **Docker Web Service** (`incident-aiops-backend`)
6. In the environment setup screen, set:
   - `GEMINI_API_KEY`: Your Google AI Gemini API Key (optional).
7. Click **Apply**.
8. Once the build finishes, copy your public backend URL (e.g., `https://incident-aiops-backend.onrender.com`).

---

### Step 2: Manual Web Service Setup (Alternative)

If setting up services individually on Render:

1. **Create PostgreSQL**:
   - In Render, click **New +** > **PostgreSQL**.
   - Name: `incident-aiops-db`
   - Database: `incident_aiops`
   - Copy the **Internal Database URL**.
2. **Create Web Service**:
   - Click **New +** > **Web Service**.
   - Connect your GitHub repository.
   - Runtime: **Docker**.
   - Dockerfile path: `./backend/Dockerfile`.
   - Docker Context: `./backend`.
   - Health Check Path: `/health`.
3. **Set Environment Variables**:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `ENVIRONMENT` | `production` | Enables production mode |
| `LOG_LEVEL` | `INFO` | Output log level |
| `DATABASE_URL` | *Your Render Internal DB URL* | Connection string for PostgreSQL |
| `SYNC_DATABASE_URL` | *Your Render Internal DB URL* | Used by Alembic synchronous migrations |
| `AUTO_SEED` | `true` | Automatically seeds demo scenarios on boot |
| `JWT_SECRET` | *32+ random characters* | Cryptographic signing secret |
| `LLM_PROVIDER` | `gemini` | AI root-cause mitigation provider |
| `GEMINI_API_KEY` | `AIzaSy...` | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model |
| `CORS_ORIGINS` | `https://incident-aiops-frontend.vercel.app,http://localhost:3000` | Permitted frontend origins |

---

## 2. Frontend Deployment (Vercel)

1. Log into [Vercel](https://vercel.com/) and click **Add New...** > **Project**.
2. Import the GitHub repository.
3. Configure project settings:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: Click **Edit** and choose `frontend` *(⚠️ Crucial: Do not leave as `./`)*.
4. Add the single required Environment Variable:
   - **Key**: `NEXT_PUBLIC_API_BASE_URL`
   - **Value**: `https://incident-aiops-backend.onrender.com` *(no trailing slash)*.
   - Check all environments (`Production`, `Preview`, `Development`).
5. Click **Deploy**.
6. Once deployed, note your live Vercel URL (e.g., `https://incident-aiops-frontend.vercel.app`).

---

## 3. Database Initialization & Seeding Verification

Your Docker container runs `backend/scripts/start.sh` automatically on every deploy:
```bash
alembic upgrade head
python -m app.scripts.seed
```

If you ever need to manually migrate or re-seed the remote database from your local machine, use Render's **External Database URL**:

```powershell
# In PowerShell:
$env:DATABASE_URL="<EXTERNAL_DATABASE_URL_FROM_RENDER>"
$env:SYNC_DATABASE_URL="<EXTERNAL_DATABASE_URL_FROM_RENDER>"

cd backend
alembic upgrade head
python -m app.scripts.seed
```

---

## 4. Post-Deployment Verification

1. **Verify Backend Health**:
   ```bash
   curl https://incident-aiops-backend.onrender.com/health
   # Expected: {"status":"ok"}
   
   curl https://incident-aiops-backend.onrender.com/ready
   # Expected: {"status":"ready","database":"connected","redis":"connected"}
   ```
2. **Access Web Console**:
   Open `https://incident-aiops-frontend.vercel.app` in your browser.
3. **Log in with Seeded Credentials**:
   - Email: `admin@example.com`
   - Password: `ChangeMe123!`
4. **Test Real-Time Incident Streaming**:
   Open two browser windows side-by-side to verify live WebSocket broadcasts (`wss://`) as incidents transition status.
