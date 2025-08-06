#!/usr/bin/env python3
# app/utils/signing.py

import hmac
import hashlib


def sign_payload(payload: str, secret: str) -> str:
    """
    Verilen payload string'i HMAC SHA256 ile imzalar ve hex kodlu imzayı döner.

    :param payload: İmzalanacak query string (örneğin "symbol=BTCUSDT&...&timestamp=..." )
    :param secret: API secret key
    :return: Hex kodlu imza
    """
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
