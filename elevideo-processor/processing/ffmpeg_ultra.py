import json
import logging
import math
import os
import subprocess
import tempfile
from typing import List, Optional, Tuple

from utils.encoding_profiles import (
    build_video_encoding_args,
    describe_rate_control,
    get_audio_bitrate,
    get_pixel_format,
)
from utils.ffmpeg_progress import probe_duration_seconds, run_ffmpeg_with_progress
from utils.processing_progress_context import get_active_progress_tracker
from utils.progress_tracker import ProcessingPhase

logger = logging.getLogger(__name__)


def crop_video_ultra(
    input_path: str,
    output_path: str,
    positions: list,
    config,
    encoder="libx264",
    source_crop_size: Optional[Tuple[int, int]] = None,
) -> bool:
    mode = config.CONVERSION_MODE["mode"]
    mode_config = config.CONVERSION_MODE["modes"][mode]
    logger.info("Modo de conversión: %s | encoder: %s", mode.upper(), encoder)

    if mode == "full":
        return _process_full(input_path, output_path, config, mode_config, encoder)
    return _process_smart_crop(
        input_path,
        output_path,
        positions,
        config,
        encoder,
        source_crop_size,
    )


def _append_unsharp(vf: str, config) -> str:
    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        return f"{vf},unsharp={config.ENCODING_SETTINGS['unsharp_params']}"
    return vf


def _process_full(input_path, output_path, config, mode_config, encoder) -> bool:
    w, h = mode_config["width"], mode_config["height"]

    if mode_config.get("blur_background", False):
        if config.ENCODING_SETTINGS.get("apply_unsharp", False):
            composite_tail = (
                f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2[composite];"
                f"[composite]unsharp={config.ENCODING_SETTINGS['unsharp_params']}[vout]"
            )
        else:
            composite_tail = "[blurred][scaled]overlay=(W-w)/2:(H-h)/2[vout]"

        vf = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma=20[blurred];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[scaled];"
            f"{composite_tail}"
        )
        logger.info("Usando fondo difuminado")
        return _encode(
            input_path,
            output_path,
            vf,
            config,
            encoder,
            filter_complex=True,
        )

    bg = mode_config.get("background_color", "black")
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg}"
    )
    logger.info("Usando letterbox | fondo=%s", bg)
    return _encode(
        input_path,
        output_path,
        _append_unsharp(vf, config),
        config,
        encoder,
    )


def _process_smart_crop(
    input_path,
    output_path,
    positions,
    config,
    encoder,
    source_crop_size,
) -> bool:
    from processing.subject_framing import clear_hybrid_profile, get_hybrid_profile

    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]
    crop_w, crop_h = source_crop_size or (output_w, output_h)
    positions = [_normalize_position(position) for position in positions]

    profile = get_hybrid_profile()
    clear_hybrid_profile()

    if config.KEYFRAME_SETTINGS.get("optimize_keyframes", False) and positions:
        min_move = config.KEYFRAME_SETTINGS.get("min_movement_threshold", 5)
        optimized = [positions[0]]
        for position in positions[1:-1]:
            if position[2] or abs(position[1] - optimized[-1][1]) > min_move:
                optimized.append(position)
        if len(positions) > 1:
            last = positions[-1]
            if optimized[-1][0] != last[0]:
                optimized.append(last)
            elif last[2] and not optimized[-1][2]:
                optimized[-1] = last

        logger.info(
            "Keyframes: %d → %d | críticos=%d",
            len(positions),
            len(optimized),
            sum(1 for position in optimized if position[2]),
        )
        positions = optimized

    hybrid_viewports, hybrid_stats = _prepare_hybrid_viewports(
        profile,
        positions,
        crop_w,
    )

    if hybrid_viewports and positions:
        logger.info(
            "Smart crop híbrido | activations=%d | zoom_frames=%d | "
            "required_max=%.0fpx | viewport_max=%.0fpx",
            hybrid_stats["hybrid_activations"],
            hybrid_stats["adaptive_zoom_frames"],
            hybrid_stats["max_required_width"],
            hybrid_stats["max_viewport_width"],
        )
        hybrid_ok = _process_hybrid_smart_crop(
            input_path,
            output_path,
            positions,
            hybrid_viewports,
            config,
            encoder,
            crop_w,
            crop_h,
            output_w,
            output_h,
        )
        if hybrid_ok:
            return True
        logger.warning(
            "Render híbrido falló; reintentando automáticamente con Smart Crop normal"
        )

    return _process_standard_smart_crop(
        input_path,
        output_path,
        positions,
        config,
        encoder,
        crop_w,
        crop_h,
        output_w,
        output_h,
    )


