import os

os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ACTIVE_EXCHANGES", "binance_futures_testnet")
os.environ.setdefault("DEFAULT_EXCHANGE", "binance_futures_testnet")
os.environ.setdefault("GOOGLE_CLIENT_ID", "dummy-client")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "dummy-secret")
os.environ.setdefault("SESSION_SECRET", "dummy-session")
os.environ.setdefault(
    "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
)
