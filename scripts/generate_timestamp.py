#!/usr/bin/env python3
# File: app/generate_timestamp.py

"""Bu dosya, şimdiki UTC zamanını UNIX formatına (saniye) dönüştürür."""
import time

timestamp = int(time.time())
print(f"Generated UNIX timestamp: {timestamp}")
