#!/usr/bin/env python3
# app/schemas.py
# Python 3.9
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, root_validator


class WebhookSignal(BaseModel):
    mode: Literal["open", "close"]
    symbol: str
    side: str
    position_size: float
    order_type: str
    exchange: str
    timestamp: datetime
    fund_manager_id: str
    reduce_only: bool = False

    # Open için gerekenler
    entry_price: Optional[float] = None
    leverage: Optional[int] = None
    order_id: Optional[str] = None

    # Close için gerekenler
    exit_price: Optional[float] = None
    public_id: Optional[str] = None  # gerekiyorsa açık pozisyon eşleştirmede

    @root_validator
    def validate_by_mode(cls, values):
        mode = values.get("mode")
        if mode == "open":
            if values.get("entry_price") is None:
                raise ValueError("entry_price is required for open signals")
            if values.get("leverage") is None:
                raise ValueError("leverage is required for open signals")
        elif mode == "close":
            if values.get("exit_price") is None:
                raise ValueError("exit_price is required for close signals")
        return values
