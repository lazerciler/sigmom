#!/usr/bin/env python3
# app/services/unrealized_sync.py
# Python 3.9

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import asyncio
import httpx
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StrategyOpenTrade
from app.utils.exchange_loader import load_execution_module
from importlib import import_module

logger = logging.getLogger("verifier")


def _to_dec(x: Any) -> Decimal:
    """Gelen değeri güvenli şekilde Decimal'e çevir."""
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _desc(obj: Any) -> str:
    """Kısa tanım: list/dict uzun metin yazmadan loglamak için."""
    t = type(obj).__name__
    if isinstance(obj, list):
        return f"{t} len={len(obj)}"
    if isinstance(obj, dict):
        keys = list(obj.keys())[:5]
        return f"{t} keys={keys}"
    return t


async def sync_unrealized_for_execution(db: AsyncSession, exchange_name: str) -> int:
    """
    Borsadan (exchange adapter) AÇIK işlemlerin unrealized PnL'ini alır
    ve strategy_open_trades.unrealized_pnl alanını günceller.
    Kaynak: app.exchanges.<exchange>.account.get_unrealized (borsa verisi).
    Dönüş: güncellenen satır sayısı.
    """
    # 'open' durumu: ENUM/kolasyon tuhaflıklarına takılmamak için küçük bir IN filtresi
    q = select(StrategyOpenTrade).where(
        StrategyOpenTrade.status.in_(("open", "Open", "OPEN")),
        StrategyOpenTrade.exchange == exchange_name,
    )
    result = await db.scalars(q)
    rows: list[StrategyOpenTrade] = list(result)
    logger.debug("[uPnL diag] exchange=%s | open_rows=%d", exchange_name, len(rows))
    if not rows:
        return 0

    execution = load_execution_module(exchange_name)

    # __init__.py export etmeyen modüller için: doğrudan submodule'den 'account' çöz
    account: Any = getattr(execution, "account", None)
    if account is None:
        try:
            acc_mod = import_module(f"app.exchanges.{exchange_name}.account")
            account = getattr(acc_mod, "account", None)
        except (ModuleNotFoundError, ImportError, AttributeError) as e:
            logger.debug("[uPnL diag] account submodule resolve failed: %s", e)
            account = None
    has_fun = bool(account) and hasattr(account, "get_unrealized")
    logger.debug(
        "[uPnL diag] account=%s | has_get_unrealized=%s | pos_mode=%s",
        type(account).__name__ if account else None,
        has_fun,
        getattr(getattr(execution, "order_handler", None), "POSITION_MODE", None),
    )
    if not has_fun:
        return 0

    # Toplu veri: {"positions":[...]} veya doğrudan liste [...]
    sym_total: dict[str, Decimal] = {}
    try:
        all_res = await account.get_unrealized(symbol=None, return_all=True)
        logger.debug(
            "[uPnL diag] bulk=%s", _desc(all_res) if all_res is not None else "None"
        )

        if isinstance(all_res, list):
            for it in all_res:
                if not isinstance(it, dict):
                    continue
                sym = str(
                    it.get("symbol") or it.get("s") or it.get("symbolName") or ""
                ).upper()
                if not sym:
                    continue
                # Binance/adapter'ların çoğunda 'unRealizedProfit' var; normalize edilmişlerde 'unrealized' olabilir
                val = (
                    it.get("unRealizedProfit")
                    or it.get("unrealized")
                    or it.get("pnl")
                    or it.get("pnlValue")
                    or 0
                )
                sym_total[sym] = sym_total.get(sym, Decimal("0")) + _to_dec(val)
        elif isinstance(all_res, dict) and isinstance(all_res.get("positions"), list):
            for it in all_res["positions"]:
                if not isinstance(it, dict):
                    continue
                sym = str(it.get("symbol") or "").upper()
                if not sym:
                    continue
                val = (
                    it.get("unRealizedProfit")
                    or it.get("unrealized")
                    or it.get("pnl")
                    or 0
                )
                sym_total[sym] = sym_total.get(sym, Decimal("0")) + _to_dec(val)
    except (httpx.HTTPError, asyncio.TimeoutError, ValueError, TypeError) as e:
        logger.warning("[uPnL diag] bulk get_unrealized failed: %s", e)
        pass

    pos_mode = getattr(
        getattr(execution, "order_handler", None), "POSITION_MODE", "one_way"
    )
    updated = 0  # değeri gerçekten değişen satır sayısı
    touched = (
        0  # borsadan veri çekilip satıra yazılan (last_checked_at dahil) satır sayısı
    )
    now = datetime.now(timezone.utc)

    for r in rows:
        sym = str(r.symbol).upper()

        if str(pos_mode).lower() == "hedge":
            # Bacak bazında çıktı: liste veya {"positions":[...]} olabilir → normalize et
            try:
                legs_raw = await account.get_unrealized(symbol=sym, return_all=True)
                logger.info("[uPnL diag] legs for %s → %s", sym, _desc(legs_raw))
            except (httpx.HTTPError, asyncio.TimeoutError, ValueError, TypeError) as e:
                logger.warning("[uPnL diag] per-symbol legs failed (%s): %s", sym, e)
                continue

            if isinstance(legs_raw, dict) and isinstance(
                legs_raw.get("positions"), list
            ):
                legs = legs_raw["positions"]
            elif isinstance(legs_raw, list):
                legs = legs_raw
            elif isinstance(legs_raw, dict) and (
                "LONG" in legs_raw or "SHORT" in legs_raw or "BOTH" in legs_raw
            ):
                # nadir: {"LONG": n, "SHORT": m} gibi
                legs = [
                    {"positionSide": k, "unRealizedProfit": v}
                    for k, v in legs_raw.items()
                ]
            else:
                continue

            leg_map = {
                str(it.get("positionSide") or "").upper(): _to_dec(
                    it.get("unRealizedProfit", 0)
                )
                for it in legs
                if isinstance(it, dict)
            }

            new_val = (
                leg_map.get("LONG")
                if (r.side or "").lower() == "long"
                else leg_map.get("SHORT")
            )
            if new_val is None:
                # bazı adapter'lar hedge'de 'BOTH' döndürebilir; onu da kabul et
                both = leg_map.get("BOTH")
                if both is None:
                    # hiçbir bacak yoksa toplam yaz (son çare)
                    new_val = sum(leg_map.values(), Decimal("0"))
                else:
                    new_val = both
        else:
            # one_way: toplam tek satır
            if sym not in sym_total:
                try:
                    one = await account.get_unrealized(symbol=sym, return_all=True)
                    logger.warning("[uPnL diag] one for %s → %s", sym, _desc(one))
                except (
                    httpx.HTTPError,
                    asyncio.TimeoutError,
                    ValueError,
                    TypeError,
                ) as e:
                    logger.exception(
                        "[uPnL diag] per-symbol one failed (%s): %s", sym, e
                    )
                    continue

                if isinstance(one, list):
                    tot = sum(
                        _to_dec(it.get("unRealizedProfit", 0))
                        for it in one
                        if isinstance(it, dict)
                    )
                elif isinstance(one, dict):
                    tot = _to_dec(one.get("unrealized", 0))
                else:
                    tot = Decimal("0")
                sym_total[sym] = tot
            new_val = sym_total.get(sym, Decimal("0"))

        prev = r.unrealized_pnl
        try:
            r.unrealized_pnl = _to_dec(new_val)
            r.last_checked_at = now
            touched += 1
        except (InvalidOperation, TypeError, ValueError):
            continue

        if prev != r.unrealized_pnl:
            updated += 1

    if touched:
        await db.flush()
        await db.commit()

    # Bilgi logu (her tur): kaç satır var, kaçına dokunduk, kaçı değişti; sembol eşleşmesi için kısa liste
    db_syms = sorted({str(r.symbol).upper() for r in rows})
    bulk_syms = sorted(sym_total.keys())
    logger.info(
        "[uPnL] %s → open=%d | touched=%d | updated=%d | bulk_syms=%d | db=%s | bulk=%s",
        exchange_name,
        len(rows),
        touched,
        updated,
        len(bulk_syms),
        ",".join(db_syms[:5]) or "-",
        ",".join(bulk_syms[:5]) or "-",
    )
    return updated
