import logging
import os
import subprocess
from typing import Callable, Optional

import cloudinary
import cloudinary.api
import cloudinary.uploader
import requests

from utils.ffmpeg_progress import probe_duration_seconds, run_ffmpeg_with_progress

logger = logging.getLogger(__name__)

_CLOUDINARY_LIMIT_MB = 100.0
_CHUNKED_THRESHOLD_MB = 50.0
_COMPRESSION_TARGET_RATIO = 0.90


class CloudinaryService:

    def __init__(self, cloud_name: str, api_key: str, api_secret: str, temp_dir: str = "/tmp/video_processing"):
        cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
        self.temp_dir = temp_dir
        self._ensure_temp_dir()
        logger.info("CloudinaryService inicializado | temp_dir=%s", temp_dir)

    def download_video(
        self,
        url: str,
        job_id: str,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        self._ensure_temp_dir()
        local_path = os.path.join(self.temp_dir, f"{job_id}_input.mp4")
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_bytes = int(response.headers.get("Content-Length") or 0)
            downloaded_bytes = 0
            last_fraction = -1.0

            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress_callback and total_bytes > 0:
                        fraction = min(1.0, downloaded_bytes / total_bytes)
                        if fraction >= 1.0 or fraction - last_fraction >= 0.01:
                            last_fraction = fraction
                            progress_callback(fraction)

            if progress_callback:
                progress_callback(1.0)

            logger.info("Video descargado | job_id=%s | size=%.2fMB",
                        job_id, os.path.getsize(local_path) / (1024 * 1024))
            return local_path
        except Exception as e:
            raise Exception(f"No se pudo descargar el video: {e}") from e

    def upload_video(
        self,
        local_path: str,
        job_id: str,
        folder: str = "processed_videos",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Archivo no encontrado: {local_path}")

        size_mb        = os.path.getsize(local_path) / (1024 * 1024)
        upload_path    = local_path
        was_compressed = False

        try:
            if size_mb > (_CLOUDINARY_LIMIT_MB - 5):
                upload_path = self._compress(
                    local_path,
                    _CLOUDINARY_LIMIT_MB * _COMPRESSION_TARGET_RATIO,
                    job_id,
                    progress_callback=(
                        (lambda fraction: progress_callback(fraction * 0.45))
                        if progress_callback
                        else None
                    ),
                )
                size_mb        = os.path.getsize(upload_path) / (1024 * 1024)
                was_compressed = True

            public_id = f"{folder}/{job_id}_output"
            use_chunked = size_mb > _CHUNKED_THRESHOLD_MB

            logger.info("Subiendo video | job_id=%s | size=%.2fMB | compressed=%s | chunked=%s",
                        job_id, size_mb, was_compressed, use_chunked)

            # El SDK de Cloudinary no expone callback de bytes enviados para
            # upload()/upload_large(). Reportamos progreso real de compresión si
            # aplica y dejamos el tramo de red como fase explícita/indeterminada.
            if progress_callback and was_compressed:
                progress_callback(0.45)

            if use_chunked:
                result = cloudinary.uploader.upload_large(
                    upload_path, resource_type="video", public_id=public_id,
                    overwrite=True, chunk_size=6_000_000, timeout=600, eager_async=False,
                )
            else:
                result = cloudinary.uploader.upload(
                    upload_path, resource_type="video", public_id=public_id,
                    overwrite=True, timeout=300, eager_async=False,
                )

            if progress_callback:
                progress_callback(1.0)

            video_url = result.get("secure_url")
            logger.info("Video subido | job_id=%s | url=%s", job_id, video_url)
            return video_url

        except Exception as e:
            raise Exception(f"No se pudo subir el video: {e}") from e
        finally:
            if was_compressed and os.path.exists(upload_path):
                try:
                    os.remove(upload_path)
                except Exception:
                    pass

    def upload_image(self, local_path: str, public_id: str, folder: str = "thumbnails") -> str:
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Archivo no encontrado: {local_path}")
        try:
            result = cloudinary.uploader.upload(
                local_path, resource_type="image",
                public_id=f"{folder}/{public_id}", overwrite=True,
            )
            image_url = result.get("secure_url")
            logger.info("Imagen subida | public_id=%s/%s | url=%s", folder, public_id, image_url)
            return image_url
        except Exception as e:
            raise Exception(f"No se pudo subir la imagen: {e}") from e

    def delete_local_files(self, job_id: str) -> None:
        if not os.path.isdir(self.temp_dir):
            logger.debug("Cleanup omitido: temp_dir no existe | job_id=%s | temp_dir=%s", job_id, self.temp_dir)
            return

        deleted = 0
        for filename in os.listdir(self.temp_dir):
            if filename.startswith(job_id) and filename.endswith(".mp4"):
                try:
                    os.remove(os.path.join(self.temp_dir, filename))
                    deleted += 1
                except Exception:
                    pass
        if deleted:
            logger.info("Cleanup completado | job_id=%s | archivos=%d", job_id, deleted)

    def get_video_info(self, cloudinary_url: str) -> Optional[dict]:
        try:
            public_id = cloudinary_url.split("/upload/")[1].rsplit(".", 1)[0]
            resource  = cloudinary.api.resource(public_id, resource_type="video")
            return {
                "format":     resource.get("format"),
                "duration":   resource.get("duration"),
                "width":      resource.get("width"),
                "height":     resource.get("height"),
                "size_bytes": resource.get("bytes"),
            }
        except Exception:
            logger.warning("No se pudo obtener info del video | url=%s", cloudinary_url)
            return None

    def _ensure_temp_dir(self) -> None:
        os.makedirs(self.temp_dir, exist_ok=True)

    def _compress(
        self,
        input_path: str,
        target_mb: float,
        job_id: str,
        max_attempts: int = 3,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> str:
        self._ensure_temp_dir()
        original_mb = os.path.getsize(input_path) / (1024 * 1024)
        crf_values   = [23, 26, 28]
        duration     = probe_duration_seconds(input_path)

        logger.warning("Video excede límite | job_id=%s | size=%.2fMB | target=%.2fMB - comprimiendo",
                       job_id, original_mb, target_mb)

        for attempt in range(max_attempts):
            crf         = crf_values[min(attempt, len(crf_values) - 1)]
            output_path = os.path.join(self.temp_dir, f"{job_id}_compressed_{attempt + 1}.mp4")

            try:
                attempt_base = attempt / max_attempts
                attempt_span = 1.0 / max_attempts

                run_ffmpeg_with_progress(
                    [
                        "ffmpeg", "-y", "-i", input_path,
                        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                        "-profile:v", "main", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart",
                        "-c:a", "aac", "-b:a", "96k",
                        output_path,
                    ],
                    duration_seconds=duration,
                    on_progress=(
                        (lambda fraction, base=attempt_base, span=attempt_span:
                            progress_callback(min(0.99, base + fraction * span)))
                        if progress_callback
                        else None
                    ),
                )

                result_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info("Intento %d/%d | job_id=%s | CRF=%d | size=%.2fMB (target=%.2fMB)",
                            attempt + 1, max_attempts, job_id, crf, result_mb, target_mb)

                if result_mb <= target_mb:
                    if progress_callback:
                        progress_callback(1.0)
                    return output_path

                os.remove(output_path)

            except Exception as e:
                logger.error("Compresión falló en intento %d | job_id=%s | %s", attempt + 1, job_id, e)
                if os.path.exists(output_path):
                    os.remove(output_path)

        raise Exception(
            f"No se pudo comprimir el video a {target_mb:.0f}MB tras {max_attempts} intentos. "
            f"Tamaño original: {original_mb:.2f}MB."
        )


def create_cloudinary_service() -> CloudinaryService:
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    api_key    = os.getenv("CLOUDINARY_API_KEY")
    api_secret = os.getenv("CLOUDINARY_API_SECRET")
    temp_dir   = os.getenv("CLOUDINARY_TEMP_DIR", "/tmp/video_processing")

    if not all([cloud_name, api_key, api_secret]):
        raise ValueError(
            "Faltan variables de entorno de Cloudinary: "
            "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET"
        )

    return CloudinaryService(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, temp_dir=temp_dir)
