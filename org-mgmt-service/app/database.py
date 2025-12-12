from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from .config import get_settings

_settings = get_settings()
_client: AsyncIOMotorClient | None = None

async def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(_settings.MONGO_URI)
    return _client

async def get_master_db() -> AsyncIOMotorDatabase:
    client = await get_client()
    return client[_settings.MASTER_DB]
