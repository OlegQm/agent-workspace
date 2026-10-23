"""Configure the asynchronous database engine and session factory."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from infrastructure.settings import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
