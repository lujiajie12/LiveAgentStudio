# LiveAgentStudio

A comprehensive platform for building, deploying, and managing intelligent agents with RAG (Retrieval-Augmented Generation) capabilities.
![Uploading ChatGPT Image 2026年4月26日 16_06_11.png…]()


## Features

- **Agent Management** - Create, configure, and manage AI agents
- **RAG Pipeline** - Retrieve and augment generation with custom documents
- **Chat Interface** - Real-time interaction with agents
- **Memory Management** - Persistent conversation history
- **Multi-Agent Support** - Orchestrate multiple agents with LangGraph

## Tech Stack

### Backend
- FastAPI - Modern Python web framework
- LangGraph - Agent orchestration
- LangChain - LLM integration
- PostgreSQL - Data persistence
- Redis - Caching and sessions

### Frontend
- Vue 3 - Progressive JavaScript framework
- Vite - Next generation build tool
- Axios - HTTP client

### Infrastructure
- Docker - Containerization
- Docker Compose - Multi-container orchestration
- Nginx - Reverse proxy

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### Local Development

1. **Clone and setup**
   ```bash
   git clone <repository>
   cd liveagent-studio
   ```

2. **Backend setup**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Frontend setup**
   ```bash
   cd frontend
   npm install
   ```

4. **Docker deployment**
   ```bash
   cd deploy
   cp .env.example .env
   # Edit .env with your configuration
   docker-compose up -d
   ```

## Documentation

- [Architecture](docs/architecture/architecture.md)
- [API Contract](docs/architecture/api_contract.md)
- [Database Schema](docs/architecture/database_schema.md)
- [Docker Deployment](docs/architecture/docker_deployment.md)
- [Git Workflow](docs/architecture/git_workflow.md)

## Project Structure

```
liveagent-studio/
├── backend/              # FastAPI + LangGraph + RAG
├── frontend/             # Vue3 application
├── deploy/               # Docker and deployment config
├── docs/                 # Documentation
├── scripts/              # Database and utility scripts
└── README.md
```

## Development

### Running Backend
```bash
cd backend
uvicorn app.main:app --reload
```

### Running Frontend
```bash
cd frontend
npm run dev
```

### Running Tests
```bash
cd backend
pytest
```

## API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Commit changes: `git commit -am 'Add feature'`
3. Push to branch: `git push origin feature/your-feature`
4. Submit a pull request

See [Git Workflow](docs/architecture/git_workflow.md) for detailed guidelines.

## License

See LICENSE file for details.

## Support

For issues and questions, please open an issue on the repository.
