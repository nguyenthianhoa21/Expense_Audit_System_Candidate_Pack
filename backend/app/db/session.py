from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import text
from app.core.config import get_settings
from app.db.models import Base

settings = get_settings()

def create_engine() -> AsyncEngine:
    kwargs: dict = {"echo": False}
    if settings.DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_async_engine(settings.DATABASE_URL, **kwargs)

engine = create_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with SessionLocal() as session:
        yield session

async def ping_db() -> str:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return "ok"
