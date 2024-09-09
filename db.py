import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

user_db = os.getenv('user_db')
password_db = os.getenv('password_db')
database = os.getenv('database')
host_db = os.getenv('host_db')



SQLALCHEMY_DATABASE_URL = f'postgresql+asyncpg://{user_db}:{password_db}@{host_db}/{database}'
engine = create_async_engine(SQLALCHEMY_DATABASE_URL, echo=True)

SQLALCHEMY_SYNC_URL = f'postgresql://{user_db}:{password_db}@{host_db}/{database}'

Base = declarative_base()

async_session = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db_session() -> AsyncSession:
    async with async_session() as session:
        return session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
