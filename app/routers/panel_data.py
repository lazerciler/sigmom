#!/usr/bin/env python3
# app/routers/panel_data.py
# Python 3.9

from decimal import Decimal, InvalidOperation
import asyncio
import httpx
from typing import Dict, Any, Tuple, List, Optional, Literal, Sequence
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from app.config import settings
from app.utils.exchange_loader import load_execution_module
import importlib
import inspect
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import StrategyOpenTrade, StrategyTrade, RawSignal

router = APIRouter(prefix="/api/me", tags=["me"])


def _to_dec(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


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
    position_size_text: Optional[str] = None
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
    symbol: Optional[str] = Query(None, description="Tek sembol. Örn: BTCUSDT"),
    tf: str = Query(..., description="Timeframe: 1m,5m,15m,1h,4h,1d"),
    db: AsyncSession = Depends(get_db),
):
    """
    Borsa onaylı veriden marker üretir:
    - Hâlâ açık pozisyonlar:
    (strategy_open_trades.status='open') -> OPEN
    - Kapanmış işlemler:
    (strategy_trades) -> aynı open_trade_public_id için EN SON kapanış + eşleşen açılış -> OPEN+CLOSE
    """
    # --- sembol filtresi (tekil) ---
    sym_list: Optional[Sequence[str]] = None
    if symbol:
        sym_list = [symbol.strip().upper()]

    markers: List[Marker] = []
    bar_sec = TF_TO_SEC.get(tf)
    if not bar_sec:
        raise HTTPException(status_code=400, detail=f"Geçersiz tf: {tf}")

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
        tb = t - (t % bar_sec)
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
                time_bar=tb,  # her zaman dolu
                is_live=False,  # canlı muma pin yok
            )
        )

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
            tb0 = t0 - (t0 % bar_sec)
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
                    time_bar=tb0,
                    is_live=False,
                )
            )

        # CLOSE marker
        side_c = str(getattr(t, "side", "")).lower() if hasattr(t, "side") else ""
        is_long_c = side_c == "long"
        tc = _to_epoch(t.timestamp)
        tbc = tc - (tc % bar_sec)
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
                time_bar=tbc,
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
    import importlib

    q = (
        select(StrategyOpenTrade)
        .where(func.lower(StrategyOpenTrade.status) == "open")
        .order_by(StrategyOpenTrade.timestamp.desc())
    )
    if symbol:
        sym = symbol.strip().upper()
        q = q.where(func.upper(StrategyOpenTrade.symbol) == sym)
    rows = (await db.execute(q)).scalars().all()
    out: List[OpenTradeOut] = []
    for r in rows:
        pos_text: Optional[str] = None
        try:
            ex = (r.exchange or settings.DEFAULT_EXCHANGE).strip()
            utils = importlib.import_module(f"app.exchanges.{ex}.utils")
            # Tercih sırası: format_quantity_text (gösterim) → adjust_quantity (legacy)
            fn = getattr(utils, "format_quantity_text", None) or getattr(
                utils, "adjust_quantity", None
            )
            if fn:
                pos_text = (
                    await fn(r.symbol, float(r.position_size))
                    if inspect.iscoroutinefunction(fn)
                    else fn(r.symbol, float(r.position_size))
                )
        except (
            ImportError,
            AttributeError,
            ValueError,
            TypeError,
            httpx.HTTPError,
            asyncio.TimeoutError,
        ):
            pos_text = None

        out.append(
            OpenTradeOut(
                public_id=r.public_id,
                symbol=r.symbol,
                side=str(r.side).lower(),
                entry_price=_f(r.entry_price),
                position_size=_f(r.position_size),
                position_size_text=pos_text,
                leverage=int(r.leverage),
                exchange=r.exchange,
                order_type=r.order_type,
                timestamp=r.timestamp,
                exchange_order_id=getattr(r, "exchange_order_id", None),
                status=str(r.status),
            )
        )
    return out


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


