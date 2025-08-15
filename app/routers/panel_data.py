# app/routers/panel_data.py — PUBLIC görünürlük (tüm veriler)
from typing import Dict, List, Optional, Literal, Sequence
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StrategyOpenTrade, StrategyTrade, RawSignal

router = APIRouter(prefix="/api/me", tags=["me"])


# ---------- Yardımcılar ----------
def _to_epoch(dt: Optional[datetime]) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _f(x):
    return None if x is None else float(x)


TF_TO_SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


# ---------- Schemas ----------
class Marker(BaseModel):
    symbol: str
    time: int
    position: Literal["aboveBar", "belowBar"]
    text: str
    price: Optional[float] = None
    id: str
    kind: Literal["open", "close"]
    side: Optional[Literal["long", "short"]] = None
    time_bar: Optional[int] = None
    is_live: Optional[bool] = None


class OpenTradeOut(BaseModel):
    public_id: str
    symbol: str
    side: Literal["long", "short"]
    entry_price: float
    position_size: float
    leverage: int
    exchange: str
    order_type: str
    timestamp: datetime
    exchange_order_id: Optional[str] = None
    status: str


class TradeOut(BaseModel):
    public_id: str
    symbol: str
    side: Literal["long", "short"]
    entry_price: float
    exit_price: float
    position_size: float
    leverage: int
    realized_pnl: float
    exchange: str
    order_type: str
    timestamp: datetime
    open_trade_public_id: str


class RawSignalLite(BaseModel):
    id: int
    received_at: datetime
    symbol: Optional[str] = None
    side: Optional[str] = None
    mode: Optional[str] = None


# ---------- Endpoints (PUBLIC) ----------
@router.get("/symbols")
async def symbols_public(
    db: AsyncSession = Depends(get_db),
):
    q1 = select(func.distinct(StrategyOpenTrade.symbol))
    q2 = select(func.distinct(StrategyTrade.symbol))
    s1 = [r[0] for r in (await db.execute(q1)).all() if r[0]]
    s2 = [r[0] for r in (await db.execute(q2)).all() if r[0]]
    return {"symbols": sorted({*s1, *s2})}


