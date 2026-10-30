from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "loss_mitigation"
    db_user: str = "postgres"
    db_password: str = ""
    db_sslmode: str = "prefer"
    # Full SQLAlchemy URL; when set it wins over the DB_* parts (tests use SQLite this way).
    database_url: str | None = None

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Auto-flow: new cases move through the workflow on their own (app/engine/scheduler.py).
    auto_flow_enabled: bool = True
    auto_flow_interval_seconds: int = 30

    # Serve frontend/dist from this server; rebuild it when frontend/ changes (app/core/frontend.py).
    frontend_auto_build: bool = True
    frontend_watch: bool = True

    @property
    def sqlalchemy_url(self) -> str | URL:
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"sslmode": self.db_sslmode},
        )


settings = Settings()
