from __future__ import annotations

from functools import lru_cache
from typing import Dict

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "api-metatrader5"
    app_version: str = "0.1.0"
    app_log_level: str = "INFO"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    hmac_shared_keys: str = "edge-1=change-this-secret"
    hmac_allowed_clock_skew_seconds: int = 30
    hmac_nonce_ttl_seconds: int = 300

    mt5_terminal_path: str | None = None
    mt5_login: int | None = None
    mt5_password: SecretStr | None = None
    mt5_server: str | None = None
    mt5_symbol_aliases: str = ""
    mt5_default_deviation: int = 20
    mt5_magic_number: int = 500001
    mt5_order_comment_prefix: str = "api-metatrader5"
    mt5_enable_order_send: bool = False

    @field_validator(
        "mt5_terminal_path",
        "mt5_server",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("mt5_login", mode="before")
    @classmethod
    def _empty_string_to_none_int(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("mt5_password", mode="before")
    @classmethod
    def _empty_string_to_none_secret(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def hmac_keys(self) -> Dict[str, str]:
        pairs: dict[str, str] = {}
        for chunk in self.hmac_shared_keys.split(","):
            item = chunk.strip()
            if not item or "=" not in item:
                continue
            key_id, secret = item.split("=", 1)
            key_id = key_id.strip()
            secret = secret.strip()
            if key_id and secret:
                pairs[key_id] = secret
        if not pairs:
            raise ValueError("Configure ao menos uma chave em HMAC_SHARED_KEYS.")
        return pairs

    @property
    def symbol_alias_map(self) -> Dict[str, str]:
        raw_aliases = self.mt5_symbol_aliases or ""
        aliases: dict[str, str] = {}
        for chunk in raw_aliases.split(","):
            item = chunk.strip()
            if not item or "=" not in item:
                continue
            public_symbol, broker_symbol = item.split("=", 1)
            public_symbol = public_symbol.strip().upper()
            broker_symbol = broker_symbol.strip().upper()
            if public_symbol and broker_symbol:
                aliases[public_symbol] = broker_symbol
        return aliases


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
