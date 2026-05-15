from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "ai-business-rag"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8105
    APP_DEBUG: bool = True

    # MySQL
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "readonly_user"
    MYSQL_PASSWORD: str = "readonly_password"
    MYSQL_DATABASE: str = "your_business_db"
    MYSQL_CHARSET: str = "utf8mb4"

    # LLM
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-chat"
    LLM_TIMEOUT: int = 60

    # Security
    MAX_QUERY_ROWS: int = 200
    SQL_TIMEOUT_SECONDS: int = 10
    SHOW_SQL_DEFAULT: bool = True

    # CORS
    CORS_ORIGINS: str = "*"

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset={self.MYSQL_CHARSET}"
        )

    _env_file = Path(__file__).resolve().parent.parent / ".env"
    model_config = {"env_file": str(_env_file), "env_file_encoding": "utf-8"}


settings = Settings()
