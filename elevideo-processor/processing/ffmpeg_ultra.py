import json
import logging
import os
import subprocess
from typing import List, Optional, Tuple

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
        return _process_hybrid_smart_crop(
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
    source_w, _ = _probe_video_size(input_path)
    if source_w <= 0:
        logger.warning("No se pudo obtener ancho fuente; se usa Smart Crop normal")
        positions = sorted(positions, key=lambda position: position[0])
        expr = _build_lerp(
            positions,
            config.STABILIZATION.get("use_easing", False),
            max_keyframes=int(config.KEYFRAME_SETTINGS.get("max_keyframes", 80)),
        )
        vf = (
            f"crop={crop_w}:{crop_h}:x='{expr}':y=(ih-{crop_h})/2,"
            f"scale={output_w}:{output_h}:flags=lanczos"
        )
        return _encode(input_path, output_path, _append_unsharp(vf, config), config, encoder)

    positions = sorted(positions, key=lambda position: position[0])
    viewports = sorted(viewports, key=lambda viewport: viewport[0])
    max_keyframes = int(config.KEYFRAME_SETTINGS.get("max_keyframes", 80))
    viewport_keyframes = min(max_keyframes, 36)

    center_positions = [
        (timestamp, x + crop_w / 2.0, critical)
        for timestamp, x, critical in positions
    ]
    center_expr = _build_lerp(
        center_positions,
        False,
        max_keyframes=max_keyframes,
    )
    viewport_expr = _build_lerp(
        viewports,
        False,
        max_keyframes=viewport_keyframes,
    )

    safe_viewport = f"min({float(source_w):.3f},max({float(crop_w):.3f},{viewport_expr}))"
    left_expr = (
        f"max(0,min({float(source_w):.3f}-({safe_viewport}),"
        f"({center_expr})-({safe_viewport})/2))"
    )
    scale_w = f"trunc(iw*{float(output_w):.3f}/({safe_viewport})/2)*2"
    scale_h = f"trunc(ih*{float(output_w):.3f}/({safe_viewport})/2)*2"
    overlay_x = f"-({left_expr})*{float(output_w):.3f}/({safe_viewport})"

    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        foreground_tail = (
            f"[fgscaled]unsharp={config.ENCODING_SETTINGS['unsharp_params']}[fg];"
        )
    else:
        foreground_tail = "[fgscaled]null[fg];"

    vf = (
        f"[0:v]crop=iw:{crop_h}:0:(ih-{crop_h})/2[base];"
        f"[base]split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={output_w}:{output_h}:force_original_aspect_ratio=increase,"
        f"crop={output_w}:{output_h},gblur=sigma=20[bg];"
        f"[fgsrc]scale=w='{scale_w}':h='{scale_h}':eval=frame:flags=lanczos[fgscaled];"
        f"{foreground_tail}"
        f"[bg][fg]overlay=x='{overlay_x}':y='(H-h)/2':eval=frame:shortest=1[vout]"
    )

    return _encode(
        input_path,
        output_path,
        vf,
        config,
        encoder,
        filter_complex=True,
    )


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

    # Si el sujeto cabe, el video sigue exactamente por el pipeline Smart Crop existente.
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

    cmd = ["ffmpeg", "-y", "-i", input_path]
    if filter_complex:
        cmd.extend([
            "-filter_complex", vf,
            "-map", "[vout]",
            "-map", "0:a?",
        ])
    else:
        cmd.extend(["-vf", vf])

    cmd.extend([
        "-c:v", encoder,
        "-preset", settings["preset"],
        "-crf", str(settings["crf"]),
    ])

    if encoder == "libx264":
        cmd.extend(["-profile:v", settings.get("profile", "high")])

    cmd.extend([
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "128k",
        output_path,
    ])

    logger.info(
        "Encoding | preset=%s | ffmpeg_preset=%s | crf=%s",
        preset,
        settings["preset"],
        settings["crf"],
    )

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error("FFmpeg falló | stderr=%s", (e.stderr or "")[-1500:])
        return False

    if os.path.exists(output_path):
        logger.info(
            "Video generado | size=%.2fMB",
            os.path.getsize(output_path) / (1024 * 1024),
        )
        _log_video_info(output_path)
    return True


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
            "Demasiados keyframes críticos (%d) para el límite FFmpeg=%d; se priorizan de forma uniforme",
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
