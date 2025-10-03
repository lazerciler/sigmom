# tests/services/test_metrics.py
# Python 3.9

import math

from app.services.metrics import OverlayConfig, generate_ma_metrics


def _build_klines():
    base = 1_000_000_000_000
    data = []
    price = 100.0
    for i in range(10):
        ts = base + i * 60_000
        price += i
        data.append(
            {
                "t": ts,
                "time": ts // 1000,
                "o": price - 1,
                "h": price + 1,
                "l": price - 2,
                "c": price,
            }
        )
    return data


def test_generate_ma_metrics_returns_overlay_and_confluence():
    klines = _build_klines()
    config = OverlayConfig(sma=[3], ema=[4])

    metrics = generate_ma_metrics(klines, config, tolerance_pct=2.0)

    assert "SMA3" in metrics.ma_overlays
    sma_series = metrics.ma_overlays["SMA3"]
    # we drop the last bar for overlays → expect len-1 items once enough data
    assert sma_series[-1]["time"] == klines[-2]["time"]
    assert math.isclose(sma_series[-1]["value"], sum(k["c"] for k in klines[6:9]) / 3)

    ema_series = metrics.ma_overlays["EMA4"]
    assert ema_series[-1]["time"] == klines[-2]["time"]

    confluence = metrics.ma_confluence
    assert "labels" in confluence
    assert confluence["labels"] == ["SMA3↔EMA4"]
    assert len(confluence["values"]) == 1
    # Value should be bounded 0..100
    assert 0 <= confluence["values"][0] <= 100
    assert confluence["time"] == klines[-2]["time"]
