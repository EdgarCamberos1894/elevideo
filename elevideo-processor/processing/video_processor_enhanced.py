import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_VERTICAL_AR_LOW  = 0.53
_VERTICAL_AR_HIGH = 0.59
_TARGET_AR        = 9 / 16
_FACE_RELIABILITY_THRESHOLD = 0.0


def process_video_enhanced(
    input_path: str,
    config,
    detector,
    stabilizer,
    use_multipass: bool = True,
    encoder: str = "libx264",
) -> Tuple[str, dict]:
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"No se pudo abrir el video: {input_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps          = cap.get(cv2.CAP_PROP_FPS)
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    logger.info("Procesando | %dx%d | %d frames @ %.2ffps | mode=%s | encoder=%s",
                width, height, total_frames, fps, config.CONVERSION_MODE["mode"], encoder)

    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]
    ar       = width / height if height else 0

    # Los modos full (barras negras / blur) siempre pasan por su pipeline para respetar
    # el fondo elegido y la nitidez, incluso si el video ya es vertical.
    if config.CONVERSION_MODE["mode"] == "full":
        return _process_full(input_path, config, encoder)

    # Un video ya 9:16 no necesita seguimiento horizontal. Solo se reescala si hace falta.
    if _VERTICAL_AR_LOW <= ar <= _VERTICAL_AR_HIGH:
        if width == output_w and height == output_h and not config.ENCODING_SETTINGS.get("apply_unsharp", False):
            logger.info("Video ya es vertical con dimensiones exactas — sin reprocesamiento")
            return input_path, _base_metrics(total_frames, reason="already_vertical_exact")
        logger.info("Video vertical — re-escalando al preset de salida")
        return _rescale_vertical(input_path, config, encoder)

    source_crop_w, source_crop_h = _calculate_source_crop_size(width, height, output_w, output_h)
    logger.info(
        "Smart crop geométrico | input=%dx%d | source_crop=%dx%d | output=%dx%d",
        width, height, source_crop_w, source_crop_h, output_w, output_h,
    )

    return _process_smart_crop(
        input_path, config, detector, stabilizer,
        use_multipass, encoder, total_frames, fps,
        width, source_crop_w, source_crop_h,
    )


def _calculate_source_crop_size(frame_w: int, frame_h: int, output_w: int, output_h: int) -> Tuple[int, int]:
    """Calcula el mayor rectángulo con la proporción de salida que cabe en el frame original."""
    if frame_w <= 0 or frame_h <= 0 or output_w <= 0 or output_h <= 0:
        raise ValueError("Dimensiones de video inválidas para calcular el recorte")

    target_ar = output_w / output_h
    frame_ar  = frame_w / frame_h

    if frame_ar >= target_ar:
        crop_h = frame_h
        crop_w = int(round(crop_h * target_ar))
    else:
        crop_w = frame_w
        crop_h = int(round(crop_w / target_ar))

    # YUV420 funciona de forma más predecible con dimensiones pares.
    crop_w = max(2, min(frame_w, crop_w - (crop_w % 2)))
    crop_h = max(2, min(frame_h, crop_h - (crop_h % 2)))
    return crop_w, crop_h


