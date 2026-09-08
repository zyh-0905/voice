"""SQLAlchemy database configuration (opt-in; API defaults to in-memory repository)."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://voicelens:voicelens@localhost:5432/voicelens")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
try:
    engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
except ModuleNotFoundError as exc:
    # Keep lightweight local test environments usable when the optional
    # PostgreSQL driver is not installed; deployed images install it.
    if DATABASE_URL.startswith("postgresql") and exc.name in {"psycopg2", "psycopg"}:
        DATABASE_URL = "sqlite:///./voicelens.db"
        connect_args = {"check_same_thread": False}
        engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
    else:
        raise
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
