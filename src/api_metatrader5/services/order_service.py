from __future__ import annotations

from ..core.config import Settings
from ..core.errors import NotSupportedError
from ..schemas.orders import (
    OrderPreviewRequest,
    OrderPreviewResponse,
    OrderSubmitRequest,
    OrderSubmitResponse,
)


class OrderService:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings

    def preview_order(self, payload: OrderPreviewRequest) -> OrderPreviewResponse:
        raise NotSupportedError(
            "BTG Trader Desk integration currently supports market data only. Order preview is not supported yet.",
            details={"provider": "btg_trader_desk", "symbol": payload.symbol.strip().upper()},
        )

    def submit_order(self, payload: OrderSubmitRequest) -> OrderSubmitResponse:
        raise NotSupportedError(
            "BTG Trader Desk integration currently supports market data only. Live order submission is not supported yet.",
            details={"provider": "btg_trader_desk", "symbol": payload.symbol.strip().upper()},
        )
