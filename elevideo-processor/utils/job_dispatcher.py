import logging
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Any, Callable

logger = logging.getLogger(__name__)


class BoundedJobDispatcher:
    """Cola FIFO acotada con un número fijo de workers de procesamiento."""

    def __init__(
        self,
        handler: Callable[[str, Any], None],
        *,
        max_workers: int = 1,
        max_queue_size: int = 8,
    ) -> None:
        self._handler = handler
        self._queue: Queue[tuple[str, Any]] = Queue(maxsize=max(1, max_queue_size))
        self._stop = Event()
        self._workers: list[Thread] = []

        for index in range(max(1, max_workers)):
            worker = Thread(
                target=self._worker_loop,
                name=f"video-job-worker-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def submit(self, job_id: str, request: Any) -> bool:
        try:
            self._queue.put_nowait((job_id, request))
            return True
        except Full:
            return False

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def capacity(self) -> int:
        return self._queue.maxsize

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id, request = self._queue.get(timeout=0.5)
            except Empty:
                continue

            try:
                self._handler(job_id, request)
            except Exception:
                logger.exception("Worker de video falló fuera del handler | job_id=%s", job_id)
            finally:
                self._queue.task_done()
