import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ProcessingPhase(str, Enum):
    QUEUED            = "queued"
    VALIDATING        = "validating"
    DOWNLOADING       = "downloading"
    DOWNLOAD_COMPLETE = "download_complete"
    SELECTING_SEGMENT = "selecting_segment"
    CUTTING_SEGMENT   = "cutting_segment"
    SEGMENT_COMPLETE  = "segment_complete"
    ANALYZING         = "analyzing"
    DETECTING_FACES   = "detecting_faces"
    ANALYSIS_COMPLETE = "analysis_complete"
    PROCESSING        = "processing"
    STABILIZING       = "stabilizing"
    CROPPING          = "cropping"
    ENCODING          = "encoding"
    ENCODING_COMPLETE = "encoding_complete"
    UPLOADING         = "uploading"
    UPLOAD_COMPLETE   = "upload_complete"
    CLEANING_UP       = "cleaning_up"
    COMPLETED         = "completed"
    FAILED            = "failed"


# Ventanas globales por defecto. Cada modo puede reemplazarlas para que el
# porcentaje refleje mejor el trabajo que realmente ejecuta ese pipeline.
_DEFAULT_PHASE_WINDOWS: Dict[ProcessingPhase, Tuple[int, int]] = {
    ProcessingPhase.QUEUED:            (0, 0),
    ProcessingPhase.VALIDATING:        (1, 4),
    ProcessingPhase.DOWNLOADING:       (4, 15),
    ProcessingPhase.DOWNLOAD_COMPLETE: (15, 15),
    ProcessingPhase.SELECTING_SEGMENT: (15, 30),
    ProcessingPhase.CUTTING_SEGMENT:   (30, 35),
    ProcessingPhase.SEGMENT_COMPLETE:  (35, 35),
    ProcessingPhase.ANALYZING:         (35, 38),
    ProcessingPhase.DETECTING_FACES:   (38, 62),
    ProcessingPhase.ANALYSIS_COMPLETE: (62, 62),
    ProcessingPhase.PROCESSING:        (62, 64),
    ProcessingPhase.STABILIZING:       (64, 65),
    ProcessingPhase.CROPPING:          (65, 66),
    ProcessingPhase.ENCODING:          (66, 87),
    ProcessingPhase.ENCODING_COMPLETE: (87, 87),
    ProcessingPhase.UPLOADING:         (87, 95),
    ProcessingPhase.UPLOAD_COMPLETE:   (95, 95),
    ProcessingPhase.CLEANING_UP:       (98, 99),
    ProcessingPhase.COMPLETED:         (100, 100),
    ProcessingPhase.FAILED:            (0, 0),
}