@router.get("/markers", response_model=List[Marker])
async def markers_public(
    symbols: Optional[str] = Query(
        None, description="Virgülle ayrılmış semboller (örn: BTCUSDT,ETHUSDT)"
    ),
    tf: Optional[str] = Query(None, description="Timeframe: 1m,5m,15m,1h,4h,1d"),
    db: AsyncSession = Depends(get_db),
):
    """
    Borsa onaylı veriden marker üretir:
    - Hâlâ açık pozisyonlar (strategy_open_trades.status='open') -> OPEN
    - Kapanmış işlemler (strategy_trades) -> aynı open_trade_public_id için EN SON kapanış + eşleşen açılış -> OPEN+CLOSE
    """
    # --- sembol filtresi ---
    sym_list: Optional[Sequence[str]] = None
    if symbols:
        sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    markers: List[Marker] = []
    bar_sec = TF_TO_SEC.get(tf) if tf else None

    # === 1) Hâlâ açık pozisyonlar -> OPEN ===
    q_open = select(StrategyOpenTrade).where(
        func.lower(StrategyOpenTrade.status) == "open"
    )
    if sym_list:
        q_open = q_open.where(func.upper(StrategyOpenTrade.symbol).in_(sym_list))
    open_rows = (await db.execute(q_open)).scalars().all()

    for r in open_rows:
        side = str(getattr(r, "side", "")).lower() if hasattr(r, "side") else ""
        is_long = side == "long"
        pos = "belowBar" if is_long else "aboveBar"
        t = _to_epoch(r.timestamp)
        tb = (t - (t % bar_sec)) if bar_sec else t
        markers.append(
            Marker(
                symbol=str(r.symbol),
                time=tb,
                position=pos,
                text="OPEN LONG" if is_long else "OPEN SHORT",
                price=_f(getattr(r, "entry_price", None)),
                id=str(r.public_id),
                kind="open",
                side=(
                    ("long" if is_long else "short")
                    if side in ("long", "short")
                    else None
                ),
                time_bar=tb if bar_sec else None,
                is_live=True,
            )
        )

    # for r in open_rows:
    #     side = (str(getattr(r, "side", "")).lower() if hasattr(r, "side") else "")
    #     is_long = side == "long"
    #     pos = "belowBar" if is_long else "aboveBar"
    #
    #     t = _to_epoch(r.timestamp)  # Zaten UTC timestamp dönüyor
    #
    #     if bar_sec:  # Sadece timeframe varsa hizala
    #         # UTC zamanını timeframe'e göre yuvarla (yerel saat dilimini etkilemeden)
    #         tb = (t // bar_sec) * bar_sec
    #     else:
    #         tb = t
    #
    #     markers.append(Marker(
    #         symbol=str(r.symbol),
    #         time=tb,  # Düzeltilmiş zaman
    #         position=pos,
    #         text="OPEN LONG" if is_long else "OPEN SHORT",
    #         price=_f(getattr(r, "entry_price", None)),
    #         id=str(r.public_id),
    #         kind="open",
    #         side=("long" if is_long else "short") if side in ("long", "short") else None,
    #         time_bar=tb if bar_sec else None,
    #         is_live=True,
    #     ))

    # === 2) Kapanmış işlemler -> son CLOSE + karşılığı OPEN ===
    q_tr = select(StrategyTrade)
    if sym_list:
        q_tr = q_tr.where(func.upper(StrategyTrade.symbol).in_(sym_list))
    tr_rows = (await db.execute(q_tr)).scalars().all()

    # aynı open_trade_public_id için EN SON kapanış
    latest_by_open: Dict[str, StrategyTrade] = {}
    for t in sorted(tr_rows, key=lambda x: x.timestamp, reverse=True):
        key = getattr(t, "open_trade_public_id", None)
        if not key:
            key = f"__{t.public_id}__"  # eşleşmeyen edge case
        if key not in latest_by_open:
            latest_by_open[key] = t

    # karşılık gelen açılış kayıtlarını getir
    open_ids = [k for k in latest_by_open.keys() if not k.startswith("__")]
    sot_map: Dict[str, StrategyOpenTrade] = {}
    if open_ids:
        q_sot = select(StrategyOpenTrade).where(
            StrategyOpenTrade.public_id.in_(open_ids)
        )
        if sym_list:
            q_sot = q_sot.where(func.upper(StrategyOpenTrade.symbol).in_(sym_list))
        for sot in (await db.execute(q_sot)).scalars().all():
            sot_map[str(sot.public_id)] = sot

    for key, t in latest_by_open.items():
        # OPEN marker (kapanmış işlem için de OPEN görünür kalsın diye)
        sot = sot_map.get(key)
        if sot:
            side_o = (
                str(getattr(sot, "side", "")).lower() if hasattr(sot, "side") else ""
            )
            is_long_o = side_o == "long"
            pos = "belowBar" if is_long_o else "aboveBar"
            t0 = _to_epoch(sot.timestamp)
            tb0 = (t0 - (t0 % bar_sec)) if bar_sec else t0
            markers.append(
                Marker(
                    symbol=str(sot.symbol),
                    time=tb0,
                    position=pos,
                    text="OPEN LONG" if is_long_o else "OPEN SHORT",
                    price=_f(getattr(sot, "entry_price", None)),
                    id=f"{t.public_id}:open",
                    kind="open",
                    side=(
                        ("long" if is_long_o else "short")
                        if side_o in ("long", "short")
                        else None
                    ),
                    time_bar=tb0 if bar_sec else None,
                    is_live=False,
                )
            )

        # CLOSE marker
        side_c = str(getattr(t, "side", "")).lower() if hasattr(t, "side") else ""
        is_long_c = side_c == "long"
        tc = _to_epoch(t.timestamp)
        tbc = (tc - (tc % bar_sec)) if bar_sec else tc
        markers.append(
            Marker(
                symbol=str(t.symbol),
                time=tbc,
                position=("aboveBar" if is_long_c else "belowBar"),
                text="CLOSE",
                price=_f(getattr(t, "exit_price", None)),
                id=str(t.public_id),
                kind="close",
                side=(
                    ("long" if is_long_c else "short")
                    if side_c in ("long", "short")
                    else None
                ),
                time_bar=tbc if bar_sec else None,
            )
        )

    # sırala ve dön
    markers.sort(key=lambda m: (m.time, 0 if m.kind == "open" else 1, m.symbol, m.id))
    return markers