def _process_standard_smart_crop(
    input_path,
    output_path,
    positions,
    config,
    encoder,
    crop_w: int,
    crop_h: int,
    output_w: int,
    output_h: int,
) -> bool:
    if not positions:
        crop_vf = f"crop={crop_w}:{crop_h}:(iw-{crop_w})/2:(ih-{crop_h})/2"
    else:
        positions = sorted(positions, key=lambda position: position[0])
        expr = _build_lerp(
            positions,
            config.STABILIZATION.get("use_easing", False),
            max_keyframes=int(config.KEYFRAME_SETTINGS.get("max_keyframes", 80)),
        )
        crop_vf = f"crop={crop_w}:{crop_h}:x='{expr}':y=(ih-{crop_h})/2"

    filters = [crop_vf, f"scale={output_w}:{output_h}:flags=lanczos"]
    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        filters.append(f"unsharp={config.ENCODING_SETTINGS['unsharp_params']}")

    return _encode(input_path, output_path, ",".join(filters), config, encoder)


def _process_hybrid_smart_crop(
    input_path,
    output_path,
    positions,
    viewports,
    config,
    encoder,
    crop_w: int,
    crop_h: int,
    output_w: int,
    output_h: int,
) -> bool:
    """
    Render híbrido robusto con geometría fija por segmento.

    FFmpeg en Windows puede volverse inestable cuando `scale` cambia el tamaño
    de salida en cada frame. Aquí el zoom se cuantiza en pequeños escalones y
    cada tramo usa dimensiones fijas; todos los tramos terminan en 1080x1920 y
    se concatenan después.
    """
    source_w, source_h = _probe_video_size(input_path)
    if source_w <= 0 or source_h <= 0:
        logger.warning("No se pudo obtener tamaño fuente para render híbrido")
        return False

    positions = sorted(positions, key=lambda position: position[0])
    viewports = sorted(viewports, key=lambda viewport: viewport[0])
    max_keyframes = int(config.KEYFRAME_SETTINGS.get("max_keyframes", 80))

    center_positions = [
        (timestamp, x + crop_w / 2.0, critical)
        for timestamp, x, critical in positions
    ]
    center_expr = _build_lerp(
        center_positions,
        False,
        max_keyframes=max_keyframes,
    )

    segments, quant_step = _build_hybrid_segments(
        viewports,
        crop_w,
        source_w,
        max_segments=28,
    )
    if not segments:
        return False

    logger.info(
        "Render híbrido estable | segments=%d | zoom_step=%.1f%% | source=%dx%d",
        len(segments),
        quant_step * 100,
        source_w,
        source_h,
    )

    graph_parts = []
    outputs = []
    for index, segment in enumerate(segments):
        start = segment["start"]
        end = segment["end"]
        viewport_w = segment["viewport_width"]
        trim = f"trim=start={start:.6f}"
        if end is not None:
            trim += f":end={end:.6f}"

        source_label = f"segsrc{index}"
        output_label = f"segout{index}"
        graph_parts.append(f"[0:v]{trim}[{source_label}];")

        if viewport_w <= crop_w * 1.015:
            left_expr = (
                f"max(0,min(iw-{float(crop_w):.3f},"
                f"({center_expr})-{float(crop_w) / 2.0:.3f}))"
            )
            graph_parts.append(
                f"[{source_label}]crop={crop_w}:{crop_h}:x='{left_expr}':"
                f"y=(ih-{crop_h})/2,"
                f"scale={output_w}:{output_h}:flags=lanczos,"
                f"setsar=1,setpts=PTS-STARTPTS[{output_label}];"
            )
        else:
            viewport_w = float(min(source_w, max(crop_w, viewport_w)))
            scaled_w = _even_dimension(source_w * output_w / viewport_w)
            scaled_h = _even_dimension(crop_h * output_w / viewport_w)
            left_expr = (
                f"max(0,min({float(source_w) - viewport_w:.3f},"
                f"({center_expr})-{viewport_w / 2.0:.3f}))"
            )
            overlay_x = f"-({left_expr})*{float(output_w) / viewport_w:.10f}"

            bg_label = f"bg{index}"
            fg_label = f"fg{index}"
            graph_parts.append(
                f"[{source_label}]crop=iw:{crop_h}:0:(ih-{crop_h})/2,"
                f"split=2[bgsrc{index}][fgsrc{index}];"
                f"[bgsrc{index}]scale={output_w}:{output_h}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={output_w}:{output_h},gblur=sigma=20,setsar=1[{bg_label}];"
                f"[fgsrc{index}]scale={scaled_w}:{scaled_h}:flags=lanczos,"
                f"setsar=1[{fg_label}];"
                f"[{bg_label}][{fg_label}]overlay=x='{overlay_x}':"
                f"y='(H-h)/2':eval=frame:shortest=1,"
                f"setsar=1,setpts=PTS-STARTPTS[{output_label}];"
            )

        outputs.append(f"[{output_label}]")

    concat_label = "hybridjoined"
    graph_parts.append(
        "".join(outputs)
        + f"concat=n={len(outputs)}:v=1:a=0[{concat_label}];"
    )

    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        graph_parts.append(
            f"[{concat_label}]unsharp="
            f"{config.ENCODING_SETTINGS['unsharp_params']}[vout]"
        )
    else:
        graph_parts.append(f"[{concat_label}]null[vout]")

    return _encode(
        input_path,
        output_path,
        "".join(graph_parts),
        config,
        encoder,
        filter_complex=True,
    )


