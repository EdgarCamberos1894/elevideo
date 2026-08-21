import logging
import os
import time
from typing import Callable, Optional, Tuple

import core.config as config
from core.error_handler import ErrorHandler, ErrorContext, retry
from core.exceptions import VideoProcessingError
from models.schemas import (
    VideoProcessRequest,
    Platform,
    BackgroundMode,
    QualityLevel,
    ProcessingMode,
    QUALITY_TO_PRESET,
    BACKGROUND_TO_CONVERSION_MODE,
    BACKGROUND_TO_BLUR,
)
from processing.face_detector_enhanced import EnhancedFaceDetector
from processing.stabilization_enhanced import AdaptiveStabilizer
from services.strategies import get_strategy
from services.webhook_service import flush_progress, notify_progress
from storage.cloudinary_service import CloudinaryService
from utils.cancellation_manager import (
    get_cancellation_manager,
    JobCancelledException,
    CancellableProgressTracker,
    CancellableOperation,
)
from utils.optimization import HardwareAccelerationDetector, PerformanceMonitor
from utils.preview_generator import create_preview_generator
from utils.progress_tracker import ProgressTracker, ProcessingPhase

logger = logging.getLogger(__name__)


class VideoProcessingService:

    def __init__(self, cloudinary_service: CloudinaryService):
        self.cloudinary           = cloudinary_service
        self.progress_callback: Optional[Callable] = None
        self.cancellation_manager = get_cancellation_manager()
        self.preview_generator    = create_preview_generator(temp_dir=cloudinary_service.temp_dir)
        self.hw_encoder           = HardwareAccelerationDetector.get_optimized_ffmpeg_encoder()
        logger.info("VideoProcessingService inicializado | encoder=%s", self.hw_encoder)

    def set_progress_callback(self, callback: Callable) -> None:
        self.progress_callback = callback

    def _publish_progress(self, job_id: str, data: dict) -> None:
        if self.progress_callback:
            self.progress_callback(job_id, data)

        # Los estados terminales viajan por el webhook final con payload completo.
        # El progreso remoto solo cubre estados intermedios.
        if data.get("phase") not in ("completed", "failed"):
            notify_progress(job_id, data)

    def process_video(self, request: VideoProcessRequest, job_id: str) -> Tuple[str, dict]:
        t0                = time.time()
        local_input_path  = None
        local_output_path = None
        cleanup_done      = False
        perf              = PerformanceMonitor()

        base_tracker = ProgressTracker(job_id, update_callback=self._publish_progress)
        base_tracker.configure_for_mode(request.processing_mode)
        base_tracker.start()
        tracker = CancellableProgressTracker(base_tracker, self.cancellation_manager, job_id)

        def _cleanup(report_progress: bool = True):
            nonlocal cleanup_done
            if cleanup_done:
                return
            cleanup_done = True
            try:
                if report_progress:
                    tracker.update_phase(ProcessingPhase.CLEANING_UP)
                self.cloudinary.delete_local_files(job_id)
                if local_output_path and os.path.exists(local_output_path):
                    os.remove(local_output_path)
                if report_progress:
                    tracker.update_phase_fraction(1.0, "Archivos temporales liberados")
            except Exception as e:
                logger.warning("Error en cleanup | job_id=%s | %s", job_id, e)

        def _cleanup_after_error():
            _cleanup(report_progress=False)

        try:
            logger.info(
                "Iniciando job | job_id=%s | mode=%s | platform=%s | quality=%s",
                job_id,
                request.processing_mode.value,
                request.platform.value,
                request.quality.value,
            )

            tracker.update_phase(ProcessingPhase.VALIDATING)
            tracker.update_phase_fraction(1.0, "Solicitud validada")

            tracker.update_phase(ProcessingPhase.DOWNLOADING)
            t_dl = time.time()
            with CancellableOperation(self.cancellation_manager, job_id, "descarga"):
                with ErrorContext("descarga de video", cleanup=_cleanup_after_error, job_id=job_id):
                    local_input_path = self._download(
                        request.cloudinary_input_url,
                        job_id,
                        progress_callback=lambda fraction: tracker.update_phase_fraction(
                            fraction,
                            f"Descargando video... {int(round(fraction * 100))}%",
                        ),
                    )
            perf.record_metric("download_time", time.time() - t_dl)
            tracker.update_phase(ProcessingPhase.DOWNLOAD_COMPLETE)

            with ErrorContext("configuración", job_id=job_id):
                runtime_config = self._configure(request)

            pipeline_started = time.time()
            with ErrorContext("procesamiento de video", cleanup=_cleanup_after_error, job_id=job_id):
                strategy   = get_strategy(request.processing_mode)
                detector   = EnhancedFaceDetector(runtime_config)
                stabilizer = AdaptiveStabilizer(runtime_config)

                local_output_path, metrics = strategy.process(
                    local_input_path=local_input_path,
                    request=request,
                    config=runtime_config,
                    detector=detector,
                    stabilizer=stabilizer,
                    encoder=self.hw_encoder,
                    job_id=job_id,
                    tracker=tracker,
                )

                if "frames_processed" in metrics:
                    base_tracker.metadata["frames_processed"] = metrics["frames_processed"]
                    base_tracker.metadata["total_frames"] = metrics.get("total_frames")
                    perf.record_metric("frames_analyzed", metrics["frames_processed"])

            perf.record_metric("pipeline_time", time.time() - pipeline_started)
            perf.record_metric("analysis_time", metrics.get("analysis_time", 0.0))
            perf.record_metric("encoding_time", metrics.get("encoding_time", 0.0))
            tracker.update_phase(ProcessingPhase.ENCODING_COMPLETE)

            if self.cancellation_manager.is_cancelled(job_id):
                _cleanup_after_error()
                raise JobCancelledException(job_id)

            tracker.update_phase(ProcessingPhase.UPLOADING)
            t_up = time.time()
            with ErrorContext("subida a Cloudinary", cleanup=_cleanup_after_error, job_id=job_id):
                folder = f"processed_{request.platform.value}"
                if request.processing_mode in (ProcessingMode.short_auto, ProcessingMode.short_manual):
                    folder = f"{folder}/shorts"
                output_url = self._upload(
                    local_output_path,
                    job_id,
                    folder,
                    progress_callback=lambda fraction: tracker.update_phase_fraction(
                        fraction,
                        "Preparando y subiendo resultado...",
                    ),
                )
            perf.record_metric("upload_time", time.time() - t_up)
            tracker.update_phase(ProcessingPhase.UPLOAD_COMPLETE)

            # Los previews son trabajo real posterior a la subida principal. Se
            # mantiene el job en 95% hasta que miniatura y preview estén listos,
            # evitando mostrar 100% antes de terminar realmente.
            preview_started = time.time()
            thumbnail_url, preview_url = self._generate_previews(
                local_output_path,
                job_id,
                request.platform.value,
                request.processing_mode,
            )
            perf.record_metric("preview_time", time.time() - preview_started)

            output_duration = self._get_duration(local_output_path)

            _cleanup(report_progress=True)

            total_time = time.time() - t0
            metrics.update({
                "processing_total_time":   total_time,
                "thumbnail_url":           thumbnail_url,
                "preview_url":             preview_url,
                "processing_mode":         request.processing_mode.value,
                "output_duration_seconds": output_duration,
            })

            perf.record_metric("hw_acceleration_used", self.hw_encoder != "libx264")
            perf.record_metric("total_processing_time", total_time)
            perf.log_summary(job_id=job_id)
            tracker.complete(success=True)

            # Garantiza que ningún progreso asíncrono quede detrás del webhook final.
            flush_progress(job_id)

            logger.info(
                "Job completado | job_id=%s | mode=%s | tiempo=%.2fs | calidad=%.1f%% | url=%s",
                job_id,
                request.processing_mode.value,
                total_time,
                metrics.get("overall_quality", 0) * 100,
                output_url,
            )

            return output_url, metrics

        except JobCancelledException:
            logger.warning("Job cancelado | job_id=%s", job_id)
            try:
                _cleanup_after_error()
            except Exception:
                pass
            base_tracker.complete(success=False)
            flush_progress(job_id)
            self.cancellation_manager.remove_cancellation(job_id)
            raise

        except Exception as e:
            logger.exception("Error en procesamiento | job_id=%s", job_id)
            error_info = ErrorHandler.handle(e, job_id=job_id, operation="process_video")
            try:
                _cleanup_after_error()
            except Exception:
                pass
            tracker.complete(success=False)
            flush_progress(job_id)
            raise VideoProcessingError(error_info["user_message"]) from e

    def _get_duration(self, path: str) -> Optional[float]:
        """Lee la duración del video de salida con ffprobe. Retorna None si falla."""
        import json
        import subprocess

        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return float(json.loads(result.stdout)["format"]["duration"])
        except Exception as e:
            logger.warning("No se pudo obtener duración del output | path=%s | %s", path, e)
            return None

    def _generate_previews(
        self,
        local_output_path: str,
        job_id: str,
        platform: str,
        processing_mode: ProcessingMode,
    ) -> Tuple[Optional[str], Optional[str]]:
        try:
            thumbnail_path = self.preview_generator.generate_thumbnail(
                local_output_path,
                timestamp_seconds=1.0,
                width=480,
            )
            thumbnail_url = self.cloudinary.upload_image(
                thumbnail_path,
                f"{job_id}_thumb",
                folder=f"processed_{platform}/thumbnails",
            )

            preview_path = self.preview_generator.generate_preview_clip(
                local_output_path,
                duration_seconds=5,
                start_time=0.0,
            )
            preview_url = self.cloudinary.upload_video(
                preview_path,
                f"{job_id}_preview",
                folder=f"processed_{platform}/previews",
            )

            self.preview_generator.cleanup(thumbnail_path, preview_path)
            return thumbnail_url, preview_url
        except Exception as e:
            logger.warning("Error generando previews (no crítico) | job_id=%s | %s", job_id, e)
            return None, None

    @retry(max_attempts=3, initial_delay=2.0)
    def _download(
        self,
        url: str,
        job_id: str,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        return self.cloudinary.download_video(
            url,
            job_id,
            progress_callback=progress_callback,
        )

    @retry(max_attempts=3, initial_delay=2.0)
    def _upload(
        self,
        local_path: str,
        job_id: str,
        folder: str,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        return self.cloudinary.upload_video(
            local_path,
            job_id,
            folder,
            progress_callback=progress_callback,
        )

    def _configure(self, request: VideoProcessRequest):
        runtime_config = config.create_runtime_config()

        platform_preset = {
            Platform.tiktok:         "tiktok",
            Platform.instagram:      "instagram",
            Platform.youtube_shorts: "youtube_shorts",
        }
        config.apply_preset(platform_preset[request.platform], runtime=runtime_config)

        quality_overrides = {
            QualityLevel.fast:   {"sample_rate": 6, "use_multipass": False, "quality_preset": "fast"},
            QualityLevel.normal: {"sample_rate": 4, "use_multipass": False, "quality_preset": "balanced"},
            QualityLevel.high:   {"sample_rate": 3, "use_multipass": True,  "quality_preset": "high"},
        }
        overrides = quality_overrides[request.quality]
        runtime_config.PERFORMANCE_SETTINGS["sample_rate"] = overrides["sample_rate"]
        runtime_config.PERFORMANCE_SETTINGS["use_multipass"] = overrides["use_multipass"]
        runtime_config.ENCODING_SETTINGS["quality_preset"] = overrides["quality_preset"]

        conversion_mode = BACKGROUND_TO_CONVERSION_MODE[request.background_mode]
        runtime_config.CONVERSION_MODE["mode"] = conversion_mode
        if conversion_mode == "full":
            runtime_config.CONVERSION_MODE["modes"]["full"]["blur_background"] = BACKGROUND_TO_BLUR[request.background_mode]

        if request.advanced_options:
            adv = request.advanced_options

            if adv.apply_sharpening is not None:
                runtime_config.ENCODING_SETTINGS["apply_unsharp"] = adv.apply_sharpening

            if conversion_mode == "smart_crop":
                if adv.max_camera_speed is not None:
                    runtime_config.STABILIZATION["max_velocity_px_per_frame"] = adv.max_camera_speed
                if adv.use_rule_of_thirds is not None:
                    runtime_config.CROP_SETTINGS["use_rule_of_thirds"] = adv.use_rule_of_thirds
                if adv.edge_padding is not None:
                    runtime_config.CROP_SETTINGS["edge_padding"] = adv.edge_padding

        logger.info(
            "Config aplicada | preset=%s | mode=%s | sample_rate=1/%s | multipass=%s | encoding=%s",
            QUALITY_TO_PRESET[request.quality],
            runtime_config.CONVERSION_MODE["mode"],
            runtime_config.PERFORMANCE_SETTINGS["sample_rate"],
            runtime_config.PERFORMANCE_SETTINGS["use_multipass"],
            runtime_config.ENCODING_SETTINGS["quality_preset"],
        )

        return runtime_config


def create_video_service(cloudinary_service: CloudinaryService) -> VideoProcessingService:
    return VideoProcessingService(cloudinary_service)
