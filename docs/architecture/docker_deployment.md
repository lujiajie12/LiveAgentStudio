# Docker Deployment Guide

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 10GB disk space

## Quick Start

1. Clone the repository
2. Copy environment file:
   ```bash
   cp deploy/.env.example deploy/.env
   ```

3. Update `.env` with your configuration:
   - Set `OPENAI_API_KEY`
   - Configure database credentials
   - Set CORS origins

4. Start services:
   ```bash
   cd deploy
   docker-compose up -d
   ```

5. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Service Health Checks

```bash
# Check all services
docker-compose ps

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop services
docker-compose down
```

## Database Initialization

The database is automatically initialized on first run using `scripts/init_db.sql`.

To manually initialize:
```bash
docker-compose exec postgres psql -U user -d liveagent -f /docker-entrypoint-initdb.d/init.sql
```

## Troubleshooting

### Port already in use
Change ports in `docker-compose.yml` or stop conflicting services.

### Database connection failed
Ensure PostgreSQL is healthy: `docker-compose ps postgres`

### Frontend not loading
Check nginx logs: `docker-compose logs nginx`
