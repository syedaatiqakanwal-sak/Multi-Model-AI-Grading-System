import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# In transaction pool mode with PgBouncer, prepared statements must be 0
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=3,
    max_overflow=2,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={
        "prepared_statement_cache_size": 0,
        "server_settings": {"application_name": "orchestrator"},
    },
    echo=False,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
