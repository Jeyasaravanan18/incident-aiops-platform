# Deployment

## AWS EC2 Target

The application is prepared for Docker Compose deployment on a single EC2 instance.

Recommended production additions:

- Nginx reverse proxy
- TLS certificates through Certbot or a managed load balancer
- restricted security groups
- managed PostgreSQL for serious production use
- Redis persistence and backups if Redis stores important state

## Local Production-Like Run

```bash
cp .env.example .env
docker compose up --build
```

## Nginx Sketch

```nginx
server {
  listen 80;
  server_name example.com;

  location /api/ {
    proxy_pass http://backend:8000;
  }

  location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
  }

  location / {
    proxy_pass http://frontend:3000;
  }
}
```

---

## Render Deployment (Backend & PostgreSQL)

The repository includes a ready-to-use Render Blueprint (`render.yaml`).

### Option 1: Render Blueprint (Recommended - 1 Click)

1. Sign up or log into [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** -> **Blueprint**.
3. Connect your GitHub repository: `https://github.com/Jeyasaravanan18/incident-aiops-platform`.
4. Render detects `render.yaml` and provisions:
   - **PostgreSQL Database** (`incident-aiops-db`)
   - **Docker Web Service** (`incident-aiops-backend`)
5. Under Environment variables, supply your `GEMINI_API_KEY`.
6. Click **Apply**.
7. Render will build the container, execute Alembic migrations, seed the initial enterprise incident scenario, and launch the service with live health checks.

### Option 2: Manual Setup on Render

If you prefer manual configuration without Blueprints:
1. **Create PostgreSQL**:
   - In Render dashboard, click **New +** -> **PostgreSQL**.
   - Name: `incident-aiops-db`, Database: `incident_aiops`, User: `incident_user`.
   - Copy the **Internal Database URL**.
2. **Create Web Service**:
   - Click **New +** -> **Web Service**.
   - Connect your GitHub repo.
   - Runtime: **Docker**.
   - Dockerfile path: `./backend/Dockerfile`.
   - Docker Context: `./backend`.
   - Health Check Path: `/health`.
3. **Set Environment Variables**:
   - `DATABASE_URL`: paste the Internal Database URL (the backend automatically resolves `postgres://` into `postgresql+asyncpg://` and `postgresql://`).
   - `ENVIRONMENT`: `production`
   - `CORS_ORIGINS`: `*` (or your frontend URL)
   - `AUTO_SEED`: `true`
   - `LLM_PROVIDER`: `gemini`
   - `GEMINI_API_KEY`: `<your_gemini_api_key>`
   - `GEMINI_MODEL`: `gemini-2.5-flash`
   - `JWT_SECRET`: `<generate_random_32_char_secret>`

