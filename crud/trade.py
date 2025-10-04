#!/usr/bin/env python3
# crud/trade.py
# Python 3.9

import uuid
import logging
import asyncio

from decimal import Decimal, InvalidOperation
from importlib import import_module
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update, desc, func, and_
from typing import Union, Optional, List, cast
from sqlalchemy.sql.elements import ColumnElement  # PyCharm tip denetimi için
from app.models import StrategyOpenTrade, StrategyTrade
from app.utils.position_utils import position_matches, confirm_open_trade
from sqlalchemy import text


async def find_merge_candidate(
    db: AsyncSession,
    *,
    symbol: str,
    exchange: str,
    side: str,
    fund_manager_id: str,
) -> Optional[StrategyOpenTrade]:
    """
    Aynı (symbol, exchange, side, fund_manager) için 'open' ya da 'pending' durumdaki
    en güncel açık pozisyonu döndürür.
    """
    # Koşulları tek tek zincirleyerek ekle (IDE'nin 'bool' şüphesini kaldırır)
    q = select(StrategyOpenTrade)
    q = q.where(func.upper(StrategyOpenTrade.symbol) == (symbol or "").strip().upper())
    q = q.where(StrategyOpenTrade.exchange == (exchange or "").strip())
    q = q.where(StrategyOpenTrade.side == (side or "").strip().lower())
    q = q.where(StrategyOpenTrade.fund_manager_id == (fund_manager_id or "").strip())
    q = q.where(StrategyOpenTrade.status.in_(("open", "pending")))
    q = q.order_by(desc(StrategyOpenTrade.id)).limit(1)
    res = await db.execute(q)
    return res.scalar_one_or_none()


def pick_close_price(position_data: dict) -> Decimal:
    """Ortak işlem/piyasa alanlarından geçerli (>0) bir kapanış fiyatı seçin.
    EntryPrice veya 0'a asla geri dönmeyin.
    Tercih: avgClosePrice, avgPrice, price, lastPrice, closePrice, markPrice.
    """
    for key in (
        "avgClosePrice",
        "avgPrice",
        "price",
        "lastPrice",
        "closePrice",
        "markPrice",
    ):
        v = position_data.get(key)
        if v is None or str(v).strip() == "":
            continue
        try:
            d = Decimal(str(v))
        except InvalidOperation:
            raise ValueError(f"Invalid close_price value: {v}")
        if d > 0:
            return d
    raise ValueError(f"No valid close_price found: position_data={position_data}")


def compute_pnl(
    side: str, entry_price: Decimal, exit_price: Decimal, position_size: Decimal
) -> Decimal:
    s = (side or "").lower()
    if s == "long":
        return (exit_price - entry_price) * position_size
    if s == "short":
        return (entry_price - exit_price) * position_size
    raise ValueError(f"Geçersiz side='{side}'")


async def get_open_trade_for_close(
    db: AsyncSession,
    public_id: Optional[str],
    symbol: str,
    exchange: str,
    fund_manager_id: Optional[str] = None,
    side: Optional[str] = None,
) -> Union[StrategyOpenTrade, None]:
    """
    Close sinyali geldiğinde kapatılacak open trade'i güvenli biçimde seçer.
    - Öncelik public_id (tekil ve güvenli).
    - public_id yoksa: symbol+exchange+status='open' içinden EN SON kaydı alır.
    - symbol karşılaştırması case-insensitive; symbol/exchange 'strip' edilir.
    """
    # Normalize inputs to avoid case/whitespace mismatches
    sym = (symbol or "").strip().upper()
    ex = (exchange or "").strip()

    if public_id:
        q = select(StrategyOpenTrade).where(
            and_(
                StrategyOpenTrade.public_id == public_id,
                StrategyOpenTrade.status == "open",
            )
        )
        res = await db.execute(q)
        return res.scalar_one_or_none()

    q = select(StrategyOpenTrade)
    q = q.where(func.upper(StrategyOpenTrade.symbol) == sym)
    q = q.where(StrategyOpenTrade.exchange == ex)
    q = q.where(StrategyOpenTrade.status == "open")

    if fund_manager_id:
        q = q.where(StrategyOpenTrade.fund_manager_id == fund_manager_id.strip())
    if side:
        q = q.where(StrategyOpenTrade.side == side.strip().lower())
    q = q.order_by(desc(StrategyOpenTrade.id))

    res = await db.execute(q)

    return res.scalars().first()


LOGGER = logging.getLogger("verifier")


