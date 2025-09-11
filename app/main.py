#!/usr/bin/env python3
# app/main.py
# Python 3.9
import asyncio
import logging
import logging.config
import os
import sys
import time

from app.config import settings
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware

from app.database import async_session
from app.routers import webhook_router
from app.utils.exchange_loader import load_execution_module
from crud.trade import verify_pending_trades_for_execution
from app.handlers.order_verification_handler import verify_closed_trades_for_execution
from app.routers import panel
from app.routers import panel_data
from app.routers import referral
from app.routers import auth_google
from app.routers import admin_settings
from app.routers import admin_referrals
from app.routers import admin_test
from app.routers import market
from app.routers import account
from app.services.referral_maintenance import cleanup_expired_reserved


if sys.version_info < (3, 9):
    sys.exit(f"Bu uygulama Python 3.9+ gerektirir. Bulundu: {sys.version.split()[0]}")

# Logger ayarları
logging.basicConfig(level=logging.INFO)
verifier_logger = logging.getLogger("verifier")

# FastAPI app tanımı
app = FastAPI(title="SIGMOM Signal Interface", version="1.0.0")

# Session middleware
app.add_middleware(
    SessionMiddleware, secret_key=settings.SESSION_SECRET, same_site="lax"
)

# Statik ve router mount
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(webhook_router.router)
app.include_router(panel.router)
app.include_router(panel_data.router)
app.include_router(auth_google.router)
app.include_router(referral.router)
app.include_router(admin_settings.router)
app.include_router(admin_referrals.router)
app.include_router(admin_test.router)
app.include_router(market.router)
app.include_router(account.page_router)
app.include_router(account.router)


def setup_logging():
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    SQLA_ECHO = os.getenv("SQLA_ECHO", "0") == "1"
    VERIFIER_LEVEL = os.getenv("VERIFIER_LEVEL", "INFO").upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "std": {"format": "%(asctime)s %(levelname)s:%(name)s:%(message)s"}
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "std"}
            },
            "loggers": {
                "": {"handlers": ["console"], "level": LOG_LEVEL},
                "httpx": {"level": "WARNING"},
                "aiomysql": {"level": "WARNING"},
                "uvicorn.access": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "INFO" if SQLA_ECHO else "WARNING"},
                "verifier": {"level": VERIFIER_LEVEL},
            },
        }
    )


setup_logging()


# Health check
@app.get("/api/health", tags=["Health"])
async def health():
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


async def verifier_loop(poll_interval: int = 5, cleanup_interval_sec: int = 10 * 60):
    await asyncio.sleep(3)
    verifier_logger.info("Verifier loop was launched at the startup.")

    last_cleanup_ts = 0.0

    while True:
        try:
            verifier_logger.info("֍ verifier_loop iteration start")

            # 1) Trade doğrulama — kendi session'unda
            async with async_session() as db:
                for exchange_name in settings.active_exchanges:
                    await verifier_iteration(db, exchange_name)

            # 2) Referral expiry cleanup — AYRI session
            now_ts = time.monotonic()
            if now_ts - last_cleanup_ts >= cleanup_interval_sec:
                try:
                    async with async_session() as s:
                        async with s.begin():
                            n = await cleanup_expired_reserved(s)
                    if n:
                        verifier_logger.info(
                            "Referral expiry cleanup: %s satır temizlendi", n
                        )
                except Exception as exc:
                    verifier_logger.exception("Referral expiry cleanup hata: %s", exc)
                last_cleanup_ts = now_ts

            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            verifier_logger.info("Verifier loop cancelled, shutting down.")
            break
        finally:
            verifier_logger.info("֍ verifier_loop iteration end")

    verifier_logger.info("Verifier loop terminated.")


@app.on_event("startup")
async def startup_event():
    # asyncio.create_task(
    #     verifier_loop(poll_interval=settings.VERIFY_INTERVAL_SECONDS)
    # )
    app.state.verifier_task = asyncio.create_task(
        verifier_loop(poll_interval=settings.VERIFY_INTERVAL_SECONDS)
    )


@app.on_event("shutdown")
async def shutdown_event():
    task = getattr(app.state, "verifier_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            verifier_logger.info("Verifier task cancelled.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

# https
# uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile cert/key.pem --ssl-certfile cert/cert.pem --reload
