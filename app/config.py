#!/usr/bin/env python3
# app/config.py
# Python 3.9
from pydantic import BaseSettings, Field, root_validator, validator
from typing import List


class Settings(BaseSettings):
    DB_URL: str = Field(..., env="DB_URL")

    # Çoklu Borsa Yönetimi (CSV formatında, örn: "binance_futures_testnet,binance_futures_mainnet")
    ACTIVE_EXCHANGES: str = Field(..., env="ACTIVE_EXCHANGES")
    DEFAULT_EXCHANGE: str = Field(..., env="DEFAULT_EXCHANGE")

    # Doğrulama döngü intervali (saniye)
    VERIFY_INTERVAL_SECONDS: int = Field(5, env="VERIFY_INTERVAL_SECONDS")

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

    # MEXC Futures Mainnet
    MEXC_FUTURES_MAINNET_API_KEY: str = Field(
        default="", env="MEXC_FUTURES_MAINNET_API_KEY"
    )
    MEXC_FUTURES_MAINNET_API_SECRET: str = Field(
        default="", env="MEXC_FUTURES_MAINNET_API_SECRET"
    )

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(..., env="GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str = Field(..., env="GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: str = Field(
        "http://localhost:8000/auth/google/callback", env="GOOGLE_REDIRECT_URI"
    )
    ADMIN_EMAILS: str = Field("", env="ADMIN_EMAILS")

    # Session Secret
    SESSION_SECRET: str = Field(..., env="SESSION_SECRET")

    @validator("SESSION_SECRET")
    def validate_session_secret(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("SESSION_SECRET must be set and not empty")
        return v

    @property
    def active_exchanges(self) -> List[str]:
        return [ex.strip() for ex in self.ACTIVE_EXCHANGES.split(",") if ex.strip()]

    @root_validator(pre=True)
    def validate_default_exchange(cls, values):
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
