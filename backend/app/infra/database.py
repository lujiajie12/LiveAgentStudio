from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base


def _sqlite_url() -> str:
    db_path = Path(__file__).resolve().parents[2] / "liveagent.db"
    return f"sqlite:///{db_path.as_posix()}"


def normalize_database_url(url: str | None) -> str:
    if not url:
        return _sqlite_url()
    return url


def build_engine(url: str | None = None) -> Engine:
    normalized = normalize_database_url(url)
    connect_args = {}
    if normalized.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(
        normalized,
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def ping_database(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