async def close_open_trade_and_record(
    db: AsyncSession, open_trade: StrategyOpenTrade, position_data: dict
):
    """
    Açık pozisyon kapanmışsa:
    - PnL hesaplanır,
    - StrategyTrade tablosuna yazılır,
    - StrategyOpenTrade status='closed' yapılır.
    """

    # --- Lazy load/expire sorunlarına karşı gerekli alanları snapshota al ---
    _ot_id = getattr(open_trade, "id", None)
    _ot_sym = getattr(open_trade, "symbol", None)
    _ot_side = getattr(open_trade, "side", None)
    _ot_fm = getattr(open_trade, "fund_manager_id", None)
    _ot_exch = getattr(open_trade, "exchange", None)

    try:
        res = await db.execute(
            update(StrategyOpenTrade)
            .where(
                and_(
                    StrategyOpenTrade.id == open_trade.id,
                    StrategyOpenTrade.status == "open",
                )
            )
            .values(status="closed")
        )
        if (res.rowcount or 0) == 0:
            # Başkası bizden önce kapatmış; tekrar trade yazmayalım.
            LOGGER.info("[idempotent-skip] already closed → %s", open_trade.public_id)
            await db.rollback()
            return True

        # 2) Kayıt kapandıktan sonra güncel halini getir (audit için)
        trade = (
            await db.execute(
                select(StrategyOpenTrade).where(
                    cast(ColumnElement[bool], StrategyOpenTrade.id == open_trade.id)
                )
            )
        ).scalar_one()

        # --- SAFE close price: asla entryPrice/0 değil ---
        # 1) Mevcut mantıkla dene (sadece beklenen hataları yakala)
        try:
            close_price = pick_close_price(position_data)
        except (ValueError, InvalidOperation, TypeError, KeyError):
            close_price = None

        # 2) Pozisyon borsada kapalıysa (amt==0) veya bulunamadıysa → userTrades→VWAP
        try:
            amt_zero = False
            try:
                amt_zero = (
                    float(str((position_data or {}).get("positionAmt", "0")) or 0)
                    == 0.0
                )
            except (ValueError, TypeError):
                pass

            if close_price is None or amt_zero:
                ex_name = (open_trade.exchange or "").strip()
                mod = import_module(f"app.exchanges.{ex_name}.account")
                helper = getattr(mod, "get_close_price_from_usertrades", None)
                if callable(helper):
                    res = await helper(
                        open_trade.symbol,
                        getattr(open_trade, "timestamp", None),
                        side=(open_trade.side or "").lower(),
                    )
                    if res and res.get("success"):
                        close_price = Decimal(str(res["price"]))
                        LOGGER.info(
                            "[fallback-vwap] %s price=%s (fills=%s)",
                            open_trade.symbol,
                            close_price,
                            res.get("fills"),
                        )
        except Exception as _e:
            LOGGER.warning("[fallback-vwap-fail] %s: %s", open_trade.symbol, _e)

        if close_price is None:
            raise ValueError("close_price could not be determined")
        # Audit: kapanış fiyatı hangi alandan geldi?
        _keys = (
            "avgClosePrice",
            "avgPrice",
            "price",
            "lastPrice",
            "closePrice",
            "markPrice",
        )
        _src = next((k for k in _keys if str(position_data.get(k)).strip()), None)
        LOGGER.info("[close-price-source] %s → vwap=%s", open_trade.symbol, close_price)

        # --- Zorunlu alanlar / guard'lar ---
        open_price = Decimal(str(open_trade.entry_price))
        if open_price <= 0:
            raise ValueError(f"Geçersiz entry_price={open_price}")

        position_size = Decimal(str(open_trade.position_size))
        if position_size <= 0:
            raise ValueError(f"Geçersiz position_size={position_size}")

        side = (getattr(open_trade, "side", "") or "").lower()
        if side not in ("long", "short"):
            raise ValueError(f"Geçersiz side={trade.side}")

        # --- PnL ---
        pnl = compute_pnl(side, open_price, close_price, position_size)

        closed_trade = StrategyTrade(
            public_id=str(uuid.uuid4()),
            open_trade_public_id=open_trade.public_id,
            raw_signal_id=open_trade.raw_signal_id,
            symbol=open_trade.symbol,
            side=open_trade.side,
            entry_price=open_price,
            exit_price=close_price,
            position_size=position_size,
            leverage=open_trade.leverage,
            realized_pnl=pnl,
            order_type=open_trade.order_type or "market",
            timestamp=datetime.utcnow(),
            exchange=open_trade.exchange,
            fund_manager_id=open_trade.fund_manager_id,
            # audit için kapanış anındaki fiyat alanlarını sakla
            response_data={
                **(open_trade.response_data or {}),
                "position_snapshot": {
                    k: position_data.get(k)
                    for k in (
                        "avgClosePrice",
                        "avgPrice",
                        "price",
                        "lastPrice",
                        "closePrice",
                        "markPrice",
                    )
                },
            },
        )

        # 3) Trade tablosuna ekle
        db.add(closed_trade)
        await db.flush()

        # 4) Commit
        try:
            await db.commit()
        except Exception as e:
            LOGGER.exception("[DB-COMMIT-FAIL] %s", e)
            await db.rollback()
            return False

        # Commit sonrası doğrulama
        try:
            result = await db.execute(
                text(
                    """
                    SELECT id, public_id, symbol, realized_pnl
                    FROM strategy_trades
                    WHERE open_trade_public_id = :otpid
                    ORDER BY id DESC LIMIT 1
                    """
                ),
                {"otpid": open_trade.public_id},
            )
            row = result.fetchone()
            if row:
                LOGGER.info(
                    "[DB-VERIFY] Trade kaydı bulundu → ID: %s, Symbol: %s, PnL: %s",
                    row.id,
                    row.symbol,
                    row.realized_pnl,
                )
            else:
                LOGGER.warning(
                    "[DB-VERIFY] Commit sonrası trade kaydı BULUNAMADI! → open_trade_public_id=%s",
                    open_trade.public_id,
                )
        except Exception as e:
            LOGGER.exception("[DB-VERIFY-FAIL] %s", e)

        LOGGER.info(
            "[closed-recorded] %s → PnL: %.2f was written and open trade status set to CLOSED.",
            _ot_sym,
            pnl,
        )
        return True

    except Exception as e:
        try:
            await db.rollback()
        except Exception as rollback_exc:  # noqa: BLE001
            LOGGER.exception("[close-fail-rollback] %s", rollback_exc)
        # ORM alanlarına dokunmadan snapshot ile logla → MissingGreenlet’i engeller
        LOGGER.error(
            "[close-fail] id=%s sym=%s side=%s fm=%s exch=%s err=%s",
            _ot_id,
            _ot_sym,
            _ot_side,
            _ot_fm,
            _ot_exch,
            e,
        )
        return False