# Bakiye (borsa-agnostik) — iş mantığı account.py’de
@router.get("/balance")
async def me_balance(
    exchange: str = Query(
        settings.DEFAULT_EXCHANGE,
        description=f"Varsayılan: {settings.DEFAULT_EXCHANGE} · Örn: binance_futures_testnet",
        example=settings.DEFAULT_EXCHANGE,  # /docs’ta tek örnek gösterir
    ),
    asset: Optional[str] = Query(None, description="USDT, USDC, FDUSD, BTC..."),
    symbol: Optional[str] = Query(
        None, description="BTCUSDT, ETHBTC, ETHBTC.P, ETH/BTC, BTCUSD_PERP ..."
    ),
    currency: Optional[str] = Query(
        None, description="Sinyal JSON 'currency' alanı (varsa öncelikli)"
    ),
    # all: bool = Query(False, description="Tüm bakiyeleri ham liste olarak döndür"),
    return_all: bool = Query(
        False,
        alias="all",  # URL'de ?all=true/1 kalır; Python tarafında return_all
        description="Tüm bakiyeleri ham liste olarak döndür (query key'i: all)",
    ),
):
    try:
        mod = importlib.import_module(f"app.exchanges.{exchange}.account")
        fn = getattr(mod, "get_available", None) or getattr(
            mod, "get_available_balance", None
        )
        if not callable(fn):
            raise RuntimeError(f"{exchange}.account içinde get_available(...) yok")
        if inspect.iscoroutinefunction(fn):
            return await fn(
                asset=asset, symbol=symbol, currency=currency, return_all=return_all
            )
        # Sync implementasyon varsa:
        return fn(asset=asset, symbol=symbol, currency=currency, return_all=return_all)
    # except Exception as e:
    #     raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        # UI akmaya devam etsin: güvenli sıfırlar döndür.
        return {"available": 0.0, "equity": 0.0}


def _normalize_upnl(raw: Any) -> Tuple[Decimal, Decimal, Decimal]:
    """
    raw -> (total, long, short)
    Kabul edilen olası şekiller:
      - sayı: toplam
      - {"unrealized": n, "legs": {"long": a, "short": b}}
      - {"long": a, "short": b}
      - [{"side": "LONG"/"SHORT", "unrealizedPnl" | "u_pnl" | "unrealized" | "pnl": v}, ...]
    """
    total = Decimal("0")
    long_amt = Decimal("0")
    short_amt = Decimal("0")

    if raw is None:
        return total, long_amt, short_amt

    # 1) Basit sayı
    if isinstance(raw, (int, float, str, Decimal)):
        total = _to_dec(raw)
        return total, long_amt, short_amt

    # 2) Sözlük
    if isinstance(raw, dict):
        # {"unrealized": n, "legs": {...}}
        if "unrealized" in raw:
            total = _to_dec(raw.get("unrealized"))
            legs = raw.get("legs") or {}
            if isinstance(legs, dict):
                long_amt = _to_dec(legs.get("long", 0))
                short_amt = _to_dec(legs.get("short", 0))
            else:
                # bazen doğrudan {"long":..,"short":..} da gelebilir
                long_amt = _to_dec(raw.get("long", 0))
                short_amt = _to_dec(raw.get("short", 0))

            # Positions / rows vb. listeden L/S yeniden hesapla
            items = None
            for _k in ("positions", "data", "rows", "items"):
                _v = raw.get(_k)
                if isinstance(_v, list):
                    items = _v
                    break
            if items:
                ll = Decimal("0")
                ss = Decimal("0")
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    side = str(
                        it.get("side")
                        or it.get("positionSide")
                        or it.get("posSide")
                        or it.get("ps")
                        or ""
                    ).lower()
                    v = (
                        it.get("unrealizedPnl")
                        or it.get("unRealizedProfit")
                        or it.get("u_pnl")
                        or it.get("unrealized")
                        or it.get("upnl")
                        or it.get("pnl")
                        or 0
                    )
                    dv = _to_dec(v)
                    if side.startswith("long") or side == "l":
                        ll += dv
                    elif side.startswith("short") or side == "s":
                        ss += dv

                # Listeden gelen veri tutarlıysa legs'i komple güncelle
                if ll != 0 or ss != 0:
                    long_amt, short_amt = ll, ss
                    total = long_amt + short_amt

            if not (long_amt or short_amt):
                # fallback: ayrı anahtar yoksa, total’ı tek bacak varsay
                long_amt = total
            return total, long_amt, short_amt

        # {"long": a, "short": b}
        if ("long" in raw) or ("short" in raw):
            long_amt = _to_dec(raw.get("long", 0))
            short_amt = _to_dec(raw.get("short", 0))
            total = long_amt + short_amt
            return total, long_amt, short_amt

        # {"positions":[...]} benzeri → sadece **liste** olan key’i al
        items = None
        for _k in ("positions", "data", "rows", "items"):
            _v = raw.get(_k)
            if isinstance(_v, list):
                items = _v
                break
        raw = items if items is not None else raw  # liste yoksa aynen devam

    # 3) Liste
    if isinstance(raw, list):
        for it in raw:
            if not isinstance(it, dict):
                total += _to_dec(it)
                continue
            side = str(
                it.get("side")
                or it.get("positionSide")
                or it.get("posSide")
                or it.get("ps")
                or ""
            ).lower()
            # Değer: 'unRealizedProfit' dahil yaygın alias'ları tara
            v = (
                it.get("unrealizedPnl")
                or it.get("unRealizedProfit")
                or it.get("u_pnl")
                or it.get("unrealized")
                or it.get("upnl")
                or it.get("pnl")
                or 0
            )

            dv = _to_dec(v)
            total += dv
            if side.startswith("long"):
                long_amt += dv
            elif side.startswith("short"):
                short_amt += dv
        # return total, long_amt, short_amt
        # one_way/BOTH: yön ayrımı yoksa toplamı LONG kabul et
        if long_amt == 0 and short_amt == 0 and total != 0:
            long_amt = total
        return total, long_amt, short_amt

    # tanınmayan şekil → sadece toplamı almaya çalış
    return _to_dec(raw), long_amt, short_amt


