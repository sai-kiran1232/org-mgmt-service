from functools import lru_cache
from pydantic import BaseModel
import os

class Settings(BaseModel):
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MASTER_DB: str = os.getenv("MASTER_DB", "master_db")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change_me")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))

@lru_cache
def get_settings() -> Settings:
    return Settings()
