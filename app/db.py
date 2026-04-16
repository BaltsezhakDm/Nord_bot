import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import redis
from settings import settings

redis_host = settings.REDIS_HOST
redis_port = settings.REDIS_PORT
redis_db = settings.REDIS_DB

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=False)

def get_sync_url(url: str) -> str:
    if not url:
        return ""
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")

SQLALCHEMY_SYNC_URL = get_sync_url(SQLALCHEMY_DATABASE_URL)

Base = declarative_base()

async_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True, db=redis_db)


async def get_db_session() -> AsyncSession:
    async with async_session() as session:
        return session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
