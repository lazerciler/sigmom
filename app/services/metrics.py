#!/usr/bin/env python3
# app/services/metrics.py
# Python 3.9

"""Utility helpers for market metrics such as moving averages.

This module centralises the calculation logic for SMA/EMA overlays and
MA confluence percentages so that it can be re-used by different routers
or background tasks without duplicating the implementation in the
front-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Mapping, MutableMapping, Optional, Sequence

Number = Optional[float]


def _to_seconds(timestamp: Number) -> Optional[int]:
    """Return the timestamp in seconds if it looks like a Unix time in ms."""
    if timestamp is None:
        return None
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return None
    if ts_int > 10**12:
        return ts_int // 1000
    if ts_int > 10**10:
        # larger than year ~2286; still treat as seconds to be safe
        return ts_int // 1000
    return ts_int


def simple_moving_average(
    values: Sequence[float], period: int
) -> List[Optional[float]]:
    """Compute the simple moving average for the given period."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    window_sum = 0.0
    for idx, value in enumerate(values):
        window_sum += value
        if idx >= period:
            window_sum -= values[idx - period]
        if idx >= period - 1:
            out[idx] = window_sum / period
    return out


def exponential_moving_average(
    values: Sequence[float], period: int
) -> List[Optional[float]]:
    """Compute the exponential moving average for the given period."""
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    multiplier = 2 / (period + 1)
    prev: Optional[float] = None
    for idx, value in enumerate(values):
        if idx == period - 1:
            prev = sum(values[:period]) / period
            out[idx] = prev
        elif idx >= period and prev is not None:
            prev = value * multiplier + prev * (1 - multiplier)
            out[idx] = prev
    return out


def _build_overlay_series(
    times: Sequence[int],
    values: Sequence[Optional[float]],
) -> List[Dict[str, float]]:
    series: List[Dict[str, float]] = []
    for idx, value in enumerate(values):
        if value is None:
            continue
        ts = times[idx]
        series.append({"time": ts, "value": float(value)})
    return series


def _closeness_pct(a: Number, b: Number, price: Number, tolerance_pct: float) -> float:
    if a is None or b is None or price is None:
        return 0.0
    if not all(isinstance(x, (float, int)) for x in (a, b, price)):
        return 0.0
    price_val = float(price)
    if price_val <= 0:
        return 0.0
    diff_pct = abs(float(a) - float(b)) / price_val * 100
    if tolerance_pct <= 0:
        return 0.0
    closeness = 100 * (1 - diff_pct / tolerance_pct)
    if closeness < 0:
        return 0.0
    if closeness > 100:
        return 100.0
    return closeness


@dataclass
class OverlayConfig:
    sma: Sequence[int]
    ema: Sequence[int]


@dataclass
class MovingAverageMetrics:
    ma_overlays: Dict[str, List[Dict[str, float]]]
    ma_confluence: Dict[str, object]


DEFAULT_TOLERANCE_PCT = 1.5


def generate_ma_metrics(
    klines: Sequence[Mapping[str, object]],
    config: OverlayConfig,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> MovingAverageMetrics:
    if not klines:
        return MovingAverageMetrics(ma_overlays={}, ma_confluence={})

    usable_klines = list(klines)
    if len(usable_klines) > 1:
        usable_klines = usable_klines[:-1]

    if not usable_klines:
        return MovingAverageMetrics(ma_overlays={}, ma_confluence={})

    closes: List[float] = [float(k.get("c", 0.0)) for k in usable_klines]
    times: List[int] = []
    for idx, kline in enumerate(usable_klines):
        ts = _to_seconds(kline.get("time"))
        if ts is None:
            ts = _to_seconds(kline.get("t"))
        if ts is None:
            ts = idx
        times.append(int(ts))

    overlays: MutableMapping[str, List[Dict[str, float]]] = {}
    overlay_values: List[Dict[str, object]] = []

    for period in sorted(set(int(p) for p in config.sma if int(p) > 0)):
        values = simple_moving_average(closes, period)
        key = f"SMA{period}"
        overlays[key] = _build_overlay_series(times, values)
        overlay_values.append(
            {
                "key": key,
                "label": f"SMA{period}",
                "values": values,
            }
        )

    for period in sorted(set(int(p) for p in config.ema if int(p) > 0)):
        values = exponential_moving_average(closes, period)
        key = f"EMA{period}"
        overlays[key] = _build_overlay_series(times, values)
        overlay_values.append(
            {
                "key": key,
                "label": f"EMA{period}",
                "values": values,
            }
        )

    last_price: Optional[float] = None
    if closes:
        last_price = closes[-1]

    labels: List[str] = []
    values_out: List[float] = []
    pairs: List[Dict[str, object]] = []

    for left, right in combinations(overlay_values, 2):
        left_val = left["values"][-1] if left["values"] else None
        right_val = right["values"][-1] if right["values"] else None
        closeness = _closeness_pct(left_val, right_val, last_price, tolerance_pct)
        label = f"{left['label']}↔{right['label']}"
        labels.append(label)
        values_out.append(closeness)
        pairs.append(
            {
                "key": f"{left['key']}|{right['key']}",
                "label": label,
                "value": closeness,
            }
        )

    latest_time = times[-1] if times else None
    confluence = {
        "labels": labels,
        "values": values_out,
        "pairs": pairs,
        "time": latest_time,
        "price": last_price,
    }

    return MovingAverageMetrics(ma_overlays=dict(overlays), ma_confluence=confluence)
