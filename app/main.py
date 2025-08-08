#!/usr/bin/env python3
# app/main.py
# python 3.9
import asyncio
import logging
import logging.config
import os
import sys

from app.config import settings
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import async_session
from app.routers import webhook_router
from app.utils.exchange_loader import load_execution_module
from crud.trade import verify_pending_trades_for_execution
from app.handlers.order_verification_handler import verify_closed_trades_for_execution

if sys.version_info < (3, 9):
    sys.exit("Python 3.9 or later is required")

# Logger ayarları
logging.basicConfig(level=logging.INFO)
verifier_logger = logging.getLogger("verifier")

# FastAPI app tanımı
app = FastAPI(title="SIGMOM Signal Interface", version="1.0.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(webhook_router.router)


def setup_logging():
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    SQLA_ECHO = os.getenv("SQLA_ECHO", "0") == "1"
    VERIFIER_LEVEL = os.getenv("VERIFIER_LEVEL", "INFO").upper()

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "std": {"format": "%(asctime)s %(levelname)s:%(name)s:%(message)s"}
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "std"
            }
        },
        "loggers": {
            "": {"handlers": ["console"], "level": LOG_LEVEL},
            "httpx": {"level": "WARNING"},
            "aiomysql": {"level": "WARNING"},
            "uvicorn.access": {"level": "WARNING"},
            "sqlalchemy.engine": {"level": "INFO" if SQLA_ECHO else "WARNING"},
            "verifier": {"level": VERIFIER_LEVEL}
        }
    })


setup_logging()


# Health check
@app.get("/", tags=["Health"])
async def root():
    return {"status": "alive", "version": "1.0.0"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/favicon.ico")


async def verifier_iteration(db, exchange_name: str) -> None:
    try:
        verifier_logger.info(f"→ Checking pending trades for {exchange_name}")
        execution = load_execution_module(exchange_name)
        await verify_pending_trades_for_execution(db, execution)
        # Ardından kapanışları da izle
        await verify_closed_trades_for_execution(db, execution)
    except Exception as e:
        verifier_logger.error(f"Verifier error for {exchange_name}: {e}", exc_info=True)


async def verifier_loop(poll_interval: int = 5):
    await asyncio.sleep(3)
    verifier_logger.info("Verifier loop startup’ta başlatıldı.")

    while True:
        verifier_logger.info("֍ verifier_loop iteration start")
        async with async_session() as db:
            for exchange_name in settings.active_exchanges:
                await verifier_iteration(db, exchange_name)
        await asyncio.sleep(poll_interval)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(verifier_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
