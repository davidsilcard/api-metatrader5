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
    app_log_file: str | None = None
    app_log_max_bytes: int = 10 * 1024 * 1024
    app_log_backup_count: int = 5

    hmac_shared_keys: str = ""
    hmac_key_scopes: str = ""
    hmac_allowed_clock_skew_seconds: int = 30
    hmac_nonce_ttl_seconds: int = 300
    mt5_gateway_key_id: str = "edge-1"
    mt5_gateway_shared_secret: SecretStr | None = None
    mt5_gateway_scopes: str = "quotes:read,symbols:read,orders:preview"

    mt5_terminal_path: str | None = None
    mt5_login: int | None = None
    mt5_password: SecretStr | None = None
    mt5_server: str | None = None
    mt5_symbol_aliases: str = ""
    mt5_default_deviation: int = 20
    mt5_magic_number: int = 500001
    mt5_order_comment_prefix: str = "api-metatrader5"
    mt5_enable_order_send: bool = False
    mt5_reconnect_max_attempts: int = 3
    mt5_reconnect_backoff_seconds: float = 1.0
    mt5_connection_probe_interval_seconds: int = 5

    @field_validator(
        "mt5_terminal_path",
        "mt5_server",
        "app_log_file",
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