def _build_hybrid_segments(
    viewports,
    crop_w: int,
    source_w: int,
    max_segments: int = 28,
):
    """Cuantiza el zoom suave a tramos estáticos para evitar reinit de `scale`."""
    if not viewports or crop_w <= 0 or source_w <= 0:
        return [], 0.0

    ordered = sorted(viewports, key=lambda viewport: float(viewport[0]))
    step = 0.05
    segments = []

    while step <= 0.20:
        segments = _quantize_viewport_segments(ordered, crop_w, source_w, step)
        if len(segments) <= max_segments:
            break
        step += 0.025

    if len(segments) > max_segments:
        indices = _evenly_spaced_indices(list(range(len(segments))), max_segments)
        reduced = [segments[index].copy() for index in indices]
        for index in range(len(reduced) - 1):
            reduced[index]["end"] = reduced[index + 1]["start"]
        reduced[-1]["end"] = None
        segments = reduced

    return segments, step


def _quantize_viewport_segments(viewports, crop_w: int, source_w: int, step: float):
    def quantize(width: float) -> float:
        ratio = max(1.0, float(width) / float(crop_w))
        if ratio <= 1.04:
            quantized_ratio = 1.0
        else:
            quantized_ratio = 1.0 + math.ceil((ratio - 1.0) / step) * step
        quantized_ratio = min(float(source_w) / float(crop_w), quantized_ratio)
        return float(crop_w) * quantized_ratio

    quantized = [(float(item[0]), quantize(float(item[1]))) for item in viewports]
    if not quantized:
        return []

    segments = []
    current_width = quantized[0][1]
    current_start = 0.0

    for index in range(1, len(quantized)):
        timestamp, width = quantized[index]
        if abs(width - current_width) < 0.5:
            continue
        previous_timestamp = quantized[index - 1][0]
        boundary = max(current_start, (previous_timestamp + timestamp) / 2.0)
        segments.append({
            "start": current_start,
            "end": boundary,
            "viewport_width": current_width,
        })
        current_start = boundary
        current_width = width

    segments.append({
        "start": current_start,
        "end": None,
        "viewport_width": current_width,
    })
    return segments