_MODE_PHASE_WINDOWS: Dict[str, Dict[ProcessingPhase, Tuple[int, int]]] = {
    "vertical": {
        ProcessingPhase.VALIDATING:        (1, 4),
        ProcessingPhase.DOWNLOADING:       (4, 16),
        ProcessingPhase.DOWNLOAD_COMPLETE: (16, 16),
        ProcessingPhase.ANALYZING:         (16, 19),
        ProcessingPhase.DETECTING_FACES:   (19, 58),
        ProcessingPhase.ANALYSIS_COMPLETE: (58, 58),
        ProcessingPhase.PROCESSING:        (58, 60),
        ProcessingPhase.STABILIZING:       (60, 61),
        ProcessingPhase.CROPPING:          (61, 63),
        ProcessingPhase.ENCODING:          (63, 87),
        ProcessingPhase.ENCODING_COMPLETE: (87, 87),
        ProcessingPhase.UPLOADING:         (87, 95),
        ProcessingPhase.UPLOAD_COMPLETE:   (95, 95),
        ProcessingPhase.CLEANING_UP:       (98, 99),
    },
    "short_auto": {
        ProcessingPhase.VALIDATING:        (1, 3),
        ProcessingPhase.DOWNLOADING:       (3, 13),
        ProcessingPhase.DOWNLOAD_COMPLETE: (13, 13),
        ProcessingPhase.SELECTING_SEGMENT: (13, 31),
        ProcessingPhase.CUTTING_SEGMENT:   (31, 36),
        ProcessingPhase.SEGMENT_COMPLETE:  (36, 36),
        ProcessingPhase.ANALYZING:         (36, 38),
        ProcessingPhase.DETECTING_FACES:   (38, 62),
        ProcessingPhase.ANALYSIS_COMPLETE: (62, 62),
        ProcessingPhase.PROCESSING:        (62, 64),
        ProcessingPhase.STABILIZING:       (64, 65),
        ProcessingPhase.CROPPING:          (65, 66),
        ProcessingPhase.ENCODING:          (66, 87),
        ProcessingPhase.ENCODING_COMPLETE: (87, 87),
        ProcessingPhase.UPLOADING:         (87, 95),
        ProcessingPhase.UPLOAD_COMPLETE:   (95, 95),
        ProcessingPhase.CLEANING_UP:       (98, 99),
    },
    "short_manual": {
        ProcessingPhase.VALIDATING:        (1, 3),
        ProcessingPhase.DOWNLOADING:       (3, 14),
        ProcessingPhase.DOWNLOAD_COMPLETE: (14, 14),
        ProcessingPhase.SELECTING_SEGMENT: (14, 16),
        ProcessingPhase.CUTTING_SEGMENT:   (16, 23),
        ProcessingPhase.SEGMENT_COMPLETE:  (23, 23),
        ProcessingPhase.ANALYZING:         (23, 25),
        ProcessingPhase.DETECTING_FACES:   (25, 61),
        ProcessingPhase.ANALYSIS_COMPLETE: (61, 61),
        ProcessingPhase.PROCESSING:        (61, 63),
        ProcessingPhase.STABILIZING:       (63, 64),
        ProcessingPhase.CROPPING:          (64, 66),
        ProcessingPhase.ENCODING:          (66, 87),
        ProcessingPhase.ENCODING_COMPLETE: (87, 87),
        ProcessingPhase.UPLOADING:         (87, 95),
        ProcessingPhase.UPLOAD_COMPLETE:   (95, 95),
        ProcessingPhase.CLEANING_UP:       (98, 99),
    },
}

# Compatibilidad para código que todavía consulte el porcentaje base de fase.
PHASE_PROGRESS: Dict[ProcessingPhase, int] = {
    phase: bounds[0] for phase, bounds in _DEFAULT_PHASE_WINDOWS.items()
}
PHASE_PROGRESS[ProcessingPhase.COMPLETED] = 100

PHASE_MESSAGES: Dict[ProcessingPhase, str] = {
    ProcessingPhase.QUEUED:            "Video en cola para procesarse",
    ProcessingPhase.VALIDATING:        "Validando el video...",
    ProcessingPhase.DOWNLOADING:       "Descargando video desde Cloudinary...",
    ProcessingPhase.DOWNLOAD_COMPLETE: "Video descargado correctamente",
    ProcessingPhase.SELECTING_SEGMENT: "Buscando el mejor momento del video...",
    ProcessingPhase.CUTTING_SEGMENT:   "Preparando el segmento seleccionado...",
    ProcessingPhase.SEGMENT_COMPLETE:  "Segmento listo para procesar",
    ProcessingPhase.ANALYZING:         "Preparando el análisis del video...",
    ProcessingPhase.DETECTING_FACES:   "Analizando sujetos y encuadre...",
    ProcessingPhase.ANALYSIS_COMPLETE: "Análisis completado",
    ProcessingPhase.PROCESSING:        "Preparando el procesamiento final...",
    ProcessingPhase.STABILIZING:       "Estabilizando movimiento de cámara...",
    ProcessingPhase.CROPPING:          "Aplicando recorte inteligente...",
    ProcessingPhase.ENCODING:          "Generando video final...",
    ProcessingPhase.ENCODING_COMPLETE: "Video generado correctamente",
    ProcessingPhase.UPLOADING:         "Subiendo video procesado...",
    ProcessingPhase.UPLOAD_COMPLETE:   "Video subido correctamente",
    ProcessingPhase.CLEANING_UP:       "Finalizando...",
    ProcessingPhase.COMPLETED:         "Video procesado exitosamente",
    ProcessingPhase.FAILED:            "Error durante el procesamiento",
}

_NOTIFY_MIN_PROGRESS_DELTA    = 1
_NOTIFY_MIN_PROGRESS_INTERVAL = 0.45
_NOTIFY_HEARTBEAT_INTERVAL    = 2.0


