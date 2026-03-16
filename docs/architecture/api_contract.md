# API Contract

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication
Currently no authentication. Will be implemented with JWT tokens.

## Common Response Format

### Success Response
```json
{
  "status": "success",
  "data": {},
  "message": "Operation completed"
}
```

### Error Response
```json
{
  "status": "error",
  "error": "error_code",
  "message": "Human readable error message"
}
```

## Endpoints

### Health Check
- **GET** `/health`
- Returns: `{"status": "ok"}`

### Agents (To be implemented)
- **GET** `/agents` - List all agents
- **POST** `/agents` - Create new agent
- **GET** `/agents/{id}` - Get agent details
- **PUT** `/agents/{id}` - Update agent
- **DELETE** `/agents/{id}` - Delete agent

### Chat (To be implemented)
- **POST** `/chat` - Send message to agent
- **GET** `/chat/{session_id}` - Get chat history

## Rate Limiting
To be implemented: 100 requests per minute per IP

## Versioning
API versioning via URL path: `/api/v1`, `/api/v2`, etc.