# async def increment_attempt_count(db: AsyncSession, trade_id: int) -> StrategyOpenTrade:
async def increment_attempt_count(db: AsyncSession, trade_id: int) -> None:
    await db.execute(
        update(StrategyOpenTrade)
        .where(StrategyOpenTrade.id == trade_id)
        .values(
            verification_attempts=StrategyOpenTrade.verification_attempts + 1,
            last_checked_at=datetime.utcnow(),
        )
    )
    # Burada ORM dönmek gereksiz ve riskli (commit sonrası akses tetikleyebilir)
    # Çağıranlar dönüş değerini kullanmıyor; None dön.
    return None


async def get_pending_open_trades(db: AsyncSession) -> list[StrategyOpenTrade]:
    result = await db.execute(
        select(StrategyOpenTrade).where(StrategyOpenTrade.status == "pending")
    )
    return cast(List[StrategyOpenTrade], result.scalars().all())


async def mark_trade_as_open(db: AsyncSession, open_trade: StrategyOpenTrade):
    await db.execute(
        update(StrategyOpenTrade)
        .where(cast(ColumnElement[bool], StrategyOpenTrade.id == open_trade.id))
        .values(
            status="open",
            exchange_verified=True,
            confirmed_at=datetime.utcnow(),
            last_checked_at=datetime.utcnow(),
        )
    )


async def mark_trade_as_failed(db: AsyncSession, open_trade: StrategyOpenTrade):
    await db.execute(
        update(StrategyOpenTrade)
        .where(cast(ColumnElement[bool], StrategyOpenTrade.id == open_trade.id))
        .values(
            status="failed",
            exchange_verified=False,
            last_checked_at=datetime.utcnow(),
            verification_attempts=StrategyOpenTrade.verification_attempts + 1,
        )
    )