def _process_smart_crop(
    input_path, config, detector, stabilizer, use_multipass,
    encoder, total_frames, fps, frame_width, source_crop_w, source_crop_h,
) -> Tuple[str, dict]:
    from processing.ffmpeg_ultra import crop_video_ultra

    if use_multipass:
        from processing.stabilization_enhanced import MultiPassStabilizer
        multipass = MultiPassStabilizer(config)

    sample_rate      = config.PERFORMANCE_SETTINGS["sample_rate"]
    positions        = []
    quality_metrics  = []
    frame_number     = 0
    frames_processed = 0
    t0               = time.time()

    cap = cv2.VideoCapture(input_path)
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_number % sample_rate == 0:
            ts    = frame_number / fps if fps > 0 else 0
            faces = detector.detect(frame)
            face  = detector.get_primary_face(faces)

            if face:
                crop_x = _optimal_horizontal_composition(face, frame_width, source_crop_w, config)
                q = face.get("quality")
                if use_multipass:
                    multipass.add_position(ts, crop_x, q)
                else:
                    sx = stabilizer.stabilize(crop_x, q) if hasattr(stabilizer, "stabilize") else crop_x
                    positions.append((ts, sx))
                conf_val     = q.confidence  if q else face.get("confidence", 0.5)
                stab_val     = q.stability   if q else 0.5
                reliable_val = q.is_reliable if q else (conf_val >= 0.65)
                quality_metrics.append({
                    "timestamp":   ts,
                    "confidence":  conf_val,
                    "stability":   stab_val,
                    "is_reliable": reliable_val,
                })
            else:
                center_x = max(0, (frame_width - source_crop_w) // 2)
                if use_multipass:
                    last = multipass._buffer[-1]["position"] if multipass._buffer else center_x
                    multipass.add_position(ts, last, None)
                else:
                    fallback = positions[-1][1] if positions else center_x
                    sx = stabilizer.stabilize(None) if hasattr(stabilizer, "stabilize") else fallback
                    positions.append((ts, sx if sx is not None else fallback))

            frames_processed += 1

        frame_number += 1
    cap.release()

    if use_multipass:
        positions = multipass.process()

    total_analyzed = frames_processed
    faces_detected = len(quality_metrics)
    reliability    = faces_detected / total_analyzed if total_analyzed > 0 else 0.0

    logger.info("Detección | frames_analizados=%d | con_cara=%d | reliability=%.1f%%",
                total_analyzed, faces_detected, reliability * 100)

    if reliability <= _FACE_RELIABILITY_THRESHOLD or not positions:
        logger.warning("Sin detecciones de cara o posiciones vacías — cambiando a modo full")
        return _process_full(input_path, config, encoder)

    output_path = _output_path(input_path, config.CONVERSION_MODE["mode"])
    success = crop_video_ultra(
        input_path,
        output_path,
        positions,
        config,
        encoder=encoder,
        source_crop_size=(source_crop_w, source_crop_h),
    )
    if not success:
        raise RuntimeError("Error en el encoding del video")

    metrics = {
        "total_frames":       total_frames,
        "frames_processed":   frames_processed,
        "keyframes":          len(positions),
        "analysis_time":      time.time() - t0,
        "overall_quality":    1.0,
        "reliability_rate":   reliability,
        "source_crop_width":  source_crop_w,
        "source_crop_height": source_crop_h,
    }
    if quality_metrics:
        avg_c = np.mean([m["confidence"] for m in quality_metrics])
        avg_s = np.mean([m["stability"]  for m in quality_metrics])
        metrics["overall_quality"] = avg_c * 0.4 + avg_s * 0.3 + reliability * 0.3

    logger.info("Smart crop completado | quality=%.1f%% | time=%.2fs",
                metrics["overall_quality"] * 100, metrics["analysis_time"])
    return output_path, metrics


def _process_full(input_path: str, config, encoder: str) -> Tuple[str, dict]:
    from processing.ffmpeg_ultra import crop_video_ultra

    cap    = cv2.VideoCapture(input_path)
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]

    # Si ya coincide exactamente y no hay nitidez adicional, no hace falta recodificar.
    if (
        width == output_w
        and height == output_h
        and not config.ENCODING_SETTINGS.get("apply_unsharp", False)
    ):
        return input_path, _base_metrics(reason="already_exact")

    original_mode = config.CONVERSION_MODE.get("mode")
    config.CONVERSION_MODE["mode"] = "full"
    try:
        output = _output_path(input_path, "full")
        ok = crop_video_ultra(input_path, output, [], config, encoder=encoder)
        if not ok:
            raise RuntimeError("Error en el encoding del video en modo full")
        return output, {**_base_metrics(reason="full_mode"), "mode": "full"}
    finally:
        config.CONVERSION_MODE["mode"] = original_mode


def _rescale_vertical(input_path: str, config, encoder: str) -> Tuple[str, dict]:
    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]
    preset   = config.ENCODING_SETTINGS["quality_preset"]
    s        = config.ENCODING_SETTINGS["presets"][preset]

    filters = [
        f"scale={output_w}:{output_h}:force_original_aspect_ratio=decrease",
        f"pad={output_w}:{output_h}:(ow-iw)/2:(oh-ih)/2:color=black",
    ]
    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        filters.append(f"unsharp={config.ENCODING_SETTINGS['unsharp_params']}")

    output = _output_path(input_path, "rescaled")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", ",".join(filters),
        "-c:v", encoder, "-preset", s["preset"], "-crf", str(s["crf"]),
    ]

    if encoder == "libx264":
        cmd.extend(["-profile:v", s.get("profile", "high")])

    cmd.extend(["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", output])

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error("Re-scale falló | stderr=%s", (e.stderr or "")[-500:])
        raise RuntimeError("Error al re-escalar el video")

    logger.info("Video re-escalado | output=%s", output)
    return output, {**_base_metrics(reason="vertical_rescale"), "mode": "vertical_rescale"}


def _optimal_horizontal_composition(face: dict, frame_w: int, crop_w: int, config) -> int:
    cx, _ = face["center"]
    cs    = config.CROP_SETTINGS

    max_x = max(0, frame_w - crop_w)
    if max_x == 0:
        return 0

    if cs.get("use_rule_of_thirds", False):
        ratio  = cx / frame_w if frame_w else 0.5
        offset = cs.get("thirds_offset_factor", 0.15)
        if ratio < 0.35:
            target = crop_w * (0.33 - offset)
        elif ratio > 0.65:
            target = crop_w * (0.67 + offset)
        else:
            target = crop_w * 0.5
    else:
        target = crop_w * 0.5

    requested_padding = max(0, int(cs.get("edge_padding", 15)))
    effective_padding = min(requested_padding, max_x // 2)
    min_x             = effective_padding
    max_allowed_x     = max(min_x, max_x - effective_padding)

    return int(np.clip(cx - target, min_x, max_allowed_x))


def _output_path(input_path: str, suffix: str) -> str:
    stem      = Path(input_path).stem
    ts        = time.strftime("%Y%m%d_%H%M%S")
    temp_dir  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, f"{stem}_vertical_{suffix}_{ts}.mp4")


def _base_metrics(total_frames: int = 0, reason: str = "") -> dict:
    return {
        "total_frames":     total_frames,
        "frames_processed": 0,
        "keyframes":        0,
        "analysis_time":    0,
        "overall_quality":  1.0,
        "skipped_reason":   reason,
    }
