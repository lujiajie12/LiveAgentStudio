# Docker Deployment Guide

## Scope

This file only describes the Docker Compose deployment layer under `deploy/`.

Environment split:
- `deploy/.env`: container ports, database account, Milvus image and other infra-only variables
- `backend/.env`: backend runtime variables such as LLM, SerpAPI, memory, embedding and retrieval settings

The backend container now loads `backend/.env` through `env_file`, so do not duplicate backend runtime secrets inside `deploy/.env`.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4 GB RAM minimum
- 10 GB disk space

## Quick Start

1. Copy environment templates:

   ```bash
   cp deploy/.env.example deploy/.env
   cp backend/.env.example backend/.env
   ```

2. Update `backend/.env`:
   - `LLM_API_KEY`
   - `LLM_BASE_URL`
   - `LLM_MODEL`
   - `SERPAPI_API_KEY`
   - `EMBEDDING_MODEL`

3. Update `deploy/.env`:
   - `DB_USER`
   - `DB_PASSWORD`
   - `DB_NAME`
   - build base images when Docker Hub is not reachable
   - service ports if needed

4. Start the full stack:

   ```bash
   cd deploy
   docker compose up -d --build
   ```

5. Access:
   - Frontend: `http://localhost:5173`
   - Backend API: `http://localhost:8000`
   - API Docs: `http://localhost:8000/docs`

## Build Image Overrides

If your machine cannot pull directly from Docker Hub, override the build base images in `deploy/.env`:

```env
BACKEND_BASE_IMAGE=python:3.11-slim
FRONTEND_NODE_BASE_IMAGE=node:18-alpine
FRONTEND_NGINX_BASE_IMAGE=nginx:alpine
```

Replace the values above with your internal registry or accessible mirror image addresses.

## Service Health Checks

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down
```

## Database Initialization

The database is initialized automatically on first run using `deploy/scripts/init_db/init.sql`.

Manual execution example:

```bash
docker compose exec postgres psql -U "$DB_USER" -d "$DB_NAME" -f /docker-entrypoint-initdb.d/init.sql
```

## Troubleshooting

### Port already in use

Change the exported ports in `deploy/.env`, then restart Compose.

### Database connection failed

Check:

```bash
docker compose ps postgres
docker compose logs --tail=200 postgres
```

### Frontend not loading

Check:

```bash
docker compose logs --tail=200 frontend
```

### Docker Hub token fetch failed during build

Typical error:

```text
failed to fetch anonymous token
Get "https://auth.docker.io/token..."
```

This means the Docker daemon cannot reach Docker Hub, not that the frontend or backend Dockerfile is invalid.

Recommended actions:
1. Configure Docker Desktop proxy or registry mirror
2. Override `BACKEND_BASE_IMAGE`, `FRONTEND_NODE_BASE_IMAGE`, `FRONTEND_NGINX_BASE_IMAGE` in `deploy/.env`
3. Rebuild:

```bash
cd deploy
docker compose build --no-cache backend frontend
docker compose up -d
```

### Milvus `channel not found` during indexing

Use only `deploy/docker-compose.yml`. The legacy standalone Milvus compose file has already been removed to avoid mixed-version deployments.

Recommended recovery order:
1. Restart the Milvus dependency chain: `docker compose restart etcd minio milvus`
2. Retry indexing after the services are healthy
3. If metadata is still corrupted, rebuild the Milvus service chain

Example reset flow:

```bash
cd deploy
docker compose down
docker compose up -d etcd minio milvus
```

If a full rebuild is required, remove only the Milvus-related volume from the active Compose project and then re-run indexing.
