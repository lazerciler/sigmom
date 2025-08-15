#!/usr/bin/env python3
# app/utils/generate_hash.py
# python 3.9
import hashlib
from app.schemas import WebhookSignal


def generate_signal_hash(signal: WebhookSignal) -> str:
    """
    WebhookSignal nesnesinden benzersiz bir SHA256 hash üretir.
    Dupe guard amacıyla kullanılır.

    Hash'e etki eden alanlar:
    - mode
    - symbol
    - side
    - entry_price
    - position_size
    - leverage
    - order_type
    - exchange
    - fund_manager_id

    Returns:
        str: SHA256 hex digest
    """
    hash_input = (
        f"{signal.mode}-{signal.symbol}-{signal.side}-"
        f"{signal.entry_price}-{signal.position_size}-"
        f"{signal.leverage}-{signal.order_type}-{signal.exchange}-"
        f"{signal.fund_manager_id}"
    )

    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
