import os
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Dict, Iterable


class GuardrailRejected(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class ProcessingGuardrailSettings:
    max_outstanding_per_user: int
    max_requests_per_minute: int
    max_requests_per_hour: int
    max_requests_per_day: int
    max_global_requests_per_minute: int
    max_concurrent_jobs: int
    max_queue_size: int
    job_retention_hours: int

    @classmethod
    def from_env(cls) -> "ProcessingGuardrailSettings":
        return cls(
            max_outstanding_per_user=_env_int("PROCESSING_MAX_OUTSTANDING_PER_USER", 3, minimum=1),
            max_requests_per_minute=_env_int("PROCESSING_MAX_REQUESTS_PER_MINUTE", 6, minimum=1),
            max_requests_per_hour=_env_int("PROCESSING_MAX_REQUESTS_PER_HOUR", 30, minimum=1),
            max_requests_per_day=_env_int("PROCESSING_MAX_REQUESTS_PER_DAY", 100, minimum=1),
            max_global_requests_per_minute=_env_int("PROCESSING_MAX_GLOBAL_REQUESTS_PER_MINUTE", 20, minimum=1),
            max_concurrent_jobs=_env_int("PROCESSING_MAX_CONCURRENT_JOBS", 1, minimum=1),
            max_queue_size=_env_int("PROCESSING_MAX_QUEUE_SIZE", 8, minimum=1),
            job_retention_hours=_env_int("PROCESSING_JOB_RETENTION_HOURS", 24, minimum=1),
        )


class ProcessingGuardrails:
    """Protecciones antiabuso para el demo, no cuotas comerciales."""

    def __init__(self, settings: ProcessingGuardrailSettings | None = None) -> None:
        self.settings = settings or ProcessingGuardrailSettings.from_env()
        self._user_requests: Dict[str, Deque[datetime]] = defaultdict(deque)
        self._global_requests: Deque[datetime] = deque()

    def assert_can_create(self, user_id: str, jobs: Iterable[dict]) -> None:
        now = datetime.utcnow()
        user_key = str(user_id)

        outstanding = sum(
            1
            for job in jobs
            if str(job.get("user_id")) == user_key
            and _status_value(job.get("status")) in {"pending", "processing"}
        )
        if outstanding >= self.settings.max_outstanding_per_user:
            raise GuardrailRejected(
                429,
                (
                    "Ya tienes demasiados procesamientos pendientes. "
                    f"Espera a que termine uno antes de crear otro "
                    f"(máximo {self.settings.max_outstanding_per_user})."
                ),
            )

        user_history = self._user_requests[user_key]
        self._trim(user_history, now - timedelta(days=1))
        self._trim(self._global_requests, now - timedelta(minutes=1))

        minute_count = _count_since(user_history, now - timedelta(minutes=1))
        hour_count = _count_since(user_history, now - timedelta(hours=1))
        day_count = len(user_history)

        if minute_count >= self.settings.max_requests_per_minute:
            raise GuardrailRejected(
                429,
                "Demasiadas solicitudes en poco tiempo. Espera un minuto antes de volver a intentar.",
            )
        if hour_count >= self.settings.max_requests_per_hour:
            raise GuardrailRejected(
                429,
                "Se alcanzó el límite de protección por hora del demo. Intenta más tarde.",
            )
        if day_count >= self.settings.max_requests_per_day:
            raise GuardrailRejected(
                429,
                "Se alcanzó el límite de protección diario del demo. Intenta nuevamente mañana.",
            )
        if len(self._global_requests) >= self.settings.max_global_requests_per_minute:
            raise GuardrailRejected(
                503,
                "El procesador está recibiendo demasiadas solicitudes. Intenta nuevamente en un momento.",
            )

        user_history.append(now)
        self._global_requests.append(now)

    def cleanup_finished_jobs(
        self,
        jobs_db: Dict[str, dict],
        idempotency_jobs: Dict[str, str],
    ) -> int:
        cutoff = datetime.utcnow() - timedelta(hours=self.settings.job_retention_hours)
        removed = 0

        for job_id, job in list(jobs_db.items()):
            status = _status_value(job.get("status"))
            completed_at = job.get("completed_at")
            if status not in {"completed", "failed", "cancelled"}:
                continue
            if not isinstance(completed_at, datetime) or completed_at >= cutoff:
                continue

            scope = job.get("idempotency_scope")
            if scope and idempotency_jobs.get(scope) == job_id:
                idempotency_jobs.pop(scope, None)
            jobs_db.pop(job_id, None)
            removed += 1

        return removed

    @staticmethod
    def _trim(history: Deque[datetime], cutoff: datetime) -> None:
        while history and history[0] < cutoff:
            history.popleft()


def _count_since(history: Deque[datetime], cutoff: datetime) -> int:
    return sum(1 for timestamp in history if timestamp >= cutoff)


def _status_value(value) -> str:
    raw = getattr(value, "value", value)
    return str(raw).lower() if raw is not None else ""


def _env_int(name: str, default: int, *, minimum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)
