from __future__ import annotations

from datetime import UTC

from ..core.config import Settings
from ..core.errors import AuthorizationError, MarketDataUnavailableError
from ..schemas.orders import (
    FillingType,
    OrderPreviewRequest,
    OrderPreviewResponse,
    OrderSide,
    OrderSubmitRequest,
    OrderSubmitResponse,
    OrderType,
    TimeInForce,
)
from .market_data import MarketDataService
from .mt5_client import Mt5ClientProtocol


class OrderService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: Mt5ClientProtocol,
        market_data_service: MarketDataService,
    ) -> None:
        self.settings = settings
        self.client = client
        self.market_data_service = market_data_service

    def preview_order(self, payload: OrderPreviewRequest) -> OrderPreviewResponse:
        requested_symbol = payload.symbol.strip().upper()
        resolved_symbol = self.market_data_service.resolve_symbol_name(requested_symbol)
        request_data = self._build_mt5_order_request(payload=payload, symbol=resolved_symbol)
        result = self.client.order_check(request_data)
        return OrderPreviewResponse(
            requested_symbol=requested_symbol,
            symbol=resolved_symbol,
            check_completed=result is not None,
            order_request=request_data,
            result=result,
        )

    def submit_order(self, payload: OrderSubmitRequest) -> OrderSubmitResponse:
        if not self.settings.mt5_enable_order_send:
            raise AuthorizationError(
                "Live order submission is disabled. Set MT5_ENABLE_ORDER_SEND=1 to enable it."
            )
        requested_symbol = payload.symbol.strip().upper()
        resolved_symbol = self.market_data_service.resolve_symbol_name(requested_symbol)
        request_data = self._build_mt5_order_request(payload=payload, symbol=resolved_symbol)
        result = self.client.order_send(request_data)
        return OrderSubmitResponse(
            requested_symbol=requested_symbol,
            symbol=resolved_symbol,
            live_sent=True,
            order_request=request_data,
            result=result,
        )

    def _build_mt5_order_request(
        self,
        *,
        payload: OrderPreviewRequest | OrderSubmitRequest,
        symbol: str,
    ) -> dict[str, object]:
        symbol_info = self.market_data_service.get_symbol_info(symbol)
        tick = self.client.symbol_info_tick(symbol)
        if not tick:
            raise MarketDataUnavailableError(
                "Cannot build order request because the current tick is unavailable.",
                details={"symbol": symbol},
            )

        request_data: dict[str, object] = {
            "symbol": symbol,
            "volume": float(payload.volume),
            "type": self._map_order_type(payload.side, payload.order_type),
            "action": self._map_trade_action(payload.order_type),
            "deviation": payload.deviation or self.settings.mt5_default_deviation,
            "magic": payload.magic or self.settings.mt5_magic_number,
            "comment": self._build_comment(payload),
            "type_time": self._map_time_in_force(payload.time_in_force),
            "type_filling": self._map_filling_type(payload.filling_type, symbol_info),
        }

        price = payload.price
        if payload.order_type == OrderType.market:
            price = float(tick["ask"] if payload.side == OrderSide.buy else tick["bid"])
        if price is not None:
            request_data["price"] = float(price)

        if payload.stop_limit_price is not None:
            request_data["stoplimit"] = float(payload.stop_limit_price)
        if payload.stop_loss is not None:
            request_data["sl"] = float(payload.stop_loss)
        if payload.take_profit is not None:
            request_data["tp"] = float(payload.take_profit)
        if payload.expiration is not None:
            request_data["expiration"] = int(payload.expiration.astimezone(UTC).timestamp())

        return request_data

    def _build_comment(self, payload: OrderPreviewRequest | OrderSubmitRequest) -> str:
        chunks = [self.settings.mt5_order_comment_prefix]
        if payload.client_order_id:
            chunks.append(payload.client_order_id)
        if payload.comment:
            chunks.append(payload.comment)
        comment = "|".join(chunk.strip() for chunk in chunks if chunk and chunk.strip())
        return comment[:64]

    def _map_trade_action(self, order_type: OrderType) -> int:
        if order_type == OrderType.market:
            return self.client.get_constant("TRADE_ACTION_DEAL")
        return self.client.get_constant("TRADE_ACTION_PENDING")

    def _map_order_type(self, side: OrderSide, order_type: OrderType) -> int:
        name_map = {
            (OrderSide.buy, OrderType.market): "ORDER_TYPE_BUY",
            (OrderSide.sell, OrderType.market): "ORDER_TYPE_SELL",
            (OrderSide.buy, OrderType.limit): "ORDER_TYPE_BUY_LIMIT",
            (OrderSide.sell, OrderType.limit): "ORDER_TYPE_SELL_LIMIT",
            (OrderSide.buy, OrderType.stop): "ORDER_TYPE_BUY_STOP",
            (OrderSide.sell, OrderType.stop): "ORDER_TYPE_SELL_STOP",
            (OrderSide.buy, OrderType.stop_limit): "ORDER_TYPE_BUY_STOP_LIMIT",
            (OrderSide.sell, OrderType.stop_limit): "ORDER_TYPE_SELL_STOP_LIMIT",
        }
        return self.client.get_constant(name_map[(side, order_type)])

    def _map_time_in_force(self, time_in_force: TimeInForce) -> int:
        name_map = {
            TimeInForce.gtc: "ORDER_TIME_GTC",
            TimeInForce.day: "ORDER_TIME_DAY",
            TimeInForce.specified: "ORDER_TIME_SPECIFIED",
        }
        return self.client.get_constant(name_map[time_in_force])

    def _map_filling_type(self, filling_type: FillingType, symbol_info: dict[str, object]) -> int:
        if filling_type == FillingType.auto:
            symbol_fill = symbol_info.get("filling_mode")
            if symbol_fill is not None:
                return int(symbol_fill)
            fallback_names = ("ORDER_FILLING_RETURN", "ORDER_FILLING_IOC", "ORDER_FILLING_FOK")
            for constant_name in fallback_names:
                try:
                    return self.client.get_constant(constant_name)
                except Exception:
                    continue
            raise MarketDataUnavailableError("Unable to determine order filling type for symbol.")

        name_map = {
            FillingType.ioc: "ORDER_FILLING_IOC",
            FillingType.fok: "ORDER_FILLING_FOK",
            FillingType.return_value: "ORDER_FILLING_RETURN",
        }
        return self.client.get_constant(name_map[filling_type])
