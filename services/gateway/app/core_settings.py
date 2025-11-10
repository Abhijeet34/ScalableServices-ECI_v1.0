from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "eci"
    POSTGRES_USER: str = "eci"
    POSTGRES_PASSWORD: str = "eci"
    JWT_SECRET: str = "change-me"
    JWT_ALG: str = "HS256"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
