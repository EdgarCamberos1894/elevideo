import logging
import time
from typing import Tuple

from processing.ffmpeg_ultra import _encode
from processing.video_processor_enhanced import _base_metrics, _output_path

logger = logging.getLogger(__name__)


_DEFAULT_BACKGROUND_ZOOM = 1.05
_DEFAULT_BACKGROUND_BRIGHTNESS = -0.08
_DEFAULT_BACKGROUND_SATURATION = 0.85


def process_full_frame(
    input_path: str,
    config,
    encoder: str = "libx264",
) -> Tuple[str, dict]:
    """Renderiza modos que conservan el encuadre completo sin usar Smart Crop."""
    mode_config = config.CONVERSION_MODE["modes"]["full"]
    width = int(mode_config["width"])
    height = int(mode_config["height"])
    blurred = bool(mode_config.get("blur_background", False))

    output_path = _output_path(
        input_path,
        "blurred" if blurred else "letterbox",
    )
    started = time.time()

    if blurred:
        filter_graph = _build_blurred_filter(width, height, config, mode_config)
        ok = _encode(
            input_path,
            output_path,
            filter_graph,
            config,
            encoder,
            filter_complex=True,
        )
        style = "blurred"
    else:
        video_filter = _build_letterbox_filter(width, height, config, mode_config)
        ok = _encode(
            input_path,
            output_path,
            video_filter,
            config,
            encoder,
            filter_complex=False,
        )
        style = "black"

    encoding_time = time.time() - started
    if not ok:
        raise RuntimeError(f"Error en el encoding del video en modo {style}")

    logger.info(
        "Composición full completada | style=%s | output=%dx%d | encoding=%.2fs",
        style,
        width,
        height,
        encoding_time,
    )
    return output_path, {
        **_base_metrics(reason=f"full_{style}"),
        "mode": "full",
        "background_style": style,
        "encoding_time": encoding_time,
    }


def _build_blurred_filter(width: int, height: int, config, mode_config: dict) -> str:
    zoom = _bounded_float(
        mode_config.get("background_zoom", _DEFAULT_BACKGROUND_ZOOM),
        minimum=1.0,
        maximum=1.12,
    )
    brightness = _bounded_float(
        mode_config.get("background_brightness", _DEFAULT_BACKGROUND_BRIGHTNESS),
        minimum=-0.25,
        maximum=0.10,
    )
    saturation = _bounded_float(
        mode_config.get("background_saturation", _DEFAULT_BACKGROUND_SATURATION),
        minimum=0.50,
        maximum=1.20,
    )
    configured_blur_sigma = mode_config.get("background_blur_sigma")
    blur_sigma = (
        _adaptive_blur_sigma(width, height)
        if configured_blur_sigma is None
        else _bounded_float(configured_blur_sigma, minimum=8.0, maximum=40.0)
    )

    background_width = _even_dimension(width * zoom)
    background_height = _even_dimension(height * zoom)

    foreground_filters = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
        "force_divisible_by=2,setsar=1"
    )
    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        foreground_filters += (
            f",unsharp={config.ENCODING_SETTINGS['unsharp_params']}"
        )

    logger.info(
        "Fondo difuminado | blur=%.1f | zoom=%.3f | brightness=%.2f | saturation=%.2f",
        blur_sigma,
        zoom,
        brightness,
        saturation,
    )

    return (
        "[0:v]split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={background_width}:{background_height}:"
        "force_original_aspect_ratio=increase:force_divisible_by=2,"
        f"crop={width}:{height},"
        f"eq=brightness={brightness:.3f}:saturation={saturation:.3f},"
        f"gblur=sigma={blur_sigma:.2f}:steps=2,setsar=1[background];"
        f"[fgsrc]{foreground_filters}[foreground];"
        "[background][foreground]overlay=(W-w)/2:(H-h)/2:"
        "shortest=1,setsar=1[vout]"
    )


def _build_letterbox_filter(width: int, height: int, config, mode_config: dict) -> str:
    background_color = mode_config.get("background_color", "black")
    filters = [
        (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2"
        ),
        "setsar=1",
    ]

    # La nitidez se aplica al contenido antes de crear las barras, evitando
    # generar halos innecesarios en el límite entre imagen y fondo negro.
    if config.ENCODING_SETTINGS.get("apply_unsharp", False):
        filters.append(f"unsharp={config.ENCODING_SETTINGS['unsharp_params']}")

    filters.extend([
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={background_color}",
        "setsar=1",
    ])
    return ",".join(filters)


def _adaptive_blur_sigma(width: int, height: int) -> float:
    """Escala el blur con la resolución manteniendo un rango visual prudente."""
    short_side = max(1, min(int(width), int(height)))
    return max(18.0, min(32.0, short_side * 0.022))


def _even_dimension(value: float) -> int:
    dimension = max(2, int(round(value)))
    return dimension if dimension % 2 == 0 else dimension + 1


def _bounded_float(value, minimum: float, maximum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = minimum
    return max(minimum, min(maximum, numeric))
