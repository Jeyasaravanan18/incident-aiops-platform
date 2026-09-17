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

## Render Deployment (Backend with MongoDB Atlas)

The repository includes a ready-to-use Render Blueprint (`render.yaml`).

### Option 1: Render Blueprint (Recommended - 1 Click)

1. Ensure **Network Access** in your [MongoDB Atlas Dashboard](https://cloud.mongodb.com/) allows access from anywhere (`0.0.0.0/0`), which is required for cloud hosting on Render.
2. Sign up or log into [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** -> **Blueprint**.
4. Connect your GitHub repository: `https://github.com/Jeyasaravanan18/incident-aiops-platform`.
5. Render detects `render.yaml` and sets up:
   - **Docker Web Service** (`incident-aiops-backend`)
6. When prompted for environment variables:
   - `MONGODB_URL`: Paste your MongoDB Atlas connection string (`mongodb+srv://...`)
   - `GEMINI_API_KEY`: Supply your Gemini API key
7. Click **Apply**.
8. Render will build the container, automatically seed the initial enterprise incident scenario into MongoDB Atlas, and launch the service with live health checks.

### Option 2: Manual Setup on Render

1. **Create Web Service**:
   - In Render, click **New +** -> **Web Service**.
   - Connect your GitHub repo.
   - Runtime: **Docker**.
   - Dockerfile path: `./backend/Dockerfile`.
   - Docker Context: `./backend`.
   - Health Check Path: `/health`.
2. **Set Environment Variables**:
   - `MONGODB_URL`: `mongodb+srv://...`
   - `MONGODB_DB_NAME`: `incident_aiops`
   - `ENVIRONMENT`: `production`
   - `CORS_ORIGINS`: `*` (or your frontend URL)
   - `AUTO_SEED`: `true`
   - `LLM_PROVIDER`: `gemini`
   - `GEMINI_API_KEY`: `<your_gemini_api_key>`
   - `GEMINI_MODEL`: `gemini-2.5-flash`
   - `JWT_SECRET`: `<generate_random_32_char_secret>`