def _even_dimension(value: float) -> int:
    dimension = max(2, int(round(value)))
    return dimension if dimension % 2 == 0 else dimension + 1


def _prepare_hybrid_viewports(profile, positions, crop_w: int):
    stats = {
        "hybrid_activations": 0,
        "adaptive_zoom_frames": 0,
        "max_required_width": float(crop_w),
        "max_viewport_width": float(crop_w),
    }
    if not profile or not positions or crop_w <= 0:
        return [], stats

    raw = [max(0.25, float(value)) for value in profile]
    max_required_ratio = max(raw)
    stats["max_required_width"] = max_required_ratio * crop_w

    if max_required_ratio <= 1.04:
        return [], stats

    samples = _resample_profile(raw, len(positions))
    active = False
    fit_streak = 0
    current_ratio = 1.0
    smoothed_ratios = []

    for required_ratio in samples:
        if not active and required_ratio > 1.04:
            active = True
            fit_streak = 0
            stats["hybrid_activations"] += 1

        if active:
            if required_ratio <= 0.98:
                fit_streak += 1
            else:
                fit_streak = 0

            if fit_streak >= 4:
                active = False
                fit_streak = 0

        target_ratio = (
            min(1.75, max(1.0, required_ratio * 1.04))
            if active
            else 1.0
        )
        alpha = 0.55 if target_ratio > current_ratio else 0.22
        current_ratio += (target_ratio - current_ratio) * alpha

        if not active and abs(current_ratio - 1.0) < 0.015:
            current_ratio = 1.0

        current_ratio = float(min(1.75, max(1.0, current_ratio)))
        smoothed_ratios.append(current_ratio)

    if max(smoothed_ratios, default=1.0) <= 1.015:
        return [], stats

    viewports = []
    previous_ratio = 1.0
    for position, ratio in zip(positions, smoothed_ratios):
        timestamp = float(position[0])
        critical = bool(position[2]) if len(position) > 2 else False
        ratio_change = abs(ratio - previous_ratio)
        viewport_critical = critical or ratio_change >= 0.025
        width = float(crop_w) * ratio
        viewports.append((timestamp, width, viewport_critical))
        if ratio > 1.015:
            stats["adaptive_zoom_frames"] += 1
        stats["max_viewport_width"] = max(stats["max_viewport_width"], width)
        previous_ratio = ratio

    return viewports, stats


def _resample_profile(profile: List[float], target_count: int) -> List[float]:
    if target_count <= 0:
        return []
    if not profile:
        return [1.0] * target_count
    if len(profile) == 1:
        return [float(profile[0])] * target_count
    if target_count == 1:
        return [float(profile[0])]

    result = []
    source_last = len(profile) - 1
    for index in range(target_count):
        source_position = index * source_last / (target_count - 1)
        left = int(source_position)
        right = min(source_last, left + 1)
        fraction = source_position - left
        value = profile[left] * (1.0 - fraction) + profile[right] * fraction
        result.append(float(value))
    return result


