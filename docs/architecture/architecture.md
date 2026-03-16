# Architecture Overview

## System Components

### Backend (FastAPI + LangGraph + RAG)
- RESTful API for agent management
- LangGraph for agent orchestration
- RAG (Retrieval-Augmented Generation) pipeline
- PostgreSQL for persistent storage
- Redis for caching and session management

### Frontend (Vue3)
- Single Page Application (SPA)
- Real-time agent monitoring
- Agent configuration interface
- Chat/interaction interface

### Infrastructure
- Docker containerization
- Docker Compose for local development
- Nginx reverse proxy
- PostgreSQL database
- Redis cache

## Data Flow

1. Frontend sends requests to Backend API
2. Backend processes requests using agents
3. Agents use RAG for context retrieval
4. Results cached in Redis
5. Data persisted in PostgreSQL

## Deployment Architecture

```
┌─────────────┐
│   Nginx     │ (Port 80/443)
└──────┬──────┘
       │
   ┌───┴────┬──────────┐
   │        │          │
┌──▼──┐ ┌──▼──┐ ┌─────▼────┐
│ API │ │ Web │ │ Static   │
└──┬──┘ └──┬──┘ └──────────┘
   │       │
┌──▼───────▼──┐
│  Backend    │
│  (FastAPI)  │
└──┬──────┬───┘
   │      │
┌──▼──┐ ┌─▼────┐
│ DB  │ │Redis │
└─────┘ └──────┘
```
