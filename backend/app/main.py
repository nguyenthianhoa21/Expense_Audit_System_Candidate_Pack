"""FastAPI app: AI Expense Audit System."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.audit import router as audit_router
from app.core.config import get_settings
from app.db.session import init_db, ping_db

settings = get_settings()

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

app = FastAPI(
    title="AI Expense Audit System",
    description="Upload bo chung tu PO / Invoice / Payment Request -> trich xuat AI -> audit R0-R12.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audit_router)


@app.on_event("startup")
async def _startup() -> None:
    await init_db()


@app.get("/")
async def root() -> dict:
    return {"ok": True, "app": "AI Expense Audit System", "docs": "/docs"}


@app.get("/health")
async def health() -> dict:
    try:
        await ping_db()
        db = "ok"
    except Exception as exc:  # noqa: BLE001
        db = f"error: {exc}"
    return {"status": "ok" if db == "ok" else "degraded", "db": db}
