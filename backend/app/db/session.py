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
        await _ensure_columns(conn)


async def _ensure_columns(conn) -> None:
    """Thêm cột mới cho bảng cũ mà không xoá dữ liệu (SQLite không tự ALTER khi create_all)."""
    wanted = {
        "audit_batches": [("reference_label", "VARCHAR(255)")],
    }
    for table, cols in wanted.items():
        for col, ddl in cols:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            except Exception:
                # Cột đã tồn tại là trường hợp bình thường.
                pass

async def get_db():
    async with SessionLocal() as session:
        yield session

async def ping_db() -> str:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return "ok"