class ProgressTracker:

    def __init__(self, job_id: str, update_callback: Optional[Callable] = None):
        self.job_id           = job_id
        self.update_callback  = update_callback

        self.current_phase:       Optional[ProcessingPhase]      = None
        self.progress_percentage: int                             = 0
        self.start_time:          Optional[datetime]              = None
        self.completion_time:     Optional[datetime]              = None
        self.phase_timestamps:    Dict[ProcessingPhase, datetime] = {}
        self.phases_completed:    list                            = []
        self.frames_processed:    int                             = 0
        self.total_frames:        Optional[int]                   = None
        self.metadata:            Dict[str, Any]                  = {}

        self._phase_windows: Dict[ProcessingPhase, Tuple[int, int]] = dict(_DEFAULT_PHASE_WINDOWS)
        self._last_notified_progress: int                       = -1
        self._last_notified_phase:    Optional[ProcessingPhase] = None
        self._last_notification_time: float                     = 0.0

    def start(self) -> None:
        self.start_time = datetime.utcnow()
        self.update_phase(ProcessingPhase.QUEUED)

    def configure_for_mode(self, processing_mode) -> None:
        value = getattr(processing_mode, "value", processing_mode)
        normalized = str(value or "").strip().lower()
        overrides = _MODE_PHASE_WINDOWS.get(normalized)
        self._phase_windows = dict(_DEFAULT_PHASE_WINDOWS)
        if overrides:
            self._phase_windows.update(overrides)
        self.metadata["progress_profile"] = normalized or "default"

    def update_phase(
        self,
        phase: ProcessingPhase,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        notify: bool = True,
    ) -> None:
        previous_phase = self.current_phase
        self.current_phase = phase
        self.phase_timestamps[phase] = datetime.utcnow()

        if phase == ProcessingPhase.COMPLETED:
            self.progress_percentage = 100
        elif phase == ProcessingPhase.FAILED:
            # Conservar cuánto alcanzó el job es más informativo que volver a 0%.
            self.progress_percentage = max(0, min(99, self.progress_percentage))
        else:
            phase_start, _ = self._phase_bounds(phase)
            # Nunca retroceder visualmente aunque una estrategia omita o reordene
            # fases auxiliares.
            self.progress_percentage = max(self.progress_percentage, phase_start)

        if phase not in self.phases_completed:
            self.phases_completed.append(phase)
        if metadata:
            self.metadata.update(metadata)

        phase_start, phase_end = self._phase_bounds(phase)
        self.metadata.update({
            "phase_start_progress": phase_start,
            "phase_end_progress": phase_end,
            "phase_progress": self._phase_local_percentage(),
        })

        msg = message or PHASE_MESSAGES.get(phase, str(phase))
        logger.info(
            "Progreso | job_id=%s | phase=%s | %d%% | %.1fs | %s",
            self.job_id,
            phase.value,
            self.progress_percentage,
            self._elapsed(),
            msg,
        )

        if notify and (previous_phase != phase or self._should_notify()):
            self._notify(msg)

    def update_phase_fraction(
        self,
        fraction: float,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.current_phase is None:
            return

        fraction = max(0.0, min(1.0, float(fraction)))
        phase_start, phase_end = self._phase_bounds(self.current_phase)
        target = int(round(phase_start + (phase_end - phase_start) * fraction))
        target = max(self.progress_percentage, min(phase_end, target))
        self.progress_percentage = target

        if metadata:
            self.metadata.update(metadata)
        self.metadata.update({
            "phase_start_progress": phase_start,
            "phase_end_progress": phase_end,
            "phase_progress": int(round(fraction * 100)),
        })

        if self._should_notify():
            self._notify(message)

    def update_work(
        self,
        completed: float,
        total: float,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if total <= 0:
            return
        self.update_phase_fraction(completed / total, message=message, metadata=metadata)

    def update_progress(self, percentage: int, message: Optional[str] = None) -> None:
        percentage = max(0, min(100, int(percentage)))
        # Progreso normal nunca debe retroceder. FAILED usa update_phase y conserva
        # el último valor alcanzado.
        self.progress_percentage = max(self.progress_percentage, percentage)
        if self._should_notify():
            self._notify(message)

    def update_frames(self, frames_processed: int, total_frames: int) -> None:
        self.frames_processed = frames_processed
        self.total_frames     = total_frames

        if total_frames <= 0:
            return

        self.update_work(
            frames_processed,
            total_frames,
            message=f"Analizando video: {frames_processed}/{total_frames}",
            metadata={
                "frames_processed": frames_processed,
                "total_frames": total_frames,
            },
        )

    def complete(self, success: bool = True) -> None:
        self.completion_time = datetime.utcnow()
        phase = ProcessingPhase.COMPLETED if success else ProcessingPhase.FAILED

        self.update_phase(phase, notify=False)

        logger.info(
            "Procesamiento %s | job_id=%s | total=%.2fs",
            "completado" if success else "falló",
            self.job_id,
            self._elapsed(),
        )
        self._notify(PHASE_MESSAGES[phase], force=True)

    def get_status(self) -> Dict[str, Any]:
        elapsed = self._elapsed()
        eta     = self._eta()
        return {
            "job_id":            self.job_id,
            "phase":             self.current_phase.value if self.current_phase else None,
            "progress":          self.progress_percentage,
            "remaining_progress": max(0, 100 - self.progress_percentage),
            "phase_progress":    self._phase_local_percentage(),
            "message":           PHASE_MESSAGES.get(self.current_phase, "Procesando..."),
            "elapsed_seconds":   elapsed,
            "elapsed_formatted": _fmt(elapsed),
            "eta_seconds":       eta,
            "eta_formatted":     _fmt(eta) if eta is not None else None,
            "start_time":        self.start_time.isoformat() if self.start_time else None,
            "frames_processed":  self.frames_processed,
            "total_frames":      self.total_frames,
            "phases_completed":  [p.value for p in self.phases_completed],
            "metadata":          self.metadata,
        }

    def _phase_bounds(self, phase: ProcessingPhase) -> Tuple[int, int]:
        return self._phase_windows.get(phase, _DEFAULT_PHASE_WINDOWS.get(phase, (0, 100)))

    def _phase_local_percentage(self) -> int:
        if self.current_phase is None:
            return 0
        start, end = self._phase_bounds(self.current_phase)
        if end <= start:
            return 100 if self.progress_percentage >= end else 0
        local = (self.progress_percentage - start) / (end - start)
        return int(round(max(0.0, min(1.0, local)) * 100))

    def _should_notify(self) -> bool:
        now = time.time()
        since_last = now - self._last_notification_time
        phase_changed = self.current_phase != self._last_notified_phase
        if phase_changed:
            return True

        progress_changed = (
            abs(self.progress_percentage - self._last_notified_progress)
            >= _NOTIFY_MIN_PROGRESS_DELTA
        )
        if progress_changed and since_last >= _NOTIFY_MIN_PROGRESS_INTERVAL:
            return True

        return since_last >= _NOTIFY_HEARTBEAT_INTERVAL

    def _notify(self, message: Optional[str] = None, force: bool = False) -> None:
        if not self.update_callback:
            return
        if not force and not self._should_notify():
            return
        try:
            data = self.get_status()
            if message:
                data["message"] = message
            self.update_callback(self.job_id, data)
            self._last_notified_progress = self.progress_percentage
            self._last_notified_phase = self.current_phase
            self._last_notification_time = time.time()
        except Exception as e:
            logger.error("Error en callback de progreso | job_id=%s | %s", self.job_id, e)

    def _elapsed(self) -> float:
        if not self.start_time:
            return 0.0
        return ((self.completion_time or datetime.utcnow()) - self.start_time).total_seconds()

    def _eta(self) -> Optional[float]:
        # Con progreso interno por fase esta estimación es mucho menos sesgada que
        # con simples checkpoints. Evitamos mostrar ETA demasiado pronto.
        if self.progress_percentage < 8 or not self.start_time:
            return None
        if self.progress_percentage >= 100:
            return 0.0
        elapsed = self._elapsed()
        return (elapsed / self.progress_percentage) * (100 - self.progress_percentage)


def _fmt(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


def create_progress_tracker(job_id: str, update_callback: Optional[Callable] = None) -> ProgressTracker:
    tracker = ProgressTracker(job_id, update_callback)
    tracker.start()
    return tracker
