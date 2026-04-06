from __future__ import annotations

import uvicorn

from .core.config import get_settings


def main() -> int:
    settings = get_settings()
    uvicorn.run(
        "api_metatrader5.app:create_app",
        factory=True,
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.app_log_level.lower(),
    )
    return 0
