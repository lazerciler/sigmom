#!/usr/bin/env python3
# app/handlers/signal_handler.py
# Python 3.9
import logging
import asyncio
from decimal import Decimal
from typing import Optional, Dict

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models import StrategyOpenTrade
from app.schemas import WebhookSignal
from app.utils.exchange_loader import load_execution_module
from crud.raw_signal import insert_raw_signal
from crud.trade import (
    insert_strategy_open_trade,
    get_open_trade_for_close,
    close_open_trade_and_record,
    find_merge_candidate,
    verify_close_after_signal,
)
from app.utils.position_utils import confirm_open_trade

logger = logging.getLogger(__name__)


async def _force_sync_qty(
    db: AsyncSession, open_trade_id: int, pos: Optional[Dict]
) -> None:
    """
    Exchange → DB senkron emniyet kemeri:
    confirm_open_trade sonrası, DB'deki position_size ve entry_price'ı
    borsadan gelen kesin değerlerle zorlama günceller (gerekirse).
    """
    if not pos:
        return
    try:
        ex_amt = Decimal(str(pos.get("positionAmt", "0"))).copy_abs()
        ex_price = Decimal(str(pos.get("entryPrice", "0")))
    except Exception as e:
        logger.warning("[SYNC] parse error: %s", e)
        return
    res = await db.execute(
        select(StrategyOpenTrade).where(StrategyOpenTrade.id == open_trade_id)
    )
    row = res.scalar_one_or_none()
    if not row:
        return
    updates = {}
    try:
        db_amt = Decimal(str(row.position_size))
    except Exception:
        db_amt = None
    if db_amt is None or db_amt != ex_amt:
        updates["position_size"] = ex_amt
    # entry_price zaten doğruysa dokunma; değilse eşitle
    try:
        db_price = Decimal(str(row.entry_price))
    except Exception:
        db_price = None
    if db_price is None or db_price != ex_price:
        updates["entry_price"] = ex_price
    if updates:
        await db.execute(
            update(StrategyOpenTrade)
            .where(StrategyOpenTrade.id == open_trade_id)
            .values(**updates)
        )
        await db.flush()
        logger.info("[SYNC] Forced qty/price sync → %s", updates)


def _canon_side(side: Optional[str]) -> Optional[str]:
    """Sinyaldeki yönü projedeki standartla eşle (long/short)."""
    if side is None:
        return None
    s = str(side).strip().lower()
    if s in ("long", "buy", "open_long", "openlong"):
        return "long"
    if s in ("short", "sell", "open_short", "openshort"):
        return "short"
    return s


async def _get_position_for_side(
    execution, symbol: str, side: Optional[str]
) -> Optional[Dict]:
    """
    Hedge modunda doğru bacağı (long/short) sorgular; destek yoksa netsiz çağrıya düşer.
    """
    try:
        position_mode = getattr(execution.order_handler, "POSITION_MODE", "one_way")
        if position_mode == "hedge" and side:
            try:
                return await execution.order_handler.get_position(symbol, side=side)
            except TypeError:
                return await execution.order_handler.get_position(symbol)
        return await execution.order_handler.get_position(symbol)
    except Exception as e:
        logger.debug("[get_position] exception: %s", e)
        return None


def _amt(pos: Optional[Dict]) -> Decimal:
    return Decimal(str((pos or {}).get("positionAmt", "0"))).copy_abs()


async def _poll_position_change(
    execution,
    symbol: str,
    side: Optional[str],
    ref_amt: Decimal,
    attempts: int = 8,
    delay: float = 0.25,
) -> Optional[Dict]:
    """
    Pozisyon miktarı ref_amt'den farklı olana kadar kısa bir süre poll et.
    one_way'da 'net', hedge'de doğru bacak çekilir.
    """
    last = None
    for _ in range(attempts):
        last = await _get_position_for_side(execution, symbol, side)
        try:
            if _amt(last) != ref_amt:
                break
        except Exception:
            pass
        await asyncio.sleep(delay)
    return last


