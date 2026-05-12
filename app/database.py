from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings

engine = create_engine(
    settings.mysql_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={"connect_timeout": settings.SQL_TIMEOUT_SECONDS},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def execute_select(sql: str, params: dict | None = None) -> list[dict]:
    """Execute a read-only SELECT query and return results as a list of dicts."""
    with SessionLocal() as db:
        db.execute(text("SET SESSION max_execution_time = :timeout"),
                   {"timeout": settings.SQL_TIMEOUT_SECONDS * 1000})
        result = db.execute(text(sql), params or {})
        rows = result.fetchall()
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in rows]
