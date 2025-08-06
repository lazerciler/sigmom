#!/usr/bin/env python3
# app/utils/position_utils.py

from decimal import Decimal


def position_matches(
    open_trade, position: dict, price_tolerance: Decimal = Decimal("0.5")
) -> bool:
    """
    open_trade: DB'deki StrategyOpenTrade örneği
    position: exchange.get_position(...) cevabı (normalize edilmiş dict)
    price_tolerance: entry_price toleransı
    """

    # Normalize exchange dönen key’lerini tek bir forma getir:
    amt = Decimal(str(position.get("positionAmt", position.get("size", 0))))
    entry = Decimal(str(position.get("entryPrice", 0)))
    side = position.get("positionSide", position.get("side", "")).lower()

    # 3 kriter
    size_ok = amt == open_trade.position_size
    side_ok = side == open_trade.side.lower()
    price_ok = abs(entry - open_trade.entry_price) <= price_tolerance

    return size_ok and side_ok and price_ok