@router.get("/unrealized")
async def me_unrealized(
    exchange: str = Query(settings.DEFAULT_EXCHANGE),
    symbol: Optional[str] = Query(None),
    return_all: bool = Query(
        False,
        alias="all",
        description="Ham çıktıyı döndür (debug). Varsayılan: normalize + legs breakdown.",
    ),
):
    """
    Döndürür:
      {
        "unrealized": <float>,                 # toplam (L+S)
        "legs": {"long": <float>, "short": <float>},
        "mode": "one_way" | "hedge"
      }
    ?all=1 verilirse borsa modülünün ham çıktısı aynen döner.
    """
    try:
        mod = importlib.import_module(f"app.exchanges.{exchange}.account")
        fn = getattr(mod, "get_unrealized", None)
        if not callable(fn):
            raise RuntimeError(f"{exchange}.account içinde get_unrealized(...) yok")

        if inspect.iscoroutinefunction(fn):
            raw = await fn(symbol=symbol, return_all=return_all)
        else:
            raw = fn(symbol=symbol, return_all=return_all)

        if return_all:
            return raw

        total, long_amt, short_amt = _normalize_upnl(raw)
        # moddan pozisyon modu (varsa) oku; yoksa varsayılan
        try:
            ex = load_execution_module(exchange)
            mode = getattr(
                getattr(ex, "order_handler", None), "POSITION_MODE", "one_way"
            )
        # except Exception:
        except (ImportError, AttributeError):
            mode = "one_way" if (short_amt == 0) else "hedge"  # kaba tahmin

        # one_way/BOTH: legs 0 ise toplamı LONG’a yaz
        if str(mode) == "one_way" and long_amt == 0 and short_amt == 0 and total != 0:
            long_amt = total

        return {
            "unrealized": float(total),
            "legs": {"long": float(long_amt), "short": float(short_amt)},
            "mode": mode,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------- Net PnL (borsa-onaylı) ---------------------------
# @router.get("/netpnl")
# async def me_netpnl(
#     exchange: str = Query(settings.DEFAULT_EXCHANGE),
#     symbol: Optional[str] = Query(None),
#     since_days: Optional[int] = Query(None, ge=1, le=3650),
#     since_epoch: Optional[int] = Query(None, description="Unix saniye"),
#     db: AsyncSession = Depends(get_db),
# ):
@router.get("/netpnl")
async def me_netpnl(
    exchange: str = Query(settings.DEFAULT_EXCHANGE),
    symbol: Optional[str] = Query(None),
    since_days: Optional[int] = Query(None, ge=1, le=3650),
    since_epoch: Optional[int] = Query(None, description="Unix saniye"),
    detail: bool = Query(False, description="Komisyon/funding ayrıntılarını da döndür"),
    db: AsyncSession = Depends(get_db),
):

    ex = exchange
    sym = symbol.upper() if symbol else None
    now = datetime.now(timezone.utc)

    # 1) Zaman penceresi: parametre varsa öncelik ver
    # since_dt: Optional[datetime] = None
    # if since_epoch is not None:
    # since_dt başlangıç atamasını kaldır (F841 susturulur)
    if since_epoch is not None:
        since_dt = datetime.fromtimestamp(int(since_epoch), tz=timezone.utc)
    elif since_days is not None:
        since_dt = now - timedelta(days=int(since_days))
    else:
        # 2) Aksi halde DB'deki İLK işlem zamanını bul (closed ve open tablolarından min)
        q_closed = select(func.min(StrategyTrade.timestamp)).where(
            StrategyTrade.exchange == ex
        )
        q_opened = select(func.min(StrategyOpenTrade.timestamp)).where(
            StrategyOpenTrade.exchange == ex
        )
        if sym:
            q_closed = q_closed.where(func.upper(StrategyTrade.symbol) == sym)
            q_opened = q_opened.where(func.upper(StrategyOpenTrade.symbol) == sym)

        t_closed = (await db.execute(q_closed)).scalar()
        t_opened = (await db.execute(q_opened)).scalar()
        since_dt = min([t for t in (t_closed, t_opened) if t], default=None)

    # Hiç işlem yoksa 0 dön (fallback)
    if since_dt is None:
        return {
            "net": 0.0,
            "window": {"since": None, "until": now.isoformat()},
            "exchange": ex,
            "symbol": sym,
            "source": "exchange-income",
        }

    try:

        def _norm_keys(d: dict) -> dict:
            normed = {}
            for k, v in (d or {}).items():
                kk = str(k).lower().strip()
                # incomeType normalizasyonu (kanonik anahtarlar: commission, funding, realized)
                if kk in (
                    "commission",
                    "fees",
                    "fee",
                    "trading_fee",
                    "makercommission",
                    "takercommission",
                    "maker_commission",
                    "taker_commission",
                ):
                    key = "commission"
                elif kk in ("funding", "funding_fee", "fundingfee"):
                    key = "funding"
                elif kk in ("realized", "realized_pnl", "trade_pnl", "realizedpnl"):
                    key = "realized"
                else:
                    key = kk
                try:
                    normed[key] = float(v or 0.0)
                except (ValueError, TypeError):
                    normed[key] = 0.0
            return normed

        total_val: float = 0.0
        breakdown: Optional[dict] = None

        # 3a) account.income_breakdown / income_summary
        acc = importlib.import_module(f"app.exchanges.{ex}.account")
        # a1) breakdown varsa onu kullan (detail istenmişse)
        if (
            detail
            and hasattr(acc, "income_breakdown")
            and callable(getattr(acc, "income_breakdown"))
        ):
            fn_bd = getattr(acc, "income_breakdown")
            res = (
                await fn_bd(symbol=sym, since=since_dt, until=None)
                if inspect.iscoroutinefunction(fn_bd)
                else fn_bd(symbol=sym, since=since_dt, until=None)
            )
            if isinstance(res, dict) and ("total" in res or "breakdown" in res):
                total_val = float(res.get("total", 0.0) or 0.0)
                breakdown = (
                    res.get("breakdown") or res.get("types") or res.get("detail")
                )
            elif isinstance(res, (list, tuple)) and len(res) >= 2:
                total_val = float(res[0] or 0.0)
                breakdown = res[1]
            elif isinstance(res, dict):
                breakdown = res
                total_val = float(sum(float(x or 0.0) for x in res.values()))

        # a2) hâlâ yoksa summary dene
        if breakdown is None:
            fn_sum = getattr(acc, "income_summary", None)
            if callable(fn_sum):
                res = (
                    await fn_sum(symbol=sym, since=since_dt, until=None)
                    if inspect.iscoroutinefunction(fn_sum)
                    else fn_sum(symbol=sym, since=since_dt, until=None)
                )
                if isinstance(res, dict) and ("total" in res or "breakdown" in res):
                    total_val = float(res.get("total", 0.0) or 0.0)
                    breakdown = res.get("breakdown") or res.get("types")
                elif isinstance(res, (list, tuple)) and len(res) >= 2:
                    total_val = float(res[0] or 0.0)
                    breakdown = res[1]
                else:
                    # sadece toplam (float) dönmüş olabilir
                    # try:
                    #     total_val = float(res or 0.0)
                    # except Exception:
                    #     total_val = 0.0
                    try:
                        total_val = float(res or 0.0)
                    except (ValueError, TypeError):
                        total_val = 0.0
        # 3b) order_handler.income_summary (start_ms/end_ms) → sum ile breakdown veriyor
        if detail and breakdown is None:
            try:
                oh = importlib.import_module(f"app.exchanges.{ex}.order_handler")
                oh_fn = getattr(oh, "income_summary", None)
                if callable(oh_fn):
                    start_ms = int(since_dt.timestamp() * 1000)
                    end_ms = int(now.timestamp() * 1000)
                    res = (
                        await oh_fn(start_ms=start_ms, end_ms=end_ms, symbol=sym)
                        if inspect.iscoroutinefunction(oh_fn)
                        else oh_fn(start_ms=start_ms, end_ms=end_ms, symbol=sym)
                    )
                    # Beklenen: {"success": True, "net": x, "sum": {...}}
                    if isinstance(res, dict):
                        if "net" in res:
                            total_val = float(res.get("net") or 0.0)
                        if "sum" in res and isinstance(res["sum"], dict):
                            breakdown = res["sum"]
            except ImportError:
                pass

        # Çıktıyı hazırla
        out = {
            "net": float(total_val or 0.0),
            "window": {"since": since_dt.isoformat(), "until": now.isoformat()},
            "exchange": ex,
            "symbol": sym,
            "source": "exchange-income",
        }
        if detail and breakdown:
            out["breakdown"] = _norm_keys(breakdown)
        return out
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
