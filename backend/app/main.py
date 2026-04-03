from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.trace import TraceIDMiddleware
from app.infra.container import build_container


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.container = build_container()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="API for LiveAgent Studio multi-agent runtime",
    version=settings.VERSION,
    lifespan=lifespan,
)
app.add_middleware(TraceIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(api_router.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
