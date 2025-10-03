#!/usr/bin/env python3
# app/main.py
# Python 3.9

import asyncio
import logging
import logging.config
import os
import sys
import time
import uuid
import contextvars

from app.utils.exchange_validator import validate_all
from app.config import settings
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware import Middleware
from starlette.types import ASGIApp
from typing import List

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
from app.services.unrealized_sync import sync_unrealized_for_execution

if sys.version_info < (3, 9):
    sys.exit(f"This app requires Python 3.9+. Found: {sys.version.split()[0]}")

# Global correlation id (rid) için contextvar
RID_CVAR: "contextvars.ContextVar[str]" = contextvars.ContextVar("rid", default="-")

# Logger ayarları (dictConfig içinde filter kullanacağız)
verifier_logger = logging.getLogger("verifier")


def _session_middleware_factory(asgi: ASGIApp) -> ASGIApp:
    return SessionMiddleware(asgi, secret_key=settings.SESSION_SECRET, same_site="lax")


middleware = [Middleware(_session_middleware_factory)]
app = FastAPI(title="SIGMOM Signal Interface", version="1.0.0", middleware=middleware)


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


class RequestIdFilter(logging.Filter):
    """Her log kaydına rid alanını enjekte eder (yoksa '-')."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.rid = RID_CVAR.get()
        return True


def setup_logging():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    sqla_echo = os.getenv("SQLA_ECHO", "0") == "1"
    verifier_level = os.getenv("VERIFIER_LEVEL", "INFO").upper()
    # verifier_level = os.getenv("VERIFIER_LEVEL", "WARNING").upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                # Tek tip format: timestamp level logger [rid] message
                "std": {
                    "format": "%(asctime)s %(levelname)s:%(name)s [rid=%(rid)s] %(message)s"
                }
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "std"}
            },
            "loggers": {
                "": {"handlers": ["console"], "level": log_level},
                "httpx": {"level": "WARNING"},
                "aiomysql": {"level": "WARNING"},
                "uvicorn.access": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "INFO" if sqla_echo else "WARNING"},
                "verifier": {"level": verifier_level},
            },
        }
    )
    _rid_filter = RequestIdFilter()
    root = logging.getLogger()
    for h in root.handlers:
        h.addFilter(_rid_filter)
    logging.getLogger("verifier").addFilter(_rid_filter)


setup_logging()


# Health check
@app.get("/api/health", tags=["Health"])
async def health():
    return {"status": "alive", "version": "1.0.0"}


# Basit Request-ID middleware: her isteğe kısa bir rid üret, log’lara ve header’a yaz
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    # Header'da geldiyse onu kullan, yoksa üret
    incoming = request.headers.get("X-Request-ID", "").strip()
    rid = incoming if incoming else uuid.uuid4().hex[:8]
    token = RID_CVAR.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        RID_CVAR.reset(token)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("app/static/favicon.ico")


def _verifier_exchanges() -> List[str]:
    """
    VERIFY_ONLY_DEFAULT=True ise yalnızca DEFAULT_EXCHANGE üzerinde çalış.
    Aksi halde ACTIVE_EXCHANGES listesini kullan.
    """
    default_ex = (getattr(settings, "DEFAULT_EXCHANGE", "") or "").strip()
    only_default = bool(getattr(settings, "VERIFY_ONLY_DEFAULT", True))
    if only_default and default_ex:
        return [default_ex]
    # settings.active_exchanges genellikle list[str]; yoksa CSV'yi parse et
    active_list = getattr(settings, "active_exchanges", None)
    if isinstance(active_list, (list, tuple)):
        return list(active_list)
    active_csv = getattr(settings, "ACTIVE_EXCHANGES", "")
    if isinstance(active_csv, str) and active_csv.strip():
        return [x.strip() for x in active_csv.split(",") if x.strip()]
    # hiçbiri yoksa güvenli düşüş: default varsa onu dön, yoksa boş
    return [default_ex] if default_ex else []


async def verifier_iteration(db, exchange_name: str) -> None:
    try:
        verifier_logger.info("→ Checking pending trades for %s", exchange_name)
        execution = load_execution_module(exchange_name)

        # Çöp fikir: Parameter 'exchange_name' unfilled (exchange), Unexpected argument (exchange=exchange_name)
        # await verify_pending_trades_for_execution(db, execution=execution)
        # await verify_closed_trades_for_execution(db, execution=execution, exchange=exchange_name)

        await verify_pending_trades_for_execution(db, exchange_name, execution)
        await verify_closed_trades_for_execution(db, execution, exchange_name)

        # Açık pozisyonların unrealized PnL senkronu (borsa → DB)
        try:
            n = await sync_unrealized_for_execution(db, exchange_name)
            verifier_logger.info(f"[uPnL] {exchange_name}: updated={n}")
        except Exception as exc:  # noqa: BLE001
            verifier_logger.exception("[uPnL] %s: sync error: %s", exchange_name, exc)

    except Exception as e:  # noqa: BLE001
        verifier_logger.error(
            "Verifier error for %s: %s", exchange_name, e, exc_info=True
        )


async def verifier_loop(poll_interval: int = 5, cleanup_interval_sec: int = 10 * 60):
    await asyncio.sleep(3)
    verifier_logger.info("Verifier loop was launched at the startup.")

    last_cleanup_ts = 0.0

    while True:
        _token = None  # verifier iteration'a özel RID token'ı
        try:
            # Her iterasyona özel bir rid üretelim; bu iterasyondaki tüm loglar gruplanır
            _token = RID_CVAR.set(f"vf-{uuid.uuid4().hex[:8]}")
            verifier_logger.info("֍ verifier_loop iteration start")

            # 1) Trade doğrulama — kendi session'unda
            async with async_session() as db:
                for exchange_name in _verifier_exchanges():
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
                            "Referral expiry cleanup: %s rows cleared", n
                        )
                except Exception as exc:  # noqa: BLE001
                    verifier_logger.exception("Referral expiry cleanup error: %s", exc)

                last_cleanup_ts = now_ts

            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            verifier_logger.info("Verifier loop cancelled, shutting down.")
            break
        finally:
            verifier_logger.info("֍ verifier_loop iteration end")
            if _token is not None:
                try:
                    RID_CVAR.reset(_token)
                except Exception:  # noqa: BLE001
                    pass

    verifier_logger.info("Verifier loop terminated.")


@asynccontextmanager
async def lifespan(app_: FastAPI):
    # ==== STARTUP ====
    app_.state.verifier_task = asyncio.create_task(  # type: ignore[attr-defined]
        verifier_loop(poll_interval=settings.VERIFY_INTERVAL_SECONDS)
    )
    try:
        verifier_logger.info(
            "Verifier exchanges (effective): %s",
            ", ".join(_verifier_exchanges()) or "∅",
        )
    except Exception:  # noqa: BLE001
        pass

    # Borsa sözleşmesi doğrulama (log’a yaz; istersen raise’a çevir)
    active_csv = getattr(settings, "ACTIVE_EXCHANGES", "")
    active = [x.strip() for x in active_csv.split(",") if x.strip()]
    issues = validate_all(active)
    if issues:
        msgs = []
        for ex, errs in issues:
            msgs.append(f"\n- {ex}:\n  - " + "\n  - ".join(errs))
        logging.getLogger("contract").error(
            "Exchange contract violations:%s", "".join(msgs)
        )

    # Uygulama request kabul etmeye burada başlar
    yield

    # ==== SHUTDOWN ====
    task = getattr(app_.state, "verifier_task", None)  # type: ignore[attr-defined]
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            verifier_logger.info("Verifier task cancelled.")


# Lifespan’ı FastAPI’ye tanıt
app.router.lifespan_context = lifespan  # type: ignore[attr-defined]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

# https
# uvicorn app.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile cert/key.pem --ssl-certfile cert/cert.pem --reload
