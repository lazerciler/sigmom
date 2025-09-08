#!/usr/bin/env python3
# app/models.py
# Python 3.9
import uuid
from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    DateTime,
    Numeric,
    Boolean,
    JSON,
    ForeignKey,
    text,
    func,
    Enum as SaEnum,
)
from sqlalchemy.orm import relationship
from app.database import Base


class RawSignal(Base):
    __tablename__ = "raw_signals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    payload = Column(JSON, nullable=False)
    fund_manager_id = Column(String(64), nullable=False, index=True)
    received_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    open_trades = relationship(
        "StrategyOpenTrade", back_populates="raw_signal", cascade="all, delete-orphan"
    )
    close_trades = relationship(
        "StrategyTrade", back_populates="raw_signal", cascade="all, delete-orphan"
    )


class StrategyOpenTrade(Base):
    __tablename__ = "strategy_open_trades"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    public_id = Column(
        String(36),
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    raw_signal_id = Column(
        BigInteger,
        ForeignKey("raw_signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fund_manager_id = Column(String(64), nullable=False)
    symbol = Column(String(32), nullable=False)
    side = Column(SaEnum("long", "short", name="open_side_enum"), nullable=False)
    entry_price = Column(Numeric(18, 8), nullable=False)
    position_size = Column(Numeric(18, 8), nullable=False)
    leverage = Column(Integer, nullable=False)
    order_type = Column(String(16), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    unrealized_pnl = Column(Numeric(18, 8), default=0, nullable=False)
    exchange = Column(String(64), nullable=False)
    exchange_order_id = Column(String(100), nullable=False, index=True)
    response_data = Column(JSON, nullable=True)

    status = Column(
        String(20), nullable=False, server_default=text("'pending'"), index=True
    )
    exchange_verified = Column(Boolean, nullable=False, server_default=text("0"))
    verification_attempts = Column(Integer, nullable=False, server_default=text("0"))
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    raw_signal = relationship("RawSignal", back_populates="open_trades")
    trades = relationship(
        "StrategyTrade", back_populates="open_trade", cascade="all, delete-orphan"
    )


class StrategyTrade(Base):
    __tablename__ = "strategy_trades"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    public_id = Column(
        String(36),
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    raw_signal_id = Column(
        BigInteger,
        ForeignKey("raw_signals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    open_trade_public_id = Column(
        String(36),
        ForeignKey("strategy_open_trades.public_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fund_manager_id = Column(String(64), nullable=False)
    symbol = Column(String(32), nullable=False)
    side = Column(SaEnum("long", "short", name="trade_side_enum"), nullable=False)
    entry_price = Column(Numeric(18, 8), nullable=False)
    exit_price = Column(Numeric(18, 8), nullable=False)
    position_size = Column(Numeric(18, 8), nullable=False)
    leverage = Column(Integer, nullable=False)
    realized_pnl = Column(Numeric(18, 8), nullable=False)
    order_type = Column(String(16), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    exchange = Column(String(64), nullable=False)
    response_data = Column(JSON, nullable=True)

    raw_signal = relationship("RawSignal", back_populates="close_trades")
    open_trade = relationship("StrategyOpenTrade", back_populates="trades")


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    google_sub = Column(String(64), unique=True, index=True)
    name = Column(String(255))
    avatar_url = Column(String(512))
    role = Column(String(32), nullable=False, server_default=text("'user'"))
    referral_verified_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