@router.get("/open-trades", response_model=List[OpenTradeOut])
async def open_trades_public(
    symbol: Optional[str] = Query(None, min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(StrategyOpenTrade)
        .where(func.lower(StrategyOpenTrade.status) == "open")
        .order_by(StrategyOpenTrade.timestamp.desc())
    )
    if symbol:
        q = q.where(StrategyOpenTrade.symbol == symbol)

    rows = (await db.execute(q)).scalars().all()
    return [
        OpenTradeOut(
            public_id=r.public_id,
            symbol=r.symbol,
            side=str(r.side).lower(),
            entry_price=_f(r.entry_price),
            position_size=_f(r.position_size),
            leverage=int(r.leverage),
            exchange=r.exchange,
            order_type=r.order_type,
            timestamp=r.timestamp,
            exchange_order_id=getattr(r, "exchange_order_id", None),
            status=str(r.status),
        )
        for r in rows
    ]


@router.get("/recent-trades", response_model=List[TradeOut])
async def recent_trades_public(
    symbol: Optional[str] = Query(None, min_length=1, max_length=64),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    q = select(StrategyTrade).order_by(StrategyTrade.timestamp.desc()).limit(limit)
    if symbol:
        q = q.where(StrategyTrade.symbol == symbol)

    rows = (await db.execute(q)).scalars().all()
    return [
        TradeOut(
            public_id=t.public_id,
            symbol=t.symbol,
            side=str(t.side).lower(),
            entry_price=_f(t.entry_price),
            exit_price=_f(t.exit_price),
            position_size=_f(t.position_size),
            leverage=int(t.leverage),
            realized_pnl=_f(t.realized_pnl),
            exchange=t.exchange,
            order_type=t.order_type,
            timestamp=t.timestamp,
            open_trade_public_id=t.open_trade_public_id,
        )
        for t in rows
    ]


@router.get("/signals", response_model=List[RawSignalLite])
async def raw_signals_public(
    symbol: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    q = select(RawSignal).order_by(RawSignal.received_at.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()

    out: List[RawSignalLite] = []
    for r in rows:
        pl = r.payload or {}
        sym = (pl.get("symbol") or "").strip()
        if symbol and sym != symbol:
            continue
        out.append(
            RawSignalLite(
                id=int(r.id),
                received_at=r.received_at,
                symbol=sym or None,
                side=(pl.get("side") or None),
                mode=(pl.get("mode") or None),
            )
        )
    return out


@router.get("/overview")
async def overview_public(
    db: AsyncSession = Depends(get_db),
):
    # Açık pozisyon sayısı
    open_count = (
        await db.scalar(
            select(func.count())
            .select_from(StrategyOpenTrade)
            .where(func.lower(StrategyOpenTrade.status) == "open")
        )
        or 0
    )

    # Son ham sinyal zamanı
    last_sig = await db.scalar(select(func.max(RawSignal.received_at)))

    # 7 gün PnL (kapanan işlemlerden)
    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    pnl_7d = (
        await db.scalar(
            select(func.coalesce(func.sum(StrategyTrade.realized_pnl), 0.0)).where(
                StrategyTrade.timestamp >= since_7d
            )
        )
        or 0.0
    )

    # 30 gün winrate
    since_30d = now - timedelta(days=30)
    total_30 = (
        await db.scalar(
            select(func.count())
            .select_from(StrategyTrade)
            .where(StrategyTrade.timestamp >= since_30d)
        )
        or 0
    )
    wins_30 = (
        await db.scalar(
            select(func.count())
            .select_from(StrategyTrade)
            .where(StrategyTrade.timestamp >= since_30d)
            .where(StrategyTrade.realized_pnl > 0)
        )
        or 0
    )
    winrate_30d = (wins_30 / total_30 * 100.0) if total_30 else None

    if last_sig and last_sig.tzinfo is None:
        last_sig = last_sig.replace(tzinfo=timezone.utc)

    return {
        "pnl_7d": float(pnl_7d),
        "winrate_30d": round(winrate_30d, 2) if winrate_30d is not None else None,
        "open_trade_count": int(open_count),
        "max_dd_30d": None,
        "sharpe_30d": None,
        "last_signal_at": (
            last_sig.isoformat().replace("+00:00", "Z") if last_sig else None
        ),
    }
