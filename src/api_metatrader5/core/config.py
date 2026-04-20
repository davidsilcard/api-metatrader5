from __future__ import annotations

from functools import lru_cache
from typing import Any
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
    app_log_file: str | None = None
    app_log_max_bytes: int = 10 * 1024 * 1024
    app_log_backup_count: int = 5

    hmac_shared_keys: str = ""
    hmac_key_scopes: str = ""
    hmac_allowed_clock_skew_seconds: int = 30
    hmac_nonce_ttl_seconds: int = 300
    mt5_gateway_key_id: str = "edge-1"
    mt5_gateway_shared_secret: SecretStr | None = None
    mt5_gateway_scopes: str = "quotes:read,symbols:read,orders:preview,metrics:read"

    mt5_symbol_aliases: str = ""
    btg_trader_desk_host: str = "127.0.0.1"
    btg_trader_desk_port: int = 9099
    btg_trader_desk_token: SecretStr | None = None
    btg_trader_desk_timeout_seconds: float = 2.0
    btg_trader_desk_symbol_timeout_seconds: float = 3.0
    btg_trader_desk_symbols_file: str | None = None
    btg_trader_desk_currency: str = "BRL"
    btg_trader_desk_default_digits: int = 2
    quote_cache_ttl_ms: int = 250
    quote_negative_cache_ttl_ms: int = 1000

    @field_validator(
        "btg_trader_desk_symbols_file",
        "app_log_file",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("btg_trader_desk_token", mode="before")
    @classmethod
    def _empty_string_to_none_secret(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("quote_cache_ttl_ms", mode="before")
    @classmethod
    def _normalize_cache_ttl(cls, value: Any) -> int:
        if value is None:
            return 250
        if isinstance(value, str) and not value.strip():
            return 250
        ttl = int(value)
        return max(0, ttl)

    @field_validator("quote_negative_cache_ttl_ms", mode="before")
    @classmethod
    def _normalize_negative_cache_ttl(cls, value: Any) -> int:
        if value is None:
            return 1000
        if isinstance(value, str) and not value.strip():
            return 1000
        ttl = int(value)
        return max(0, ttl)

    @field_validator(
        "btg_trader_desk_timeout_seconds",
        "btg_trader_desk_symbol_timeout_seconds",
        mode="before",
    )
    @classmethod
    def _normalize_timeout_seconds(cls, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, str) and not value.strip():
            return 0.0
        timeout = float(value)
        return max(0.1, timeout)

    @field_validator("mt5_gateway_key_id", mode="before")
    @classmethod
    def _normalize_gateway_key_id(cls, value: object) -> str:
        if value is None:
            return "edge-1"
        text = str(value).strip()
        return text or "edge-1"

    @field_validator("mt5_gateway_shared_secret", mode="before")
    @classmethod
    def _empty_gateway_secret_to_none(cls, value: object) -> object:
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
        if pairs:
            return pairs

        if self.mt5_gateway_shared_secret is not None:
            secret = self.mt5_gateway_shared_secret.get_secret_value().strip()
            if secret:
                return {self.mt5_gateway_key_id: secret}

        raise ValueError(
            "Configure HMAC_SHARED_KEYS ou MT5_GATEWAY_SHARED_SECRET para autenticar endpoints /internal."
        )

    @property
    def hmac_scopes(self) -> Dict[str, set[str]]:
        parsed = self._parse_scope_mapping(self.hmac_key_scopes, item_separator="|")
        if parsed:
            return parsed

        if (self.hmac_shared_keys or "").strip():
            return {key_id: {"*"} for key_id in self.hmac_keys}

        if self.mt5_gateway_shared_secret is not None:
            scopes = self._parse_scope_list(self.mt5_gateway_scopes)
            return {self.mt5_gateway_key_id: scopes or {"quotes:read", "symbols:read"}}

        return {key_id: {"*"} for key_id in self.hmac_keys}

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

    @staticmethod
    def _parse_scope_mapping(raw: str, *, item_separator: str) -> Dict[str, set[str]]:
        mapping: dict[str, set[str]] = {}
        for chunk in (raw or "").split(","):
            item = chunk.strip()
            if not item or "=" not in item:
                continue
            key_id, scopes_text = item.split("=", 1)
            key_id = key_id.strip()
            scopes = Settings._parse_scope_list(scopes_text, separator=item_separator)
            if key_id and scopes:
                mapping[key_id] = scopes
        return mapping

    @staticmethod
    def _parse_scope_list(raw: str, *, separator: str = ",") -> set[str]:
        scopes = {part.strip() for part in (raw or "").split(separator) if part.strip()}
        return scopes


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
