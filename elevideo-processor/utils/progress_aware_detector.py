import math
from typing import Optional

import cv2

from utils.progress_tracker import ProcessingPhase


class ProgressAwareDetector:
    """
    Proxy transparente del detector que convierte llamadas reales a detect()
    en progreso local de la fase activa.

    No altera el detector ni su estado de tracking. Cualquier atributo o método
    no definido aquí se delega al detector original.
    """

    def __init__(self, detector, tracker):
        self._detector = detector
        self._tracker = tracker
        self._phase: Optional[ProcessingPhase] = None
        self._expected_samples = 1
        self._processed_samples = 0
        self._message = "Analizando video..."
        self._max_fraction = 0.96

    def configure(
        self,
        phase: ProcessingPhase,
        expected_samples: int,
        message: str,
        max_fraction: float = 0.96,
    ) -> None:
        self._phase = phase
        self._expected_samples = max(1, int(expected_samples))
        self._processed_samples = 0
        self._message = message
        self._max_fraction = max(0.1, min(1.0, float(max_fraction)))

    def complete_phase(self, message: Optional[str] = None) -> None:
        if self._phase is None:
            return
        self._tracker.update_phase_fraction(1.0, message or self._message)

    def detect(self, frame):
        result = self._detector.detect(frame)
        if self._phase is not None and self._tracker.current_phase == self._phase:
            self._processed_samples += 1
            fraction = min(
                self._max_fraction,
                self._processed_samples / self._expected_samples,
            )
            visible_processed = min(self._processed_samples, self._expected_samples)
            self._tracker.update_phase_fraction(
                fraction,
                f"{self._message} {visible_processed}/{self._expected_samples}",
                metadata={
                    "analysis_samples_processed": self._processed_samples,
                    "analysis_samples_expected": self._expected_samples,
                },
            )
        return result

    def __getattr__(self, name):
        return getattr(self._detector, name)


def expected_tracking_samples(total_frames: int, sample_rate: int) -> int:
    """Estimación de llamadas base al detector durante Smart Crop."""
    if total_frames <= 0:
        return 1
    return max(1, int(math.ceil(total_frames / max(1, sample_rate))))


def expected_tracking_samples_for_video(video_path: str, sample_rate: int) -> int:
    cap = cv2.VideoCapture(video_path)
    try:
        if not cap.isOpened():
            return 1
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return expected_tracking_samples(total_frames, sample_rate)
    finally:
        cap.release()


def expected_selector_samples(total_duration: float) -> int:
    """
    SegmentSelector v2/v3 limita el análisis visual a ~480 muestras y usa una
    separación base cercana a 1.5 s. Esta estimación refleja ese trabajo real.
    """
    if total_duration <= 0:
        return 1
    return max(1, min(480, int(math.ceil(total_duration / 1.5))))
