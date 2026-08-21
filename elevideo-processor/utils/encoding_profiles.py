import logging
from typing import Mapping

logger = logging.getLogger(__name__)


_NVENC_PRESETS = {
    "ultra_fast": "p2",
    "fast": "p3",
    "balanced": "p5",
    "web": "p5",
    "high": "p6",
    "ultra": "p7",
}

_QSV_PRESETS = {
    "ultra_fast": "veryfast",
    "fast": "fast",
    "balanced": "medium",
    "web": "medium",
    "high": "slow",
    "ultra": "slower",
}


def build_video_encoding_args(
    encoder: str,
    quality_preset: str,
    settings: Mapping[str, object],
) -> list[str]:
    """Construye parámetros de calidad compatibles con el encoder H.264 activo."""
    quality = str(settings.get("crf", "21"))

    if encoder == "libx264":
        args = [
            "-preset", str(settings.get("preset", "medium")),
            "-crf", quality,
            "-profile:v", str(settings.get("profile", "high")),
        ]
        if settings.get("level"):
            args.extend(["-level:v", str(settings["level"])])
        if settings.get("tune"):
            args.extend(["-tune", str(settings["tune"])])
        if settings.get("maxrate"):
            args.extend(["-maxrate", str(settings["maxrate"])])
        if settings.get("bufsize"):
            args.extend(["-bufsize", str(settings["bufsize"])])
        return args

    if encoder == "h264_nvenc":
        return [
            "-preset", _NVENC_PRESETS.get(quality_preset, "p5"),
            "-tune", "hq",
            "-rc", "vbr",
            "-cq:v", quality,
            "-b:v", "0",
            "-profile:v", "high",
        ]

    if encoder == "h264_qsv":
        return [
            "-preset", _QSV_PRESETS.get(quality_preset, "medium"),
            "-global_quality", quality,
            "-profile:v", "high",
        ]

    logger.warning(
        "Encoder sin perfil específico: %s; usando opciones mínimas compatibles",
        encoder,
    )
    return []


def get_audio_bitrate(settings: Mapping[str, object]) -> str:
    """Devuelve el bitrate AAC configurado para el nivel de calidad."""
    return str(settings.get("bitrate_audio", "192k"))


def get_pixel_format(encoder: str) -> str:
    """Selecciona un formato de píxel aceptado por el encoder activo."""
    if encoder == "h264_qsv":
        return "nv12"
    return "yuv420p"


def describe_rate_control(
    encoder: str,
    quality_preset: str,
    settings: Mapping[str, object],
) -> str:
    quality = str(settings.get("crf", "21"))
    if encoder == "libx264":
        return f"crf={quality},preset={settings.get('preset', 'medium')}"
    if encoder == "h264_nvenc":
        return f"cq={quality},preset={_NVENC_PRESETS.get(quality_preset, 'p5')}"
    if encoder == "h264_qsv":
        return f"global_quality={quality},preset={_QSV_PRESETS.get(quality_preset, 'medium')}"
    return "default"