def _encode(
    input_path,
    output_path,
    vf,
    config,
    encoder,
    filter_complex: bool = False,
) -> bool:
    preset = config.ENCODING_SETTINGS["quality_preset"]
    settings = config.ENCODING_SETTINGS["presets"][preset]
    filter_script_path = None

    cmd = ["ffmpeg", "-y", "-i", input_path]
    try:
        if filter_complex:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".ffgraph",
                prefix="elevideo_",
                delete=False,
            ) as script:
                script.write(vf)
                filter_script_path = script.name

            cmd.extend([
                "-filter_complex_script", filter_script_path,
                "-map", "[vout]",
                "-map", "0:a?",
            ])
            logger.debug(
                "Filter graph externo | chars=%d | path=%s",
                len(vf),
                filter_script_path,
            )
        else:
            cmd.extend(["-vf", vf])

        cmd.extend(["-c:v", encoder])
        cmd.extend(build_video_encoding_args(encoder, preset, settings))

        audio_bitrate = get_audio_bitrate(settings)
        pixel_format = get_pixel_format(encoder)
        cmd.extend([
            "-pix_fmt", pixel_format,
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            output_path,
        ])

        logger.info(
            "Encoding | quality=%s | encoder=%s | rate_control=%s | pix_fmt=%s | audio=%s",
            preset,
            encoder,
            describe_rate_control(encoder, preset, settings),
            pixel_format,
            audio_bitrate,
        )

        tracker = get_active_progress_tracker()
        duration = probe_duration_seconds(input_path) if tracker else None
        if tracker:
            tracker.update_phase(ProcessingPhase.ENCODING)

        run_ffmpeg_with_progress(
            cmd,
            duration_seconds=duration,
            on_progress=(
                lambda fraction: tracker.update_phase_fraction(
                    fraction,
                    f"Generando video final... {int(round(fraction * 100))}%",
                )
                if tracker
                else None
            ),
        )
    except subprocess.CalledProcessError as e:
        logger.error(
            "FFmpeg falló | code=%s | diagnostic=%s",
            e.returncode,
            _ffmpeg_error_summary(e.stderr or ""),
        )
        return False
    except OSError as e:
        logger.error(
            "No se pudo iniciar FFmpeg | winerror=%s | errno=%s | error=%s",
            getattr(e, "winerror", None),
            getattr(e, "errno", None),
            e,
        )
        return False
    finally:
        if filter_script_path:
            try:
                os.remove(filter_script_path)
            except FileNotFoundError:
                pass
            except OSError as cleanup_error:
                logger.warning(
                    "No se pudo eliminar filter graph temporal | path=%s | error=%s",
                    filter_script_path,
                    cleanup_error,
                )

    if os.path.exists(output_path):
        logger.info(
            "Video generado | size=%.2fMB",
            os.path.getsize(output_path) / (1024 * 1024),
        )
        _log_video_info(output_path)
    return True


def _ffmpeg_error_summary(stderr: str) -> str:
    if not stderr:
        return "sin stderr"

    normalized = stderr.replace("\r", "\n")
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    useful = []
    for line in lines:
        lower = line.lower()
        if line.startswith("frame="):
            continue
        if any(token in lower for token in (
            "error", "failed", "invalid", "cannot", "could not", "unable",
            "conversion failed", "terminating", "nothing was written",
        )):
            useful.append(line)

    selected = useful[-12:] if useful else lines[-12:]
    text = " | ".join(selected)
    return text[-5000:]


def _normalize_position(position) -> Tuple[float, float, bool]:
    timestamp = float(position[0])
    x = float(position[1])
    critical = bool(position[2]) if len(position) > 2 else False
    return timestamp, x, critical


