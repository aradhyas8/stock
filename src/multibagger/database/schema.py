"""Database schema management and connection utilities"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

# Default database location - repo relative
DEFAULT_DB_PATH = Path("data/multibagger.db")


def get_db_path(db_path: str | None = None) -> Path:
    """Get the database file path, creating directory if needed"""
    if db_path:
        path = Path(db_path)
    else:
        path = DEFAULT_DB_PATH

    # Create directory if it doesn't exist
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_engine(db_path: str | None = None, echo: bool = False) -> Engine:
    """Create SQLite engine with optimized settings"""
    path = get_db_path(db_path)

    # SQLite connection string
    engine = create_engine(
        f"sqlite:///{path}",
        echo=echo,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )

    # Enable SQLite optimizations
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # Enable WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL")
        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys=ON")
        # Optimize for fast reads (we're read-heavy)
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=10000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

    return engine


def get_session(engine: Engine) -> Session:
    """Create database session"""
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def create_all_tables(engine: Engine) -> None:
    """Create all database tables"""
    Base.metadata.create_all(bind=engine)


def drop_all_tables(engine: Engine) -> None:
    """Drop all database tables (dev only)"""
    Base.metadata.drop_all(bind=engine)
