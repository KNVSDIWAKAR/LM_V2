from collections.abc import Iterator

from sqlalchemy import JSON, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create any missing tables, and add new nullable columns to existing ones. Never inserts data."""
    from .. import models  # noqa: F401 — registers every table on Base.metadata

    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all never alters an existing table; add columns introduced since it was created.

    Only nullable columns without a server default are added, which is every column added so
    far (new MSP screens, new documents). Anything else needs a real migration.
    """
    existing = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not existing.has_table(table.name):
                continue
            present = {c["name"] for c in existing.get_columns(table.name)}
            for column in table.columns:
                if column.name in present or not column.nullable:
                    continue
                ddl = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {ddl}'))