def _build_lerp(
    positions: List[Tuple[float, float]],
    use_easing: bool,
    max_keyframes: int = 80,
) -> str:
    positions = _deduplicate_positions(
        [_normalize_position(position) for position in positions]
    )
    if len(positions) == 1:
        return str(int(positions[0][1]))

    max_keyframes = max(2, max_keyframes)
    if len(positions) > max_keyframes:
        before = len(positions)
        positions = _reduce_positions_preserving_critical(positions, max_keyframes)
        logger.info(
            "Keyframes reducidos a %d | críticos preservados=%d | antes=%d",
            len(positions),
            sum(1 for position in positions if position[2]),
            before,
        )

    t0, x0, _ = positions[0]
    tn, xn, _ = positions[-1]
    slopes = []
    for index in range(len(positions) - 1):
        t1, x1, _ = positions[index]
        t2, x2, _ = positions[index + 1]
        duration = max(1e-6, t2 - t1)
        slopes.append((x2 - x1) / duration)

    terms = [f"{x0:.3f}+({slopes[0]:.8f})*(t-{t0:.3f})"]
    for index in range(1, len(positions) - 1):
        ti = positions[index][0]
        slope_delta = slopes[index] - slopes[index - 1]
        if abs(slope_delta) >= 1e-8:
            terms.append(f"+({slope_delta:.8f})*max(t-{ti:.3f},0)")

    core = "".join(terms)
    return (
        f"if(lt(t,{t0:.3f}),{x0:.3f},"
        f"if(gt(t,{tn:.3f}),{xn:.3f},{core}))"
    )


def _deduplicate_positions(positions):
    if not positions:
        return []
    deduplicated = [positions[0]]
    for timestamp, x, critical in positions[1:]:
        last_timestamp, _, last_critical = deduplicated[-1]
        if abs(timestamp - last_timestamp) < 1e-6:
            deduplicated[-1] = (timestamp, x, bool(critical or last_critical))
        else:
            deduplicated.append((timestamp, x, critical))
    return deduplicated


def _reduce_positions_preserving_critical(
    positions: List[Tuple[float, float, bool]],
    max_keyframes: int,
) -> List[Tuple[float, float, bool]]:
    if len(positions) <= max_keyframes:
        return positions

    mandatory = {0, len(positions) - 1}
    mandatory.update(index for index, position in enumerate(positions) if position[2])

    if len(mandatory) > max_keyframes:
        critical_indices = sorted(
            index
            for index in mandatory
            if index not in (0, len(positions) - 1)
        )
        slots = max(0, max_keyframes - 2)
        selected_critical = _evenly_spaced_indices(critical_indices, slots)
        keep = {0, len(positions) - 1, *selected_critical}
        logger.warning(
            "Demasiados keyframes críticos (%d) para el límite FFmpeg=%d; "
            "se priorizan de forma uniforme",
            len(mandatory),
            max_keyframes,
        )
        return [positions[index] for index in sorted(keep)]

    keep = set(mandatory)
    candidates = [
        index
        for index in range(1, len(positions) - 1)
        if index not in keep
    ]
    remaining_slots = max_keyframes - len(keep)
    keep.update(_evenly_spaced_indices(candidates, remaining_slots))
    return [positions[index] for index in sorted(keep)]


def _evenly_spaced_indices(indices: list, count: int) -> list:
    if count <= 0 or not indices:
        return []
    if count >= len(indices):
        return list(indices)
    if count == 1:
        return [indices[len(indices) // 2]]

    step = (len(indices) - 1) / (count - 1)
    selected = []
    used = set()
    for i in range(count):
        candidate = indices[int(round(i * step))]
        if candidate not in used:
            selected.append(candidate)
            used.add(candidate)
    return selected


def _probe_video_size(path: str) -> Tuple[int, int]:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        streams = json.loads(result.stdout).get("streams", [])
        if streams:
            return int(streams[0].get("width", 0)), int(streams[0].get("height", 0))
    except Exception as e:
        logger.warning("No se pudo consultar dimensiones del video: %s", e)
    return 0, 0


def _log_video_info(path: str):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        info = json.loads(result.stdout)
        for stream in info.get("streams", []):
            if stream["codec_type"] == "video":
                logger.info(
                    "Resolución=%sx%s | codec=%s",
                    stream["width"],
                    stream["height"],
                    stream["codec_name"],
                )
                if "r_frame_rate" in stream:
                    num, den = stream["r_frame_rate"].split("/")
                    logger.info("FPS=%.2f", float(num) / float(den))
        if "duration" in info.get("format", {}):
            logger.info("Duración=%.2fs", float(info["format"]["duration"]))
    except Exception as e:
        logger.warning("No se pudo obtener metadata: %s", e)
