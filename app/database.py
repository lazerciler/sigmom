#!/usr/bin/env python3
# app/database.py
# Python 3.9
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

# Veritabanı bağlantı URL'si
DATABASE_URL = settings.DB_URL

# Async engine oluştur
engine = create_async_engine(DATABASE_URL, echo=False, future=True)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)

# Alias for compatibility with main.py
async_session = AsyncSessionLocal

# Base sınıf
Base = declarative_base()


# FastAPI içinde varsayılan session dependency
async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# Geriye dönük uyum için alias
get_db = get_session


# Testlerde override edilmek üzere ayrı tanım
async def override_get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
