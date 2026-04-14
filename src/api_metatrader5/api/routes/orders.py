from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_order_service, get_settings
from ...core.config import Settings
from ...schemas.orders import (
    OrderPreviewRequest,
    OrderPreviewResponse,
    OrderSubmitRequest,
    OrderSubmitResponse,
)
from ...security.hmac_auth import require_hmac_scopes
from ...services.order_service import OrderService


router = APIRouter(
    prefix="/internal/v1/orders",
    tags=["orders"],
)


@router.post("/preview", response_model=OrderPreviewResponse)
def preview_order(
    payload: OrderPreviewRequest,
    _auth=Depends(require_hmac_scopes("orders:preview")),
    _settings: Settings = Depends(get_settings),
    order_service: OrderService = Depends(get_order_service),
) -> OrderPreviewResponse:
    return order_service.preview_order(payload)


@router.post("", response_model=OrderSubmitResponse)
def submit_order(
    payload: OrderSubmitRequest,
    _auth=Depends(require_hmac_scopes("orders:send")),
    _settings: Settings = Depends(get_settings),
    order_service: OrderService = Depends(get_order_service),
) -> OrderSubmitResponse:
    return order_service.submit_order(payload)
