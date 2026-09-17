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
