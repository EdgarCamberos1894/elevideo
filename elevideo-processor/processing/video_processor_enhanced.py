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

    logger.info(
        "Procesando | %dx%d | %d frames @ %.2ffps | mode=%s | encoder=%s",
        width,
        height,
        total_frames,
        fps,
        config.CONVERSION_MODE["mode"],
        encoder,
    )

    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]
    ar       = width / height if height else 0

    if config.CONVERSION_MODE["mode"] == "full":
        return _process_full(input_path, config, encoder)

    if _VERTICAL_AR_LOW <= ar <= _VERTICAL_AR_HIGH:
        if width == output_w and height == output_h and not config.ENCODING_SETTINGS.get("apply_unsharp", False):
            logger.info("Video ya es vertical con dimensiones exactas - sin reprocesamiento")
            return input_path, _base_metrics(total_frames, reason="already_vertical_exact")
        logger.info("Video vertical - re-escalando al preset de salida")
        return _rescale_vertical(input_path, config, encoder)

    source_crop_w, source_crop_h = _calculate_source_crop_size(width, height, output_w, output_h)
    logger.info(
        "Smart crop geométrico | input=%dx%d | source_crop=%dx%d | output=%dx%d",
        width,
        height,
        source_crop_w,
        source_crop_h,
        output_w,
        output_h,
    )

    return _process_smart_crop(
        input_path,
        config,
        detector,
        stabilizer,
        use_multipass,
        encoder,
        total_frames,
        fps,
        width,
        source_crop_w,
        source_crop_h,
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

    crop_w = max(2, min(frame_w, crop_w - (crop_w % 2)))
    crop_h = max(2, min(frame_h, crop_h - (crop_h % 2)))
    return crop_w, crop_h


def _process_smart_crop(
    input_path,
    config,
    detector,
    stabilizer,
    use_multipass,
    encoder,
    total_frames,
    fps,
    frame_width,
    source_crop_w,
    source_crop_h,
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
    analysis_started = time.time()

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

    analysis_time  = time.time() - analysis_started
    total_analyzed = frames_processed
    faces_detected = len(quality_metrics)
    reliability    = faces_detected / total_analyzed if total_analyzed > 0 else 0.0

    logger.info(
        "Detección | frames_analizados=%d | con_cara=%d | reliability=%.1f%% | analysis=%.2fs",
        total_analyzed,
        faces_detected,
        reliability * 100,
        analysis_time,
    )

    if reliability <= _FACE_RELIABILITY_THRESHOLD or not positions:
        logger.warning("Sin detecciones de cara o posiciones vacías - cambiando a modo full")
        output_path, metrics = _process_full(input_path, config, encoder)
        metrics.update({
            "analysis_time":    analysis_time,
            "reliability_rate": reliability,
        })
        return output_path, metrics

    trajectory_smoothness = _calculate_trajectory_smoothness(positions, frame_width)
    avg_confidence = float(np.mean([m["confidence"] for m in quality_metrics])) if quality_metrics else 0.0
    avg_tracker_stability = float(np.mean([m["stability"] for m in quality_metrics])) if quality_metrics else 0.0
    overall_quality = (
        avg_confidence * 0.40
        + reliability * 0.35
        + trajectory_smoothness * 0.25
    )

    logger.info(
        "Calidad tracking | confidence=%.1f%% | detector_stability=%.1f%% | trajectory_smoothness=%.1f%% | overall=%.1f%%",
        avg_confidence * 100,
        avg_tracker_stability * 100,
        trajectory_smoothness * 100,
        overall_quality * 100,
    )

    output_path = _output_path(input_path, config.CONVERSION_MODE["mode"])
    encoding_started = time.time()
    success = crop_video_ultra(
        input_path,
        output_path,
        positions,
        config,
        encoder=encoder,
        source_crop_size=(source_crop_w, source_crop_h),
    )
    encoding_time = time.time() - encoding_started
    if not success:
        raise RuntimeError("Error en el encoding del video")

    metrics = {
        "total_frames":               total_frames,
        "frames_processed":           frames_processed,
        "keyframes":                  len(positions),
        "analysis_time":              analysis_time,
        "encoding_time":              encoding_time,
        "overall_quality":            overall_quality,
        "average_face_confidence":    avg_confidence,
        "detector_stability":         avg_tracker_stability,
        "trajectory_smoothness":      trajectory_smoothness,
        "reliability_rate":           reliability,
        "source_crop_width":          source_crop_w,
        "source_crop_height":         source_crop_h,
    }

    logger.info(
        "Smart crop completado | quality=%.1f%% | analysis=%.2fs | encoding=%.2fs",
        metrics["overall_quality"] * 100,
        analysis_time,
        encoding_time,
    )
    return output_path, metrics


def _process_full(input_path: str, config, encoder: str) -> Tuple[str, dict]:
    from processing.ffmpeg_ultra import crop_video_ultra

    cap    = cv2.VideoCapture(input_path)
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]

    if width == output_w and height == output_h and not config.ENCODING_SETTINGS.get("apply_unsharp", False):
        return input_path, _base_metrics(reason="already_exact")

    original_mode = config.CONVERSION_MODE.get("mode")
    config.CONVERSION_MODE["mode"] = "full"
    try:
        output = _output_path(input_path, "full")
        encoding_started = time.time()
        ok = crop_video_ultra(input_path, output, [], config, encoder=encoder)
        encoding_time = time.time() - encoding_started
        if not ok:
            raise RuntimeError("Error en el encoding del video en modo full")
        return output, {
            **_base_metrics(reason="full_mode"),
            "mode": "full",
            "encoding_time": encoding_time,
        }
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

    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "128k",
        output,
    ])

    encoding_started = time.time()
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error("Re-scale falló | stderr=%s", (e.stderr or "")[-500:])
        raise RuntimeError("Error al re-escalar el video")
    encoding_time = time.time() - encoding_started

    logger.info("Video re-escalado | output=%s | encoding=%.2fs", output, encoding_time)
    return output, {
        **_base_metrics(reason="vertical_rescale"),
        "mode": "vertical_rescale",
        "encoding_time": encoding_time,
    }


def _calculate_trajectory_smoothness(positions, frame_width: int) -> float:
    """Mide jitter de la trayectoria sin penalizar desplazamiento lateral legítimo."""
    if len(positions) < 3:
        return 1.0

    xs = np.asarray([float(position[1]) for position in positions], dtype=float)
    second_differences = np.diff(xs, n=2)
    if second_differences.size == 0:
        return 1.0

    jitter = float(np.percentile(np.abs(second_differences), 75))
    tolerance = max(6.0, frame_width * 0.015)
    return float(np.clip(1.0 - (jitter / tolerance), 0.0, 1.0))


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
    stem = Path(input_path).stem
    ts = time.strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "temp")
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, f"{stem}_vertical_{suffix}_{ts}.mp4")


def _base_metrics(total_frames: int = 0, reason: str = "") -> dict:
    return {
        "total_frames":     total_frames,
        "frames_processed": 0,
        "keyframes":        0,
        "analysis_time":    0.0,
        "encoding_time":    0.0,
        "overall_quality":  1.0,
        "skipped_reason":   reason,
    }
