from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_monitoring_service
from ...security.hmac_auth import require_hmac_scopes
from ...services.monitoring import MonitoringService


router = APIRouter(
    prefix="/internal/v1/metrics",
    tags=["metrics"],
    dependencies=[Depends(require_hmac_scopes("metrics:read", "quotes:read"))],
)


@router.get("")
def get_metrics(
    monitoring_service: MonitoringService = Depends(get_monitoring_service),
) -> dict[str, object]:
    return monitoring_service.snapshot()