async def verify_pending_trades_for_execution(
    # db: AsyncSession, execution, max_retries: int = 3
    db: AsyncSession,
    execution,
    exchange_name: str,
    max_retries: int = 3,
):
    """
    Pending durumdaki açık pozisyonları exchange ile doğrular.
    Başarılıysa status="open", exchange_verified=True;
    retry aşıldıysa status="failed".
    """
    verifier_logger = LOGGER

    exchange = (exchange_name or "").strip()

    result = await db.execute(
        # select(StrategyOpenTrade).where(StrategyOpenTrade.status == "pending")
        select(StrategyOpenTrade).where(
            StrategyOpenTrade.status == "pending",
            StrategyOpenTrade.exchange == exchange,
        )
    )
    pending_trades = result.scalars().all()
    # verifier_logger.info("[loop] %s pending trade found", len(pending_trades))
    verifier_logger.info(
        "[loop] %s pending trade found for %s",
        len(pending_trades),
        exchange if exchange else "<empty>",
    )

    for open_trade in pending_trades:
        now = datetime.utcnow()

        if open_trade.last_checked_at and (
            now - open_trade.last_checked_at
        ) < timedelta(seconds=5):
            verifier_logger.debug("[skip] %s - checked too recently", open_trade.symbol)
            continue

        verifier_logger.debug(
            "[verify-start] %s | side: %s, size: %s",
            open_trade.symbol,
            open_trade.side,
            open_trade.position_size,
        )
        verifier_logger.debug(
            "execution.order_handler.get_position: %s",
            getattr(execution.order_handler, "get_position", "NONE"),
        )

        try:
            position = await execution.order_handler.get_position(open_trade.symbol)
        except Exception as e:
            verifier_logger.warning(
                "[exception] get_position(%s) exception: %s", open_trade.symbol, e
            )
            continue

        verifier_logger.debug("[position] %s: %r", open_trade.symbol, position)
        verifier_logger.debug(
            "Position was brought: %s → %s", open_trade.symbol, position
        )

        if not position:
            verifier_logger.warning(
                "[no-position] Could not get a position for %s", open_trade.symbol
            )
            continue

        # Yeni signature ile kullan
        if position_matches(position):
            open_trade.status = "open"
            open_trade.exchange_verified = True
            open_trade.confirmed_at = now
            await confirm_open_trade(db, open_trade, position)
            verifier_logger.info("[verified] %s position confirmed.", open_trade.symbol)
        else:
            await increment_attempt_count(db, open_trade.id)
            await db.refresh(open_trade)

            if open_trade.verification_attempts >= max_retries:
                open_trade.status = "failed"
                verifier_logger.warning(
                    "[failed] %s max retries (%s) exceeded, position is invalid.",
                    open_trade.symbol,
                    max_retries,
                )
            else:
                verifier_logger.debug(
                    "[retry] %s retries %s/%s",
                    open_trade.symbol,
                    open_trade.verification_attempts,
                    max_retries,
                )

        open_trade.last_checked_at = now
        await db.commit()


# -------------------- CLOSE doğrulama / retry --------------------
async def verify_close_after_signal(
    db: AsyncSession,
    execution,
    *,
    public_id: Optional[str],
    symbol: str,
    exchange: str,
    max_retries: int = 5,
    interval_seconds: float = 2.0,
) -> bool:
    """
    Close sinyali atıldıktan sonra borsayı kontrol eder.
    - Kapanış doğrulanırsa: close_open_trade_and_record(...) çağrılır ve True döner.
    - Kapanmazsa: birkaç kez yeniden dener; sonunda açık bırakır ve False döner.
    Şema değişikliği yok; mevcut verification_attempts/last_checked_at alanlarını kullanır.
    """
    open_trade = await get_open_trade_for_close(db, public_id, symbol, exchange)
    if not open_trade:
        return False

    # Çoktan kaydedilmişse hiç uğraşma
    ex_q = await db.execute(
        select(func.count())
        .select_from(StrategyTrade)
        .where(StrategyTrade.open_trade_public_id == open_trade.public_id)
    )
    if (ex_q.scalar_one() or 0) > 0:
        # statü açık kalmışsa kapat ve KALICI yap
        if (open_trade.status or "").lower() != "closed":
            open_trade.status = "closed"
            await db.flush()
            await db.commit()  # ← kritik: commit yoksa session kapanınca atılır
        return True

    for _ in range(max_retries):
        # now = datetime.utcnow()
        # Pozisyonu getir
        try:
            position = await execution.order_handler.get_position(symbol)
        except Exception as e:
            LOGGER.warning("[close-check] get_position(%s) ex: %s", symbol, e)
            position = None

        # KAPANDI mı? (one-way için net 0, hedge için kaba yaklaşım: işaret değişti ya da 0)
        amt = Decimal(str((position or {}).get("positionAmt", 0)))
        side = (open_trade.side or "").lower()
        closed = (
            (amt == 0)
            or (side == "long" and amt <= 0)
            or (side == "short" and amt >= 0)
        )

        if closed:
            ok = await close_open_trade_and_record(db, open_trade, position or {})
            if ok:
                return True
            LOGGER.error(
                "[close-fail-after-signal] could not record close for %s", symbol
            )
            return False

        # Kapanmamışsa deneme sayacı/son kontrol zamanı güncelle
        await increment_attempt_count(db, open_trade.id)
        await db.commit()
        await asyncio.sleep(interval_seconds)

    # Hâlâ kapanmadı → açık bırak, logla
    LOGGER.warning(
        "[close-timeout] %s not closed after %s tries; keeping OPEN.",
        symbol,
        max_retries,
    )
    return False


