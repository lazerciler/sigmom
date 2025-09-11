#!/usr/bin/env python3
# app/routers/account.py
# Python 3.9

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional, List
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator, constr

from sqlalchemy.orm import Session
from pathlib import Path

# Projede mevcut olduğu varsayılan bağımlılıklar:
from app.dependencies.auth import get_current_user
from app.database import get_db  # get_db yolu farklıysa düzeltin
from fastapi import Request
from fastapi.responses import RedirectResponse

# API router'ınızdan AYRI bir page router açın
page_router = APIRouter()


@page_router.get("/account", include_in_schema=False)
def account_page(request: Request, user=Depends(get_current_user)):
    # Giriş kontrolü (isterseniz require_asil_user(user) ile Asil'e kilitleyebilirsiniz)
    if not user:
        return RedirectResponse("/auth/google/login", status_code=302)
    return templates.TemplateResponse(
        "account.html",
        {
            "request": request,
            "user": user,
            "referral_verified": getattr(user, "referral_verified", False),
        },
    )


# --- Modeller (SQLAlchemy) ---
# Aşağıdaki importları kendi model dosyanıza göre ayarlayın.
# from app.models import FundNav, UnitHoldings, UnitLocks, CashRequest, UserPayoutAddress

router = APIRouter(prefix="/api/account", tags=["account"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"  # app/templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

FUND_ID = 1
FEE_RATE = Decimal("0.03")  # platform gideri (%3)
EARLY_PENALTY = Decimal("0.03")  # erken çıkış ek kesinti (%3)
UNIT_Q = Decimal("0.00000001")  # units için 8 ondalık
USDT_Q = Decimal("0.01")  # para göstermek için (gerekirse 0.0001 yapın)


# ---------- Helpers ----------
def q_units(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(UNIT_Q, rounding=ROUND_HALF_UP)


def q_usdt(x: Decimal) -> Decimal:
    return (x or Decimal("0")).quantize(USDT_Q, rounding=ROUND_HALF_UP)


def require_asil_user(user):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Giriş yapın."
        )
    if not getattr(user, "referral_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Asil üyelik gerekli."
        )
    return user


def last_nav(db: Session) -> Decimal:
    # TODO: kendi FundNav modelinize göre uyarlayın
    # nav = db.execute(select(FundNav.nav).where(FundNav.fund_id==FUND_ID).order_by(FundNav.ts.desc())).scalars().first()
    nav = None
    return Decimal(nav) if nav else Decimal("1.00")


# ---------- Schemas ----------
class SummaryMy(BaseModel):
    units_total: Decimal
    units_locked: Decimal
    units_available: Decimal
    value_usdt: Decimal
    invested_usdt: Decimal
    withdrawn_usdt: Decimal
    pnl_abs: Decimal
    pnl_pct: Decimal

    class Config:
        json_encoders = {Decimal: lambda v: str(v)}


class SummaryOut(BaseModel):
    nav: Decimal
    my: SummaryMy

    class Config:
        json_encoders = {Decimal: lambda v: str(v)}


class PayoutAddressIn(BaseModel):
    kind: Literal["internal_binance", "onchain"]
    network: Optional[Literal["ERC20", "TRC20", "BEP20"]] = None
    identifier: constr(min_length=3, max_length=128)
    memo_tag: Optional[str] = None
    label: Optional[str] = None
    is_default: bool = False

    @validator("network")
    def network_required_for_onchain(cls, v, values):
        if values.get("kind") == "onchain" and not v:
            raise ValueError("On-chain için network zorunlu.")
        return v


class PayoutAddressOut(BaseModel):
    id: int
    kind: Literal["internal_binance", "onchain"]
    network: Optional[str]
    identifier: str
    memo_tag: Optional[str]
    is_default: bool
    label: Optional[str]
    verified_at: Optional[datetime]


class DepositRequestIn(BaseModel):
    amount: Decimal = Field(..., gt=0, description="USDT")


class WithdrawRequestIn(BaseModel):
    amount: Optional[Decimal] = Field(None, gt=0, description="USDT")
    units: Optional[Decimal] = Field(None, gt=0, description="Birim")

    @validator("units", always=True)
    def one_of_amount_or_units(cls, units, values):
        if not units and not values.get("amount"):
            raise ValueError("Tutar (USDT) veya birim giriniz.")
        return units


class HistoryItem(BaseModel):
    id: int
    type: Literal["DEPOSIT", "WITHDRAW", "WITHDRAW_EARLY"]
    amount: Decimal
    state: Literal["PENDING", "APPROVED", "SETTLED", "REJECTED"]
    requested_at: datetime
    approved_at: Optional[datetime]
    settled_at: Optional[datetime]

    class Config:
        json_encoders = {Decimal: lambda v: str(v)}


# ---------- Endpoints ----------
@router.get("/summary", response_model=SummaryOut)
def get_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    nav = last_nav(db)

    # TODO: kendi tablolarınıza göre aşağıdaki sorguları uyarlayın
    units_total = Decimal("0")
    units_locked = Decimal("0")
    invested = Decimal("0")
    withdrawn = Decimal("0")

    # örnek:
    # h = db.execute(select(UnitHoldings).where(UnitHoldings.user_id==user.id, UnitHoldings.fund_id==FUND_ID)).scalars().first()
    # if h:
    #     units_total = Decimal(h.units_total)
    #     units_locked = Decimal(h.units_locked)
    #
    # invested = Decimal(db.execute(
    #     select(func.coalesce(func.sum(CashRequest.amount), 0))
    #     .where(CashRequest.user_id==user.id, CashRequest.fund_id==FUND_ID,
    #            CashRequest.type=="DEPOSIT", CashRequest.state=="SETTLED")
    # ).scalar() or 0)
    # withdrawn = Decimal(db.execute(
    #     select(func.coalesce(func.sum(CashRequest.amount), 0))
    #     .where(CashRequest.user_id==user.id, CashRequest.fund_id==FUND_ID,
    #            CashRequest.type.in_(["WITHDRAW", "WITHDRAW_EARLY"]),
    #            CashRequest.state=="SETTLED")
    # ).scalar() or 0)

    units_avail = max(Decimal("0"), units_total - units_locked)
    value = q_usdt(units_total * nav)
    pnl_abs = q_usdt(value + withdrawn - invested)
    pnl_pct = q_usdt(Decimal("0") if invested == 0 else (pnl_abs / invested) * 100)

    return SummaryOut(
        nav=q_usdt(nav),
        my=SummaryMy(
            units_total=q_units(units_total),
            units_locked=q_units(units_locked),
            units_available=q_units(units_avail),
            value_usdt=value,
            invested_usdt=q_usdt(invested),
            withdrawn_usdt=q_usdt(withdrawn),
            pnl_abs=pnl_abs,
            pnl_pct=pnl_pct,
        ),
    )


@router.get("/lots")
def get_lots(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # TODO: UnitLocks tablosundan çekin ve aşağıdaki JSON’a benzer döndürün
    # locks = db.execute(select(UnitLocks).where(UnitLocks.user_id==user.id, UnitLocks.fund_id==FUND_ID).order_by(UnitLocks.created_at.desc())).scalars().all()
    demo = [
        {
            "id": 1,
            "units_initial": "800.00000000",
            "units_left": "800.00000000",
            "lock_end": (datetime.now(timezone.utc) + timedelta(days=12)).isoformat(),
            "status": "active",
        }
    ]
    return demo


@router.get("/history", response_model=List[HistoryItem])
def get_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # TODO: CashRequest tablosundan son kayıtlar
    # q = (select(CashRequest)
    #      .where(CashRequest.user_id==user.id, CashRequest.fund_id==FUND_ID)
    #      .order_by(desc(CashRequest.requested_at)).limit(limit))
    # rows = db.execute(q).scalars().all()
    # return [...]
    return []


# ------- Payout addresses -------
@router.get("/payout-addresses", response_model=List[PayoutAddressOut])
def list_payout_addresses(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # TODO: UserPayoutAddress tablosundan çekin
    return []


@router.post("/payout-addresses", response_model=PayoutAddressOut, status_code=201)
def add_payout_address(
    body: PayoutAddressIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # Doğrulama ipuçları:
    # - internal_binance: identifier e-posta veya UID görünümlü mü?
    # - onchain: ağ + adres biçimi (temel regex) kontrolü
    # TODO: kaydı oluşturup döndürün. is_default=True ise diğerlerini false yapın (aynı user).
    return PayoutAddressOut(
        id=1,
        kind=body.kind,
        network=body.network,
        identifier=body.identifier,
        memo_tag=body.memo_tag,
        is_default=body.is_default,
        label=body.label,
        verified_at=None,
    )


@router.post("/payout-addresses/{addr_id}/make-default", status_code=204)
def make_default_payout_address(
    addr_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # TODO: addr.user_id==user.id doğrula, tüm adresleri default=False yap, bu adresi True yap
    return


@router.delete("/payout-addresses/{addr_id}", status_code=204)
def delete_payout_address(
    addr_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # TODO: soft delete veya hard delete uygulayın
    return


# ------- Requests (user side) -------
@router.post("/deposit-requests", status_code=201)
def create_deposit_request(
    body: DepositRequestIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    amount = q_usdt(body.amount)
    if amount <= 0:
        raise HTTPException(400, "Geçersiz miktar")
    # TODO: CashRequest(type=DEPOSIT, amount=amount, state=PENDING, user_id=user.id, fund_id=FUND_ID)
    # Ücret kesintisi onay anında uygulanacak; burada sadece talep yaratılır.
    return {"ok": True}


@router.post("/withdraw-requests", status_code=201)
def create_withdraw_request(
    body: WithdrawRequestIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # Kullanıcı amount (USDT) veya units ile talep eder.
    # Not: Uygunluk (kilitsiz units) kontrolü admin onayında kesin yapılacak;
    # burada istek oluşturulur, input kaba doğrulama yapılır.
    if body.amount:
        amt = q_usdt(body.amount)
        if amt <= 0:
            raise HTTPException(400, "Geçersiz tutar")
    if body.units:
        u = q_units(body.units)
        if u <= 0:
            raise HTTPException(400, "Geçersiz birim")
    # TODO: CashRequest(type=WITHDRAW, state=PENDING, ...)
    return {"ok": True}


@router.post("/withdraw-early", status_code=201)
def create_withdraw_early_request(
    body: WithdrawRequestIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user = require_asil_user(user)
    # Politikalar: ayda 1, %10 limit vb. kontroller admin onayında kesinlenir.
    # Burada talebi açıyoruz.
    # TODO: CashRequest(type=WITHDRAW_EARLY, penalty_rate=EARLY_PENALTY, state=PENDING, ...)
    return {"ok": True}
