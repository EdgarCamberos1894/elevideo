import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_VERTICAL_AR_LOW = 0.53
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
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
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
    ar = width / height if height else 0

    if config.CONVERSION_MODE["mode"] == "full":
        return _process_full(input_path, config, encoder)

    if _VERTICAL_AR_LOW <= ar <= _VERTICAL_AR_HIGH:
        if (
            width == output_w
            and height == output_h
            and not config.ENCODING_SETTINGS.get("apply_unsharp", False)
        ):
            logger.info("Video ya es vertical con dimensiones exactas - sin reprocesamiento")
            return input_path, _base_metrics(total_frames, reason="already_vertical_exact")
        logger.info("Video vertical - re-escalando al preset de salida")
        return _rescale_vertical(input_path, config, encoder)

    source_crop_w, source_crop_h = _calculate_source_crop_size(
        width, height, output_w, output_h
    )
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


def _calculate_source_crop_size(
    frame_w: int,
    frame_h: int,
    output_w: int,
    output_h: int,
) -> Tuple[int, int]:
    """Calcula el mayor rectángulo con la proporción de salida que cabe en el frame original."""
    if frame_w <= 0 or frame_h <= 0 or output_w <= 0 or output_h <= 0:
        raise ValueError("Dimensiones de video inválidas para calcular el recorte")

    target_ar = output_w / output_h
    frame_ar = frame_w / frame_h

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
    from processing.subject_framing import SubjectFramer

    if use_multipass:
        from processing.stabilization_enhanced import MultiPassStabilizer
        multipass = MultiPassStabilizer(config)

    base_sample_rate = max(1, int(config.PERFORMANCE_SETTINGS["sample_rate"]))
    danger_sample_rate = max(1, (base_sample_rate + 1) // 2)
    positions = []
    quality_metrics = []
    framing_windows = []
    frame_number = 0
    next_sample_frame = 0
    danger_samples_remaining = 0
    frames_processed = 0
    dynamic_samples = 0
    predicted_frames = 0
    face_loss_events = 0
    comfort_zone_corrections = 0
    safe_zone_corrections = 0
    emergency_reframes = 0
    subject_edge_events = 0
    max_edge_pressure = 0.0
    was_predicted = False
    was_under_pressure = False
    analysis_started = time.time()
    subject_framer = SubjectFramer()

    cap = cv2.VideoCapture(input_path)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_number >= next_sample_frame:
                if danger_samples_remaining > 0 and danger_sample_rate < base_sample_rate:
                    dynamic_samples += 1

                ts = frame_number / fps if fps > 0 else 0
                faces = detector.detect(frame)
                face = detector.get_primary_face(faces)
                pressure_event = False

                if face:
                    subject = subject_framer.analyze(frame, face)
                    (
                        desired_x,
                        safe_min_x,
                        safe_max_x,
                        comfort_min_x,
                        comfort_max_x,
                    ) = _optimal_horizontal_composition(
                        face,
                        subject,
                        frame_width,
                        source_crop_w,
                        config,
                    )

                    q = face.get("quality")
                    is_predicted = bool(face.get("is_predicted", False))
                    if is_predicted:
                        predicted_frames += 1
                        if not was_predicted:
                            face_loss_events += 1
                    was_predicted = is_predicted

                    original_critical = is_predicted
                    if use_multipass:
                        multipass.add_position(ts, desired_x, q)
                        framing_windows.append((
                            ts,
                            safe_min_x,
                            safe_max_x,
                            comfort_min_x,
                            comfort_max_x,
                            original_critical,
                        ))
                        pressure = _position_pressure(
                            desired_x,
                            safe_min_x,
                            safe_max_x,
                            comfort_min_x,
                            comfort_max_x,
                            source_crop_w,
                        )
                        pressure_event = is_predicted or pressure >= 0.35
                        max_edge_pressure = max(max_edge_pressure, pressure)
                    else:
                        stabilized_x = (
                            stabilizer.stabilize(desired_x, q)
                            if hasattr(stabilizer, "stabilize")
                            else desired_x
                        )
                        (
                            protected_x,
                            corrected,
                            emergency,
                            comfort_corrected,
                            pressure,
                        ) = _protect_subject_position(
                            stabilized_x,
                            safe_min_x,
                            safe_max_x,
                            comfort_min_x,
                            comfort_max_x,
                            source_crop_w,
                        )
                        critical = original_critical or corrected or emergency
                        positions.append((ts, protected_x, critical))

                        if comfort_corrected:
                            comfort_zone_corrections += 1
                        if emergency:
                            safe_zone_corrections += 1
                            emergency_reframes += 1
                        pressure_event = corrected or is_predicted or pressure >= 0.35
                        max_edge_pressure = max(max_edge_pressure, pressure)

                    if pressure_event and not was_under_pressure:
                        subject_edge_events += 1
                    was_under_pressure = pressure_event

                    if pressure_event:
                        danger_samples_remaining = max(danger_samples_remaining, 4)
                    elif danger_samples_remaining > 0:
                        danger_samples_remaining -= 1

                    conf_val = q.confidence if q else face.get("confidence", 0.5)
                    stab_val = q.stability if q else 0.5
                    reliable_val = q.is_reliable if q else (conf_val >= 0.65)
                    quality_metrics.append({
                        "timestamp": ts,
                        "confidence": conf_val,
                        "stability": stab_val,
                        "is_reliable": reliable_val,
                        "is_predicted": is_predicted,
                        "pose_detected": bool(subject.get("pose_detected", False)),
                    })
                else:
                    was_predicted = False
                    if not was_under_pressure:
                        subject_edge_events += 1
                    was_under_pressure = True
                    danger_samples_remaining = max(danger_samples_remaining, 4)
                    center_x = max(0, (frame_width - source_crop_w) // 2)

                    if use_multipass:
                        last = (
                            multipass._buffer[-1]["position"]
                            if multipass._buffer
                            else center_x
                        )
                        multipass.add_position(ts, last, None)
                        framing_windows.append((
                            ts,
                            0,
                            max(0, frame_width - source_crop_w),
                            0,
                            max(0, frame_width - source_crop_w),
                            True,
                        ))
                    else:
                        fallback = positions[-1][1] if positions else center_x
                        sx = (
                            stabilizer.stabilize(None)
                            if hasattr(stabilizer, "stabilize")
                            else fallback
                        )
                        positions.append((ts, sx if sx is not None else fallback, True))

                frames_processed += 1
                next_interval = (
                    danger_sample_rate
                    if danger_samples_remaining > 0
                    else base_sample_rate
                )
                next_sample_frame = frame_number + max(1, next_interval)

            frame_number += 1
    finally:
        cap.release()
        subject_framer.close()

    if use_multipass:
        positions = multipass.process()
        (
            positions,
            multipass_comfort_corrections,
            multipass_safe_corrections,
            multipass_emergencies,
            multipass_pressure,
        ) = _protect_multipass_positions(
            positions,
            framing_windows,
            source_crop_w,
        )
        comfort_zone_corrections += multipass_comfort_corrections
        safe_zone_corrections += multipass_safe_corrections
        emergency_reframes += multipass_emergencies
        max_edge_pressure = max(max_edge_pressure, multipass_pressure)

    analysis_time = time.time() - analysis_started
    total_analyzed = frames_processed
    faces_detected = len(quality_metrics)
    reliability = faces_detected / total_analyzed if total_analyzed > 0 else 0.0
    tracking_stats = (
        detector.get_tracking_stats()
        if hasattr(detector, "get_tracking_stats")
        else {}
    )
    pose_stats = subject_framer.get_stats()
    critical_keyframes = sum(1 for position in positions if _position_is_critical(position))

    logger.info(
        "Detección | frames_analizados=%d | con_cara=%d | reliability=%.1f%% | "
        "predicted=%d | face_loss_events=%d | fallback=%d/%d | analysis=%.2fs",
        total_analyzed,
        faces_detected,
        reliability * 100,
        predicted_frames,
        face_loss_events,
        tracking_stats.get("fallback_successes", 0),
        tracking_stats.get("fallback_activations", 0),
        analysis_time,
    )

    logger.info(
        "Encuadre sujeto | pose=%d/%d | comfort_corrections=%d | safe_corrections=%d | "
        "emergency_reframes=%d | dynamic_samples=%d | critical_keyframes=%d | "
        "subject_edge_events=%d | max_edge_pressure=%.1f%%",
        pose_stats.get("pose_detections", 0),
        pose_stats.get("pose_attempts", 0),
        comfort_zone_corrections,
        safe_zone_corrections,
        emergency_reframes,
        dynamic_samples,
        critical_keyframes,
        subject_edge_events,
        max_edge_pressure * 100,
    )

    if reliability <= _FACE_RELIABILITY_THRESHOLD or not positions:
        logger.warning("Sin detecciones de cara o posiciones vacías - cambiando a modo full")
        output_path, metrics = _process_full(input_path, config, encoder)
        metrics.update({
            "analysis_time": analysis_time,
            "reliability_rate": reliability,
            "predicted_frames": predicted_frames,
            "face_loss_events": face_loss_events,
            "fallback_activations": tracking_stats.get("fallback_activations", 0),
            "fallback_successes": tracking_stats.get("fallback_successes", 0),
            "pose_attempts": pose_stats.get("pose_attempts", 0),
            "pose_detections": pose_stats.get("pose_detections", 0),
            "comfort_zone_corrections": comfort_zone_corrections,
            "safe_zone_corrections": safe_zone_corrections,
            "emergency_reframes": emergency_reframes,
            "dynamic_samples": dynamic_samples,
            "critical_keyframes": critical_keyframes,
            "subject_edge_events": subject_edge_events,
            "max_edge_pressure": max_edge_pressure,
        })
        return output_path, metrics

    trajectory_smoothness = _calculate_trajectory_smoothness(positions, frame_width)
    avg_confidence = (
        float(np.mean([m["confidence"] for m in quality_metrics]))
        if quality_metrics
        else 0.0
    )
    avg_tracker_stability = (
        float(np.mean([m["stability"] for m in quality_metrics]))
        if quality_metrics
        else 0.0
    )
    overall_quality = (
        avg_confidence * 0.40
        + reliability * 0.35
        + trajectory_smoothness * 0.25
    )

    logger.info(
        "Calidad tracking | confidence=%.1f%% | detector_stability=%.1f%% | "
        "trajectory_smoothness=%.1f%% | overall=%.1f%%",
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
        "total_frames": total_frames,
        "frames_processed": frames_processed,
        "keyframes": len(positions),
        "analysis_time": analysis_time,
        "encoding_time": encoding_time,
        "overall_quality": overall_quality,
        "average_face_confidence": avg_confidence,
        "detector_stability": avg_tracker_stability,
        "trajectory_smoothness": trajectory_smoothness,
        "reliability_rate": reliability,
        "source_crop_width": source_crop_w,
        "source_crop_height": source_crop_h,
        "predicted_frames": predicted_frames,
        "face_loss_events": face_loss_events,
        "mediapipe_detection_failures": tracking_stats.get("total_detection_failures", 0),
        "fallback_activations": tracking_stats.get("fallback_activations", 0),
        "fallback_successes": tracking_stats.get("fallback_successes", 0),
        "pose_attempts": pose_stats.get("pose_attempts", 0),
        "pose_detections": pose_stats.get("pose_detections", 0),
        "comfort_zone_corrections": comfort_zone_corrections,
        "safe_zone_corrections": safe_zone_corrections,
        "emergency_reframes": emergency_reframes,
        "dynamic_samples": dynamic_samples,
        "critical_keyframes": critical_keyframes,
        "subject_edge_events": subject_edge_events,
        "max_edge_pressure": max_edge_pressure,
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

    cap = cv2.VideoCapture(input_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]

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
    preset = config.ENCODING_SETTINGS["quality_preset"]
    s = config.ENCODING_SETTINGS["presets"][preset]

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
        "-c:v", encoder,
        "-preset", s["preset"],
        "-crf", str(s["crf"]),
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


def _optimal_horizontal_composition(
    face: dict,
    subject: dict,
    frame_w: int,
    crop_w: int,
    config,
):
    """Calcula un objetivo centrado en la persona y ventanas segura/cómoda."""
    cs = config.CROP_SETTINGS
    max_x = max(0, frame_w - crop_w)
    if max_x == 0:
        return 0, 0, 0, 0, 0

    requested_padding = max(0, int(cs.get("edge_padding", 15)))
    safe_min_x, safe_max_x = _subject_safe_window(
        face,
        subject,
        frame_w,
        crop_w,
        requested_padding,
    )

    subject_center = float(subject.get("center_x", face["center"][0]))
    ratio = subject_center / frame_w if frame_w else 0.5

    if cs.get("use_rule_of_thirds", False):
        if ratio < 0.42:
            target_ratio = 0.46
        elif ratio > 0.58:
            target_ratio = 0.54
        else:
            target_ratio = 0.50
    else:
        target_ratio = 0.50

    comfort_min_x = max(safe_min_x, int(round(subject_center - crop_w * 0.56)))
    comfort_max_x = min(safe_max_x, int(round(subject_center - crop_w * 0.44)))
    if comfort_min_x > comfort_max_x:
        centered = int(np.clip(subject_center - crop_w * 0.50, safe_min_x, safe_max_x))
        comfort_min_x = centered
        comfort_max_x = centered

    desired_x = int(np.clip(
        subject_center - crop_w * target_ratio,
        comfort_min_x,
        comfort_max_x,
    ))
    return desired_x, safe_min_x, safe_max_x, comfort_min_x, comfort_max_x


def _subject_safe_window(
    face: dict,
    subject: dict,
    frame_w: int,
    crop_w: int,
    edge_padding: int,
) -> Tuple[int, int]:
    """Prioriza cara completa e intenta conservar también el torso visible."""
    face_safe_min, face_safe_max = _face_safe_window(
        face,
        frame_w,
        crop_w,
        edge_padding,
    )

    max_crop_x = max(0, frame_w - crop_w)
    if max_crop_x == 0:
        return 0, 0

    subject_left = float(np.clip(subject.get("left", face["bbox"][0]), 0, frame_w))
    subject_right = float(np.clip(
        subject.get("right", face["bbox"][0] + face["bbox"][2]),
        0,
        frame_w,
    ))
    subject_width = max(1.0, subject_right - subject_left)
    subject_margin = max(
        float(edge_padding),
        crop_w * 0.04,
        min(crop_w * 0.10, subject_width * 0.08),
    )

    subject_min = max(0, int(round(subject_right + subject_margin - crop_w)))
    subject_max = min(max_crop_x, int(round(subject_left - subject_margin)))

    if subject_min <= subject_max:
        combined_min = max(face_safe_min, subject_min)
        combined_max = min(face_safe_max, subject_max)
        if combined_min <= combined_max:
            return int(combined_min), int(combined_max)

    return int(face_safe_min), int(face_safe_max)


def _face_safe_window(
    face: dict,
    frame_w: int,
    crop_w: int,
    edge_padding: int,
) -> Tuple[int, int]:
    face_x, _, face_w, _ = face["bbox"]
    max_crop_x = max(0, frame_w - crop_w)
    if max_crop_x == 0:
        return 0, 0

    face_left = max(0, int(face_x))
    face_right = min(frame_w, int(face_x + face_w))
    margin = max(
        int(edge_padding),
        int(face_w * 0.25),
        int(crop_w * 0.08),
    )

    safe_min = max(0, face_right + margin - crop_w)
    safe_max = min(max_crop_x, face_left - margin)
    if safe_min <= safe_max:
        return int(safe_min), int(safe_max)

    face_center = (face_left + face_right) / 2.0
    best_effort = int(np.clip(face_center - crop_w / 2.0, 0, max_crop_x))
    return best_effort, best_effort


def _protect_subject_position(
    position: float,
    safe_min_x: int,
    safe_max_x: int,
    comfort_min_x: int,
    comfort_max_x: int,
    crop_w: int,
):
    """Mantiene primero seguridad facial y después busca una zona visualmente cómoda."""
    position = float(position)
    safe_min_x = float(safe_min_x)
    safe_max_x = float(safe_max_x)
    comfort_min_x = float(np.clip(comfort_min_x, safe_min_x, safe_max_x))
    comfort_max_x = float(np.clip(comfort_max_x, safe_min_x, safe_max_x))

    if position < safe_min_x:
        overflow = safe_min_x - position
        pressure = min(1.0, overflow / max(1.0, crop_w * 0.10))
        return safe_min_x, True, True, False, pressure

    if position > safe_max_x:
        overflow = position - safe_max_x
        pressure = min(1.0, overflow / max(1.0, crop_w * 0.10))
        return safe_max_x, True, True, False, pressure

    if position < comfort_min_x:
        gap = comfort_min_x - position
        pressure = min(1.0, gap / max(1.0, crop_w * 0.18))
        step = min(gap, max(10.0, crop_w * (0.08 + 0.10 * pressure)))
        return position + step, True, False, True, pressure

    if position > comfort_max_x:
        gap = position - comfort_max_x
        pressure = min(1.0, gap / max(1.0, crop_w * 0.18))
        step = min(gap, max(10.0, crop_w * (0.08 + 0.10 * pressure)))
        return position - step, True, False, True, pressure

    return position, False, False, False, 0.0


def _position_pressure(
    position: float,
    safe_min_x: int,
    safe_max_x: int,
    comfort_min_x: int,
    comfort_max_x: int,
    crop_w: int,
) -> float:
    if position < safe_min_x:
        return min(1.0, (safe_min_x - position) / max(1.0, crop_w * 0.10))
    if position > safe_max_x:
        return min(1.0, (position - safe_max_x) / max(1.0, crop_w * 0.10))
    if position < comfort_min_x:
        return min(1.0, (comfort_min_x - position) / max(1.0, crop_w * 0.18))
    if position > comfort_max_x:
        return min(1.0, (position - comfort_max_x) / max(1.0, crop_w * 0.18))
    return 0.0


def _protect_multipass_positions(positions, framing_windows, crop_w: int):
    if not positions or not framing_windows:
        return positions, 0, 0, 0, 0.0

    protected_positions = []
    comfort_corrections = 0
    safe_corrections = 0
    emergencies = 0
    max_pressure = 0.0

    for index, position_data in enumerate(positions):
        timestamp, position = position_data[0], position_data[1]
        window = framing_windows[index] if index < len(framing_windows) else framing_windows[-1]
        (
            _,
            safe_min_x,
            safe_max_x,
            comfort_min_x,
            comfort_max_x,
            original_critical,
        ) = window
        (
            protected,
            corrected,
            emergency,
            comfort_corrected,
            pressure,
        ) = _protect_subject_position(
            position,
            safe_min_x,
            safe_max_x,
            comfort_min_x,
            comfort_max_x,
            crop_w,
        )
        critical = bool(original_critical or corrected or emergency)
        protected_positions.append((timestamp, protected, critical))

        if comfort_corrected:
            comfort_corrections += 1
        if emergency:
            safe_corrections += 1
            emergencies += 1
        max_pressure = max(max_pressure, pressure)

    return (
        protected_positions,
        comfort_corrections,
        safe_corrections,
        emergencies,
        max_pressure,
    )


def _position_is_critical(position) -> bool:
    return len(position) > 2 and bool(position[2])


def _output_path(input_path: str, suffix: str) -> str:
    stem = Path(input_path).stem
    ts = time.strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "temp",
    )
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, f"{stem}_vertical_{suffix}_{ts}.mp4")


def _base_metrics(total_frames: int = 0, reason: str = "") -> dict:
    return {
        "total_frames": total_frames,
        "frames_processed": 0,
        "keyframes": 0,
        "analysis_time": 0.0,
        "encoding_time": 0.0,
        "overall_quality": 1.0,
        "skipped_reason": reason,
    }
