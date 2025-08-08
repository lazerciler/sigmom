#!/usr/bin/env python3
# app/main.py

import asyncio
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import async_session       # AsyncSession factory
from app.routers import webhook_router, verify
from app.utils.exchange_loader import load_execution_module
from crud.trade import verify_pending_trades_for_execution
from app.exchanges.binance_futures_testnet.router import router as binance_router

# ————————————————
# Logger ayarları
logging.basicConfig(level=logging.INFO)
verifier_logger = logging.getLogger("verifier")
# ————————————————

app = FastAPI(title="SIGMOM Signal Interface", version="1.0.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(webhook_router.router)
app.include_router(binance_router)
app.include_router(verify.router)


# Health check
@app.get("/", tags=["Health"])
async def root():
    return {"status": "alive", "version": "1.0.0"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/favicon.ico")


# Verifier loop’u ayrı bir fonksiyon olarak tanımlıyoruz
async def verifier_loop():
    while True:
        try:
            verifier_logger.info("🔄 verifier_loop iteration start")
            async with async_session() as db:
                for exchange in settings.active_exchanges:
                    verifier_logger.info(f"→ Checking pending trades for {exchange}")
                    execution = load_execution_module(exchange)
                    await verify_pending_trades_for_execution(db, execution)
        except Exception as e:
            verifier_logger.exception(f"Verifier loop hatası: {e}")
        await asyncio.sleep(settings.VERIFY_INTERVAL_SECONDS)


# Uygulama ayağa kalkınca verifier_loop’u background task olarak başlatıyoruz
@app.on_event("startup")
async def start_verifier():
    asyncio.create_task(verifier_loop())
    verifier_logger.info("Verifier loop startup’ta başlatıldı.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