async def insert_strategy_trade_from_open(
    db: AsyncSession,
    open_trade,
    signal_data,
    order_response: dict,
    close_raw_signal,  # yeni parametre
):
    try:
        entry_price = Decimal(str(open_trade.entry_price))
        exit_price = Decimal(str(getattr(signal_data, "exit_price", None)))
        position_size = Decimal(str(open_trade.position_size))
    except (InvalidOperation, TypeError) as e:
        raise RuntimeError(f"Price conversion error: {e}")

    side = open_trade.side.lower()
    if side == "long":
        pnl_value = (exit_price - entry_price) * position_size
    else:
        pnl_value = (entry_price - exit_price) * position_size

    trade = StrategyTrade(
        public_id=str(uuid.uuid4()),
        raw_signal_id=close_raw_signal.id,  # close sinyalinin raw_signal.id'si
        open_trade_public_id=open_trade.public_id,
        symbol=signal_data.symbol,
        side=signal_data.side,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        leverage=open_trade.leverage,
        realized_pnl=pnl_value,
        order_type=signal_data.order_type,
        timestamp=datetime.utcnow(),
        exchange=signal_data.exchange,
        fund_manager_id=signal_data.fund_manager_id,
        response_data=order_response.get("data", {}),
    )
    db.add(trade)


async def insert_strategy_open_trade(db: AsyncSession, open_trade: StrategyOpenTrade):
    """
    Yeni açık pozisyonu DB'ye ekler. open_trade.exchange_order_id
    ve status="pending" olarak gelmiş olmalı.
    """
    db.add(open_trade)
    await db.flush()
    return open_trade


async def insert_strategy_trade(db: AsyncSession, signal_data, order_response: dict):
    open_trade = await get_open_trade_by_symbol_and_exchange(
        db, signal_data.symbol, signal_data.exchange
    )
    if not open_trade:
        raise RuntimeError("No open positions found for Close")

    # Fiyatları Decimal'a çevir
    try:
        entry_price = Decimal(str(open_trade.entry_price))
        exit_price = Decimal(str(getattr(signal_data, "exit_price", None)))
    except (InvalidOperation, TypeError) as e:
        raise RuntimeError(f"Price conversion error: {e}")

    position_size = Decimal(str(open_trade.position_size))
    side = open_trade.side.lower()

    if side == "long":
        realized_pnl = (exit_price - entry_price) * position_size
    else:
        realized_pnl = (entry_price - exit_price) * position_size

    trade = StrategyTrade(
        public_id=str(uuid.uuid4()),
        open_trade_public_id=open_trade.public_id,
        symbol=signal_data.symbol,
        side=signal_data.side,
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        leverage=open_trade.leverage,
        realized_pnl=realized_pnl,
        exchange=signal_data.exchange,
        fund_manager_id=signal_data.fund_manager_id,
        response_data=order_response.get("data", {}),
        timestamp=datetime.utcnow(),
    )
    db.add(trade)


async def get_open_trade_by_symbol_and_exchange(
    db: AsyncSession, symbol: str, exchange: str
):
    query = select(StrategyOpenTrade)
    query = query.where(cast(ColumnElement[bool], StrategyOpenTrade.symbol == symbol))
    query = query.where(
        cast(ColumnElement[bool], StrategyOpenTrade.exchange == exchange)
    )

    result = await db.execute(query)
    return result.scalar_one_or_none()


async def delete_open_trade_by_id(db: AsyncSession, trade_id: str):
    # query = delete(StrategyOpenTrade).where(StrategyOpenTrade.id == trade_id)
    query = delete(StrategyOpenTrade).where(
        cast(ColumnElement[bool], StrategyOpenTrade.id == trade_id)
    )
    await db.execute(query)
    await db.commit()


async def delete_strategy_open_trade(db: AsyncSession, symbol: str, exchange: str):
    """
    Belirtilen sembol ve borsaya ait açık pozisyon kaydını siler.
    """
    query = delete(StrategyOpenTrade)
    query = query.where(cast(ColumnElement[bool], StrategyOpenTrade.symbol == symbol))
    query = query.where(
        cast(ColumnElement[bool], StrategyOpenTrade.exchange == exchange)
    )
    await db.execute(query)
    await db.commit()
