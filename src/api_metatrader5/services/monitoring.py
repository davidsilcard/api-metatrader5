from __future__ import annotations

import ctypes
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from .market_data_client import MarketDataClientProtocol


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((len(values) - 1) * percentile)))
    return values[index]


@dataclass
class EndpointMetrics:
    requests: int = 0
    in_flight: int = 0
    errors: int = 0
    status_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=1000))


class MonitoringService:
    def __init__(self, *, market_data_client: MarketDataClientProtocol) -> None:
        self.market_data_client = market_data_client
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._global = EndpointMetrics()
        self._by_endpoint: dict[str, EndpointMetrics] = defaultdict(EndpointMetrics)

    def request_started(self, endpoint_key: str) -> None:
        with self._lock:
            self._global.requests += 1
            self._global.in_flight += 1
            endpoint = self._by_endpoint[endpoint_key]
            endpoint.requests += 1
            endpoint.in_flight += 1

    def request_finished(self, endpoint_key: str, *, status_code: int, duration_ms: float) -> None:
        status_key = f"{status_code // 100}xx"
        with self._lock:
            self._global.in_flight = max(0, self._global.in_flight - 1)
            self._global.status_counts[status_key] += 1
            self._global.durations_ms.append(duration_ms)
            if status_code >= 400:
                self._global.errors += 1

            endpoint = self._by_endpoint[endpoint_key]
            endpoint.in_flight = max(0, endpoint.in_flight - 1)
            endpoint.status_counts[status_key] += 1
            endpoint.durations_ms.append(duration_ms)
            if status_code >= 400:
                endpoint.errors += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            endpoints = {
                key: self._serialize_metrics(metrics)
                for key, metrics in sorted(self._by_endpoint.items())
            }
            global_metrics = self._serialize_metrics(self._global)

        return {
            "uptime_seconds": round(time.time() - self.started_at, 2),
            "global": global_metrics,
            "endpoints": endpoints,
            "provider": self.market_data_client.connection_status(),
            "mt5": self.market_data_client.connection_status(),
            "machine": self._machine_snapshot(),
        }

    @staticmethod
    def _serialize_metrics(metrics: EndpointMetrics) -> dict[str, Any]:
        durations = sorted(metrics.durations_ms)
        avg_ms = round(sum(durations) / len(durations), 2) if durations else 0.0
        return {
            "requests": metrics.requests,
            "in_flight": metrics.in_flight,
            "errors": metrics.errors,
            "status_counts": dict(metrics.status_counts),
            "latency_ms": {
                "avg": avg_ms,
                "p50": round(_percentile(durations, 0.50), 2),
                "p95": round(_percentile(durations, 0.95), 2),
                "p99": round(_percentile(durations, 0.99), 2),
                "max": round(max(durations), 2) if durations else 0.0,
                "samples": len(durations),
            },
        }

    @staticmethod
    def _machine_snapshot() -> dict[str, Any]:
        return {
            "cpu_count": os.cpu_count(),
            "process_id": os.getpid(),
            "system_uptime_seconds": MonitoringService._system_uptime_seconds(),
            "memory": MonitoringService._memory_snapshot(),
        }

    @staticmethod
    def _system_uptime_seconds() -> float | None:
        try:
            return round(ctypes.windll.kernel32.GetTickCount64() / 1000.0, 2)
        except Exception:
            return None

    @staticmethod
    def _memory_snapshot() -> dict[str, Any] | None:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return {
                "load_percent": int(status.dwMemoryLoad),
                "total_physical_mb": round(status.ullTotalPhys / (1024 * 1024), 2),
                "available_physical_mb": round(status.ullAvailPhys / (1024 * 1024), 2),
                "total_pagefile_mb": round(status.ullTotalPageFile / (1024 * 1024), 2),
                "available_pagefile_mb": round(status.ullAvailPageFile / (1024 * 1024), 2),
            }
        except Exception:
            return None
