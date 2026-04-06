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
from ...security.hmac_auth import verify_hmac_request
from ...services.order_service import OrderService


router = APIRouter(
    prefix="/internal/v1/orders",
    tags=["orders"],
    dependencies=[Depends(verify_hmac_request)],
)


@router.post("/preview", response_model=OrderPreviewResponse)
def preview_order(
    payload: OrderPreviewRequest,
    _settings: Settings = Depends(get_settings),
    order_service: OrderService = Depends(get_order_service),
) -> OrderPreviewResponse:
    return order_service.preview_order(payload)


@router.post("", response_model=OrderSubmitResponse)
def submit_order(
    payload: OrderSubmitRequest,
    _settings: Settings = Depends(get_settings),
    order_service: OrderService = Depends(get_order_service),
) -> OrderSubmitResponse:
    return order_service.submit_order(payload)
