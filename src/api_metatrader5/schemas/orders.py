from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class OrderType(str, Enum):
    market = "market"
    limit = "limit"
    stop = "stop"
    stop_limit = "stop_limit"


class TimeInForce(str, Enum):
    gtc = "gtc"
    day = "day"
    specified = "specified"


class FillingType(str, Enum):
    auto = "auto"
    ioc = "ioc"
    fok = "fok"
    return_value = "return"


class OrderRequestBase(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType
    volume: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    stop_limit_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    deviation: int | None = Field(default=None, ge=0, le=500)
    time_in_force: TimeInForce = TimeInForce.day
    filling_type: FillingType = FillingType.auto
    expiration: datetime | None = None
    comment: str | None = Field(default=None, max_length=64)
    magic: int | None = Field(default=None, ge=0)
    client_order_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_order_fields(self) -> "OrderRequestBase":
        if self.order_type != OrderType.market and self.price is None:
            raise ValueError("price is required for pending orders.")
        if self.order_type == OrderType.stop_limit and self.stop_limit_price is None:
            raise ValueError("stop_limit_price is required for stop_limit orders.")
        if self.time_in_force == TimeInForce.specified and self.expiration is None:
            raise ValueError("expiration is required when time_in_force is specified.")
        return self


class OrderPreviewRequest(OrderRequestBase):
    pass


class OrderSubmitRequest(OrderRequestBase):
    pass


class OrderPreviewResponse(BaseModel):
    requested_symbol: str
    symbol: str
    check_completed: bool
    order_request: dict[str, Any]
    result: dict[str, Any] | None = None
    mt5_last_error: dict[str, Any] | None = None


class OrderSubmitResponse(BaseModel):
    requested_symbol: str
    symbol: str
    live_sent: bool
    order_request: dict[str, Any]
    result: dict[str, Any] | None = None
    mt5_last_error: dict[str, Any] | None = None