async def handle_signal(signal_data: WebhookSignal, db: AsyncSession) -> dict:
    logger.info("Signal received: %s", signal_data)
    logger.info("Order type: %s", signal_data.order_type)

    if signal_data.order_type.lower() != "market":
        logger.warning(
            "Only market orders are supported. The transaction was rejected."
        )
        raise HTTPException(
            status_code=400,
            detail="Limit orders are not currently supported by the system.",
        )

    # if signal_data.order_type.lower() not in ("market", "limit"):
    #     logger.warning(
    #         "Only market or limit orders are supported. The transaction was rejected."
    #     )
    #     raise HTTPException(
    #         status_code=400,
    #         detail="Only market or limit orders are supported.",
    #     )

    # Borsa modülünü yükle
    try:
        execution = load_execution_module(signal_data.exchange)
    except Exception as e:
        logger.exception("Exchange module failed to load")
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    # Raw sinyali kaydet ve hemen commit et
    raw_signal = await insert_raw_signal(db, signal_data)
    await db.commit()
    logger.info("The received raw signal was recorded.")

    # Sonraki işlemler için yeni bir transaction başlat
    await db.begin()

    # OPEN
    if signal_data.mode == "open":
        try:
            # PRE-FLIGHT: Emirden önce kaldıraç ayarı
            if signal_data.leverage is not None:
                lev_res = await execution.order_handler.set_leverage(
                    signal_data.symbol, signal_data.leverage
                )
                if not lev_res or not lev_res.get("success", False):
                    logger.warning("Leverage preflight failed: %s", lev_res)
                else:
                    logger.info(
                        "Preflight leverage set → %s x%s",
                        signal_data.symbol,
                        signal_data.leverage,
                    )

            # Yönü tekilleştir
            canonical_side = _canon_side(signal_data.side)

            # === one_way MODUNDA TERS YÖN GELDİYSE → REDUCE (CLOSE) ===
            execution = load_execution_module(signal_data.exchange)
            # Mevcut açık trade'i fund_manager_id ile ve her iki side için ara
            open_trade = await find_merge_candidate(
                db,
                symbol=signal_data.symbol,
                exchange=signal_data.exchange,
                side="long",
                fund_manager_id=signal_data.fund_manager_id,
            ) or await find_merge_candidate(
                db,
                symbol=signal_data.symbol,
                exchange=signal_data.exchange,
                side="short",
                fund_manager_id=signal_data.fund_manager_id,
            )

            if open_trade is not None:
                # Hedge ise doğru bacağı, değilse net pozisyonu oku
                pos_now = await _get_position_for_side(
                    execution, signal_data.symbol, open_trade.side
                )
                # positionAmt>0 → long, <0 → short
                try:
                    amt_now = Decimal(
                        str((pos_now or {}).get("positionAmt", "0"))
                    ).copy_abs()
                except Exception:
                    amt_now = Decimal("0")

                # order_handler.settings içindeki mod
                position_mode = getattr(
                    execution.order_handler, "POSITION_MODE", "one_way"
                )

                # one_way ve YÖN FARKLI ise: bu "open" sinyalini REDUCE (close) olarak uygula
                if (
                    position_mode != "hedge"
                    and amt_now > Decimal("0")
                    and (open_trade.side != signal_data.side)
                ):
                    reduce_qty = min(amt_now, Decimal(str(signal_data.position_size)))
                    if reduce_qty > Decimal("0"):
                        # CLOSE sinyali oluştur (schema close exit_price zorunlu, borsa entryPrice ile besliyoruz)
                        exit_px = (pos_now or {}).get("entryPrice") or str(
                            signal_data.entry_price
                        )
                        close_signal = WebhookSignal(
                            mode="close",
                            symbol=signal_data.symbol,
                            side=open_trade.side,  # close mantığı: mevcut yön
                            position_size=float(reduce_qty),
                            order_type=signal_data.order_type,
                            exchange=signal_data.exchange,
                            timestamp=signal_data.timestamp,
                            fund_manager_id=signal_data.fund_manager_id,
                            exit_price=float(exit_px),
                            leverage=signal_data.leverage,  # close için şart değil ama dolduruyoruz
                        )
                        coid = f"sai_close_{raw_signal.id}"
                        order_result = await execution.order_handler.place_order(
                            close_signal, client_order_id=coid
                        )
                        if not order_result.get("success"):
                            await db.rollback()
                            return {
                                "success": False,
                                "message": f"Reduce (close) order failed: "
                                f"{order_result.get('message', 'Unknown error')}",
                                "response_data": order_result.get("data", {}),
                            }
                        # BORSADAN GERÇEK POZİSYONU ÇEK → DB’yi SENKRONLA
                        pos_after = await _poll_position_change(
                            execution,
                            signal_data.symbol,
                            open_trade.side,
                            ref_amt=amt_now,
                        )
                        try:
                            amt_after = Decimal(
                                str((pos_after or {}).get("positionAmt", "0"))
                            ).copy_abs()
                        except Exception:
                            amt_after = Decimal("0")

                        if amt_after == Decimal("0"):
                            # Tamamen kapandı → trade kaydını kapat ve StrategyTrade’e yaz
                            await close_open_trade_and_record(db, open_trade, pos_after)
                            await db.commit()
                            return {
                                "success": True,
                                "message": "Counter signal (one_way): position fully closed and recorded.",
                                "public_id": open_trade.public_id,
                            }
                        else:
                            # Kısmi kapandı → open trade'i borsa verisiyle güncelle,
                            # sonra emniyet kemeriyle zorla eşitle
                            await confirm_open_trade(db, open_trade, pos_after)
                            await _force_sync_qty(db, open_trade.id, pos_after)
                            await db.commit()
                            return {
                                "success": True,
                                "message": "Counter signal (one_way): position reduced and synced with exchange.",
                                "public_id": open_trade.public_id,
                            }

            # === NORMAL OPEN (aynı yönde artırma dâhil) ===
            # Emirden önce referans pozisyonu oku (race condition önlemi)
            pos_before_open = await _get_position_for_side(
                execution, signal_data.symbol, canonical_side
            )
            ref_amt = _amt(pos_before_open)
            # Emir gönder
            coid = f"sai_open_{raw_signal.id}"
            order_result = await execution.order_handler.place_order(
                signal_data, client_order_id=coid
            )
            if not order_result.get("success"):

                logger.error("OPEN order failed: %s", order_result)
                await db.rollback()
                return {
                    "success": False,
                    "message": f"Opening order failed: {order_result.get('message', 'Unknown error')}",
                    "response_data": order_result.get("data", {}),
                }

            # Aynı yönde açık pozisyon var mı? (side tekilleştirilmiş)
            merge_candidate = await find_merge_candidate(
                db,
                symbol=signal_data.symbol,
                exchange=signal_data.exchange,
                side=canonical_side,
                fund_manager_id=signal_data.fund_manager_id,
            )

            if merge_candidate:
                open_trade = merge_candidate  # yeni satır açma
            else:
                # İlk kez açılıyorsa mevcut davranışı koru (INSERT)
                open_trade = await insert_strategy_open_trade(
                    db=db,
                    open_trade=execution.order_handler.build_open_trade_model(
                        signal_data=signal_data,
                        order_response=order_result,
                        raw_signal_id=raw_signal.id,
                    ),
                )

            # BORSADAN GERÇEK POZİSYON (race guard ile) → entryPrice & positionAmt ile DB’yi senkronla
            pos_after_open = await _poll_position_change(
                execution, signal_data.symbol, open_trade.side, ref_amt=ref_amt
            )
            await confirm_open_trade(db, open_trade, pos_after_open)
            # Bazı borsalarda/latency durumlarında qty güncellenmeyebiliyor → emniyet kemeri
            await _force_sync_qty(db, open_trade.id, pos_after_open)
            await db.commit()
            return {
                "success": True,
                "message": "The position was opened/increased and synced with the exchange.",
                "public_id": open_trade.public_id,
            }

        except Exception as e:
            logger.exception("OPEN operation failed: %s", e)
            await db.rollback()
            return {"success": False, "message": f"OPEN error: {e}"}

    # CLOSE
    elif signal_data.mode == "close":
        logger.info(
            "CLOSE signal received → %s | %s", signal_data.symbol, signal_data.exchange
        )

        # 1) Kapatılacak open trade’i güvenli seç
        open_trade = await get_open_trade_for_close(
            db=db,
            public_id=signal_data.public_id,
            symbol=signal_data.symbol,
            exchange=signal_data.exchange,
            fund_manager_id=signal_data.fund_manager_id,
            side=_canon_side(
                getattr(signal_data, "side", None)
            ),  # hedge için doğru bacak
        )
        # Hedge: sinyalde side geldiyse yanlış bacak seçildiyse düzelt / ya da hiç bulunamadıysa side ile seç
        try:
            position_mode = getattr(execution.order_handler, "POSITION_MODE", "one_way")
        except Exception:
            position_mode = "one_way"

        # desired_side = _canon_side(getattr(signal_data, "side", None))
        # if (
        #     position_mode == "hedge"
        #     and desired_side
        #     and open_trade is not None
        #     and open_trade.side != desired_side
        # ):
        #     cand = await find_merge_candidate(
        #         db,
        #         symbol=signal_data.symbol,
        #         exchange=signal_data.exchange,
        #         side=desired_side,
        #         fund_manager_id=signal_data.fund_manager_id,
        #     )
        #     if cand:
        #         open_trade = cand

        desired_side = _canon_side(getattr(signal_data, "side", None))
        if position_mode == "hedge" and desired_side:
            if open_trade is None or open_trade.side != desired_side:
                cand = await find_merge_candidate(
                    db,
                    symbol=signal_data.symbol,
                    exchange=signal_data.exchange,
                    side=desired_side,
                    fund_manager_id=signal_data.fund_manager_id,
                )
                if cand:
                    open_trade = cand

        if open_trade is None:
            logger.error(
                "[CLOSE] No matching open position found (if there is no public id, the last open record is checked)."
            )
            await db.rollback()
            return {
                "success": False,
                "message": "No open positions were found to be closed.",
            }

        # 2) Close emrini gönder (LEVERAGE YOK!)
        coid = f"sai_close_{raw_signal.id}"
        order_result = await execution.order_handler.place_order(
            signal_data, client_order_id=coid
        )
        if not order_result.get("success"):
            logger.error("[CLOSE] Order failed: %s", order_result)
            await db.rollback()
            return {
                "success": False,
                "message": f"Close order failed: {order_result.get('message', 'Unknown error')}",
                "response_data": order_result.get("data", {}),
            }

        # 3) Pozisyonu race-safe kontrol et (poll ile)
        pos_first = await _get_position_for_side(
            execution, signal_data.symbol, open_trade.side
        )
        ref_amt = _amt(pos_first)
        pos_after = await _poll_position_change(
            execution, signal_data.symbol, open_trade.side, ref_amt=ref_amt
        )

        if pos_after and _amt(pos_after) == Decimal("0"):
            # Tam kapanış: kalıcı trade’e taşı
            await close_open_trade_and_record(db, open_trade, pos_after)
            await db.commit()
            return {
                "success": True,
                "message": "Position closed and recorded.",
                "public_id": open_trade.public_id,
            }
        else:
            # Kısmi kapanış: açık trade'i borsa verisiyle hemen güncelle + emniyet kemeri
            await confirm_open_trade(db, open_trade, pos_after)
            await _force_sync_qty(db, open_trade.id, pos_after)
            await db.commit()
            # return {
            #     "success": True,
            #     "message": "Position reduced and synced with the exchange.",
            #     "public_id": open_trade.public_id,
            # }
            # Ardından kısa bir onay penceresi: kapanış tamamlandı mı diye yeniden dene
            ok = await verify_close_after_signal(
                db,
                execution,
                public_id=open_trade.public_id,
                symbol=signal_data.symbol,
                exchange=signal_data.exchange,
                max_retries=5,
                interval_seconds=0.5,
            )
            if ok:
                return {
                    "success": True,
                    "message": "Position closed after short retry window.",
                    "public_id": open_trade.public_id,
                }
            return {
                "success": True,
                "message": "Position reduced and synced; close confirmation pending.",
                "public_id": open_trade.public_id,
            }
