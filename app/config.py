#!/usr/bin/env python3
# app/config.py
# Python 3.9
from pydantic import BaseSettings, Field, root_validator, validator
from typing import List, Optional


class Settings(BaseSettings):
    DB_URL: str = Field(..., env="DB_URL")

    # Çoklu Borsa Yönetimi (CSV formatında, örn: "binance_futures_testnet,binance_futures_mainnet")
    ACTIVE_EXCHANGES: str = Field(..., env="ACTIVE_EXCHANGES")
    DEFAULT_EXCHANGE: str = Field(..., env="DEFAULT_EXCHANGE")

    # Global varsayılanlar
    HTTP_TIMEOUT_SYNC: float = Field(2.0, env="HTTP_TIMEOUT_SYNC")
    HTTP_TIMEOUT_SHORT: float = Field(5.0, env="HTTP_TIMEOUT_SHORT")
    HTTP_TIMEOUT_LONG: float = Field(15.0, env="HTTP_TIMEOUT_LONG")

    # ... mevcut alanlar ...
    FUTURES_RECV_WINDOW_MS: int = Field(7000, env="FUTURES_RECV_WINDOW_MS")
    # Uzun pencere
    FUTURES_RECV_WINDOW_LONG_MS: int = Field(15000, env="FUTURES_RECV_WINDOW_LONG_MS")

    MARKET_MA_SMA_PERIODS: str = Field("7,25", env="MARKET_MA_SMA_PERIODS")
    MARKET_MA_EMA_PERIODS: str = Field("99", env="MARKET_MA_EMA_PERIODS")
    MARKET_MA_TOLERANCE_PCT: float = Field(1.5, env="MARKET_MA_TOLERANCE_PCT")

    # ---- (Opsiyonel) borsa-bazlı override'lar: set edilmezse None kalsın ----
    BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_SYNC: Optional[float] = Field(
        None, env="BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_SYNC"
    )
    BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_SHORT: Optional[float] = Field(
        None, env="BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_SHORT"
    )
    BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_LONG: Optional[float] = Field(
        None, env="BINANCE_FUTURES_TESTNET_HTTP_TIMEOUT_LONG"
    )
    BINANCE_FUTURES_TESTNET_RECV_WINDOW_MS: Optional[int] = Field(
        None, env="BINANCE_FUTURES_TESTNET_RECV_WINDOW_MS"
    )
    BINANCE_FUTURES_TESTNET_RECV_WINDOW_LONG_MS: Optional[int] = Field(
        None, env="BINANCE_FUTURES_TESTNET_RECV_WINDOW_LONG_MS"
    )

    BINANCE_FUTURES_MAINNET_HTTP_TIMEOUT_SYNC: Optional[float] = Field(
        None, env="BINANCE_FUTURES_MAINNET_HTTP_TIMEOUT_SYNC"
    )
    BINANCE_FUTURES_MAINNET_HTTP_TIMEOUT_SHORT: Optional[float] = Field(
        None, env="BINANCE_FUTURES_MAINNET_HTTP_TIMEOUT_SHORT"
    )
    BINANCE_FUTURES_MAINNET_HTTP_TIMEOUT_LONG: Optional[float] = Field(
        None, env="BINANCE_FUTURES_MAINNET_HTTP_TIMEOUT_LONG"
    )
    BINANCE_FUTURES_MAINNET_RECV_WINDOW_MS: Optional[int] = Field(
        None, env="BINANCE_FUTURES_MAINNET_RECV_WINDOW_MS"
    )
    BINANCE_FUTURES_MAINNET_RECV_WINDOW_LONG_MS: Optional[int] = Field(
        None, env="BINANCE_FUTURES_MAINNET_RECV_WINDOW_LONG_MS"
    )

    # Doğrulama döngü intervali (saniye)
    VERIFY_INTERVAL_SECONDS: int = Field(5, env="VERIFY_INTERVAL_SECONDS")

    # Verifier yalnızca DEFAULT_EXCHANGE üzerinde çalışsın mı?
    VERIFY_ONLY_DEFAULT: bool = Field(True, env="VERIFY_ONLY_DEFAULT")

    # Binance Futures Testnet
    BINANCE_FUTURES_TESTNET_API_KEY: str = Field(
        default="", env="BINANCE_FUTURES_TESTNET_API_KEY"
    )
    BINANCE_FUTURES_TESTNET_API_SECRET: str = Field(
        default="", env="BINANCE_FUTURES_TESTNET_API_SECRET"
    )

    # Binance Futures Mainnet
    BINANCE_FUTURES_MAINNET_API_KEY: str = Field(
        default="", env="BINANCE_FUTURES_MAINNET_API_KEY"
    )
    BINANCE_FUTURES_MAINNET_API_SECRET: str = Field(
        default="", env="BINANCE_FUTURES_MAINNET_API_SECRET"
    )

    # Bybit ortak hesap tipi (UNIFIED / CONTRACT). Opsiyonel; modül tarafı AUTO fallback yapabilir.
    BYBIT_ACCOUNT_TYPE: Optional[str] = Field(default=None, env="BYBIT_ACCOUNT_TYPE")

    # Bybit Futures Testnet
    BYBIT_FUTURES_TESTNET_API_KEY: str = Field(
        default="", env="BYBIT_FUTURES_TESTNET_API_KEY"
    )
    BYBIT_FUTURES_TESTNET_API_SECRET: str = Field(
        default="", env="BYBIT_FUTURES_TESTNET_API_SECRET"
    )

    # # Bybit Futures Mainnet (istersen sonra kullanırsın)
    # BYBIT_FUTURES_MAINNET_API_KEY: str = Field(
    #     default="", env="BYBIT_FUTURES_MAINNET_API_KEY"
    # )
    # BYBIT_FUTURES_MAINNET_API_SECRET: str = Field(
    #     default="", env="BYBIT_FUTURES_MAINNET_API_SECRET"
    # )

    # MEXC Futures Mainnet
    MEXC_FUTURES_API_KEY: str = Field(default="", env="MEXC_FUTURES_API_KEY")
    MEXC_FUTURES_API_SECRET: str = Field(default="", env="MEXC_FUTURES_API_SECRET")

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(..., env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str = Field(..., env="GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: str = Field(
        "http://localhost:8000/auth/google/callback",
        env="GOOGLE_REDIRECT_URI",
        # Secure
        # "https://localhost:8000/auth/google/callback",
        # env="GOOGLE_REDIRECT_URI"
    )

    # Root admins
    ADMIN_EMAIL_WHITELIST: str = Field("", env="ADMIN_EMAIL_WHITELIST")
    # Session Secret
    SESSION_SECRET: str = Field(..., env="SESSION_SECRET")
    # Allowed fund managers
    ALLOWED_FUND_MANAGER_IDS: str = Field("", env="ALLOWED_FUND_MANAGER_IDS")

    @validator("SESSION_SECRET", allow_reuse=True)
    def validate_session_secret(cls, v: str) -> str:  # noqa: N805
        if not v or not v.strip():
            raise ValueError("SESSION_SECRET must be set and not empty")
        return v

    @property
    def active_exchanges(self) -> List[str]:
        return [ex.strip() for ex in self.ACTIVE_EXCHANGES.split(",") if ex.strip()]

    @property
    def allowed_fund_manager_ids(self) -> List[str]:
        return [
            x.strip() for x in self.ALLOWED_FUND_MANAGER_IDS.split(",") if x.strip()
        ]

    @staticmethod
    def _parse_periods(raw: str) -> List[int]:
        if raw is None:
            return []
        out: List[int] = []
        for part in str(raw).replace(";", ",").split(","):
            piece = part.strip()
            if not piece:
                continue
            try:
                val = int(piece)
            except ValueError:
                continue
            if val > 0:
                out.append(val)
        return out

    @property
    def market_ma_sma_periods(self) -> List[int]:
        return self._parse_periods(self.MARKET_MA_SMA_PERIODS)

    @property
    def market_ma_ema_periods(self) -> List[int]:
        return self._parse_periods(self.MARKET_MA_EMA_PERIODS)

    @root_validator(pre=True, allow_reuse=True)
    def validate_default_exchange(cls, values):  # noqa: N805
        active = values.get("ACTIVE_EXCHANGES", "")
        default = values.get("DEFAULT_EXCHANGE", "")
        active_list = [x.strip() for x in active.split(",")]
        if default not in active_list:
            raise ValueError(
                f"DEFAULT_EXCHANGE '{default}' is not listed in ACTIVE_EXCHANGES"
            )
        return values

    class Config:
        env_file = ".env"


settings = Settings()
