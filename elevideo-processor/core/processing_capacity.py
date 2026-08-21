"""Protecciones operativas ligeras para el procesador de demostración.

No representan cuotas comerciales. Su objetivo es impedir que una cuenta autenticada
pueda llenar la máquina de trabajos de FFmpeg o crear una cola ilimitada.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Deque, Dict, Iterable


@dataclass(frozen=True)
class ProcessingCapacitySettings:
    max_concurrent_jobs: int = 1
    max_queued_per_user: int = 2
    max_global_queue: int = 8
    requests_per_window: int = 6
    request_window_seconds: int = 60

    @classmethod
    def from_env(cls) -> "ProcessingCapacitySettings":
        return cls(
            max_concurrent_jobs=_positive_int("PROCESSING_MAX_CONCURRENT_JOBS", 1),
            max_queued_per_user=_positive_int("PROCESSING_MAX_QUEUED_PER_USER", 2),
            max_global_queue=_positive_int("PROCESSING_MAX_GLOBAL_QUEUE", 8),
            requests_per_window=_positive_int("PROCESSING_REQUESTS_PER_WINDOW", 6),
            request_window_seconds=_positive_int("PROCESSING_REQUEST_WINDOW_SECONDS", 60),
        )


class ProcessingCapacityExceeded(RuntimeError):
    """La solicitud es válida, pero excede una protección de capacidad."""


class ProcessingCapacityGuard:
    """Controla ráfagas y tamaño de cola con estado local al proceso.

    Para el demo desplegado como una sola instancia esto evita abuso sin introducir
    Redis, brokers o cuotas persistentes. Si se escala a varias instancias, esta capa
    debe moverse a almacenamiento compartido.
    """

    def __init__(self, settings: ProcessingCapacitySettings | None = None) -> None:
        self.settings = settings or ProcessingCapacitySettings.from_env()
        self._lock = Lock()
        self._request_times: Dict[str, Deque[float]] = defaultdict(deque)

    def assert_can_enqueue(self, user_id: str, jobs: Iterable[dict]) -> None:
        now = time.monotonic()
        jobs_snapshot = list(jobs)

        with self._lock:
            timestamps = self._request_times[user_id]
            cutoff = now - self.settings.request_window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.settings.requests_per_window:
                raise ProcessingCapacityExceeded(
                    "Has enviado demasiadas solicitudes de procesamiento en poco tiempo. "
                    "Espera un momento antes de crear otro job."
                )

            user_pending = sum(
                1
                for job in jobs_snapshot
                if str(job.get("user_id")) == user_id and _status_value(job) == "pending"
            )
            global_pending = sum(1 for job in jobs_snapshot if _status_value(job) == "pending")

            if user_pending >= self.settings.max_queued_per_user:
                raise ProcessingCapacityExceeded(
                    f"Ya tienes {self.settings.max_queued_per_user} jobs esperando. "
                    "Deja que avance la cola antes de crear otro."
                )

            if global_pending >= self.settings.max_global_queue:
                raise ProcessingCapacityExceeded(
                    "La cola de procesamiento está llena temporalmente. Intenta nuevamente más tarde."
                )

            # Solo registramos solicitudes que realmente pueden crear un nuevo job.
            timestamps.append(now)

    def reset_for_tests(self) -> None:
        with self._lock:
            self._request_times.clear()


def _status_value(job: dict) -> str:
    status = job.get("status")
    value = getattr(status, "value", status)
    return str(value or "").lower()


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default
