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
        vf = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=20[blurred];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[scaled];"
            f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
        )
        logger.info("Usando fondo difuminado")
    else:
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
    output_w = config.CROP_SETTINGS["width"]
    output_h = config.CROP_SETTINGS["height"]
    crop_w, crop_h = source_crop_size or (output_w, output_h)
    positions = [_normalize_position(position) for position in positions]

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

    if not positions:
        crop_vf = f"crop={crop_w}:{crop_h}:(iw-{crop_w})/2:(ih-{crop_h})/2"
    else:
        positions = sorted(positions, key=lambda position: position[0])
        expr = _build_lerp(positions, config.STABILIZATION.get("use_easing", False))
        crop_vf = f"crop={crop_w}:{crop_h}:x='{expr}':y=(ih-{crop_h})/2"

    filters = [crop_vf, f"scale={output_w}:{output_h}:flags=lanczos"]
    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        filters.append(f"unsharp={config.ENCODING_SETTINGS['unsharp_params']}")

    return _encode(input_path, output_path, ",".join(filters), config, encoder)


def _encode(input_path, output_path, vf, config, encoder) -> bool:
    preset = config.ENCODING_SETTINGS["quality_preset"]
    settings = config.ENCODING_SETTINGS["presets"][preset]

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        "-c:v", encoder,
        "-preset", settings["preset"],
        "-crf", str(settings["crf"]),
    ]

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
        logger.error("FFmpeg falló | stderr=%s", (e.stderr or "")[-1000:])
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


def _build_lerp(positions: List[Tuple[float, float]], use_easing: bool) -> str:
    positions = [_normalize_position(position) for position in positions]
    if len(positions) == 1:
        return str(int(positions[0][1]))

    max_keyframes = 28
    if len(positions) > max_keyframes:
        before = len(positions)
        positions = _reduce_positions_preserving_critical(positions, max_keyframes)
        logger.info(
            "Keyframes reducidos a %d para expresión FFmpeg | críticos preservados=%d | antes=%d",
            len(positions),
            sum(1 for position in positions if position[2]),
            before,
        )

    expr = ""
    open_groups = 0
    for i in range(len(positions) - 1):
        t1, x1, _ = positions[i]
        t2, x2, _ = positions[i + 1]
        dur = t2 - t1
        if dur <= 0:
            continue
        interp = f"{int(x1)}+({int(x2)}-{int(x1)})*(t-{t1:.3f})/{dur:.3f}"
        expr += f"if(between(t,{t1:.3f},{t2:.3f}),{interp},"
        open_groups += 1

    return expr + str(int(positions[-1][1])) + ")" * open_groups


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
