import logging
import math
from typing import List, Optional, Tuple

from models.schemas import SHORT_MIN_DURATION_SECONDS, SHORT_MAX_DURATION_SECONDS
from services.segment_selector import (
    SegmentSelector,
    _boundary_proximity,
    _has_meaningful_signal,
    _window_avg,
)

logger = logging.getLogger(__name__)

_AUTO_MIN_DURATION_SECONDS = 20
_AUTO_IDEAL_MIN_SECONDS = 30
_AUTO_IDEAL_MAX_SECONDS = 50
_AUTO_DURATION_STEP_SECONDS = 2
_APPROX_MIN_TOLERANCE_SECONDS = 3
_APPROX_MAX_TOLERANCE_SECONDS = 6

# La señal de interés sigue mandando. El cierre natural recibe suficiente peso
# para poder vencer a una ventana apenas más intensa que termine de forma abrupta.
_CONTENT_SCORE_WEIGHT = 0.80
_END_QUALITY_WEIGHT = 0.14
_DURATION_PREFERENCE_WEIGHT = 0.06


class NaturalSegmentSelector:
    """Selector v3 que optimiza conjuntamente inicio y duración del Short Auto."""

    @staticmethod
    def select_best_segment(
        video_path: str,
        total_duration: float,
        target_duration: Optional[int],
        duration_mode: str = "exact",
        detector=None,
        config=None,
    ) -> Tuple[float, int, str]:
        mode = _normalize_duration_mode(duration_mode)
        fallback_duration = _fallback_duration(total_duration, target_duration, mode)

        if total_duration <= SHORT_MIN_DURATION_SECONDS:
            return 0.0, fallback_duration, "full_video"

        if mode == "auto" and total_duration <= _AUTO_MIN_DURATION_SECONDS:
            return 0.0, fallback_duration, "full_video_auto"

        if mode == "exact" and target_duration is not None and total_duration <= target_duration:
            return 0.0, fallback_duration, "full_video_exact"

        try:
            return NaturalSegmentSelector._analyze_and_select(
                video_path=video_path,
                total_duration=total_duration,
                target_duration=target_duration,
                duration_mode=mode,
                detector=detector,
                config=config,
            )
        except Exception as exc:
            logger.warning(
                "Análisis Smart Clip v3 falló (%s). Usando segmento central como fallback.",
                exc,
            )
            start, duration = SegmentSelector._central_segment(
                total_duration,
                fallback_duration,
            )
            return start, duration, f"central_fallback_v3_{mode}"

    @staticmethod
    def _analyze_and_select(
        video_path: str,
        total_duration: float,
        target_duration: Optional[int],
        duration_mode: str,
        detector=None,
        config=None,
    ) -> Tuple[float, int, str]:
        audio_scores, silences = SegmentSelector._analyze_audio_and_silence(
            video_path,
            total_duration,
        )
        scene_cuts = SegmentSelector._detect_scene_cuts(
            video_path,
            total_duration,
        )

        face_scores: dict = {}
        visual_scores: dict = {}
        if detector is not None and config is not None:
            try:
                face_scores, visual_scores = SegmentSelector._analyze_visual_signals(
                    video_path=video_path,
                    total_duration=total_duration,
                    detector=detector,
                    scene_cuts=scene_cuts,
                )
            except Exception as exc:
                logger.warning(
                    "Análisis visual Smart Clip v3 falló (%s). Continuando con audio/escenas.",
                    exc,
                )

        logger.info(
            "Smart Clip v3 signals | mode=%s | audio=%d | silences=%d | scenes=%d | faces=%d | visual_activity=%d",
            duration_mode,
            len(audio_scores),
            len(silences) if silences is not None else 0,
            len(scene_cuts),
            len(face_scores),
            len(visual_scores),
        )

        has_face_signal = _has_meaningful_signal(face_scores)
        has_audio_signal = _has_meaningful_signal(audio_scores)
        has_visual_signal = _has_meaningful_signal(visual_scores)
        has_boundaries = bool(scene_cuts) or bool(silences)

        durations = _duration_candidates(
            total_duration=total_duration,
            target_duration=target_duration,
            duration_mode=duration_mode,
        )
        if not durations:
            fallback_duration = _fallback_duration(total_duration, target_duration, duration_mode)
            start, duration = SegmentSelector._central_segment(total_duration, fallback_duration)
            return start, duration, f"central_fallback_v3_{duration_mode}"

        if not (has_face_signal or has_audio_signal or has_visual_signal or has_boundaries):
            fallback_duration = _fallback_duration(total_duration, target_duration, duration_mode)
            start, duration = SegmentSelector._central_segment(total_duration, fallback_duration)
            logger.info(
                "Smart Clip v3 sin señales útiles | mode=%s | start=%.2fs | duration=%ds",
                duration_mode,
                start,
                duration,
            )
            return start, duration, f"central_fallback_no_signals_v3_{duration_mode}"

        # Primera pasada: cada duración compite con sus mejores ventanas. Solo
        # conservamos las tres mejores por duración para evitar inflar memoria.
        coarse_segments: List[dict] = []
        for duration in durations:
            starts = SegmentSelector._generate_candidates(total_duration, duration)
            if not starts:
                continue

            _, _, detail = SegmentSelector._score_candidates(
                candidates=starts,
                target_duration=duration,
                audio_scores=audio_scores,
                visual_scores=visual_scores,
                scene_cuts=scene_cuts,
                face_scores=face_scores,
                silences=silences,
                log_top=False,
            )
            for entry in sorted(detail, key=lambda item: item["score"], reverse=True)[:3]:
                coarse_segments.append(
                    _decorate_segment(
                        entry=entry,
                        duration=duration,
                        target_duration=target_duration,
                        duration_mode=duration_mode,
                        scene_cuts=scene_cuts,
                        silences=silences,
                        audio_scores=audio_scores,
                        visual_scores=visual_scores,
                        total_duration=total_duration,
                    )
                )

        if not coarse_segments:
            fallback_duration = _fallback_duration(total_duration, target_duration, duration_mode)
            start, duration = SegmentSelector._central_segment(total_duration, fallback_duration)
            return start, duration, f"central_fallback_v3_{duration_mode}"

        coarse_segments.sort(key=lambda item: item["natural_score"], reverse=True)
        best = coarse_segments[0]

        # Segunda pasada: refinamos los mejores pares (inicio, duración) a 250ms
        # y alineamos inicio/fin con cortes y silencios detectados.
        refined_segments: List[dict] = []
        seen_pairs = set()
        for segment in coarse_segments[:8]:
            duration = segment["duration"]
            pair = (round(segment["start"], 3), duration)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            refined_starts = SegmentSelector._refine_candidates(
                top_starts=[segment["start"]],
                total_duration=total_duration,
                target_duration=duration,
                scene_cuts=scene_cuts,
                silences=silences,
            )
            if not refined_starts:
                continue

            _, _, detail = SegmentSelector._score_candidates(
                candidates=refined_starts,
                target_duration=duration,
                audio_scores=audio_scores,
                visual_scores=visual_scores,
                scene_cuts=scene_cuts,
                face_scores=face_scores,
                silences=silences,
                log_top=False,
            )
            for entry in detail:
                refined_segments.append(
                    _decorate_segment(
                        entry=entry,
                        duration=duration,
                        target_duration=target_duration,
                        duration_mode=duration_mode,
                        scene_cuts=scene_cuts,
                        silences=silences,
                        audio_scores=audio_scores,
                        visual_scores=visual_scores,
                        total_duration=total_duration,
                    )
                )

        if refined_segments:
            refined_best = max(refined_segments, key=lambda item: item["natural_score"])
            if refined_best["natural_score"] >= best["natural_score"]:
                best = refined_best

        signal_label = _signal_label(
            has_face_signal=has_face_signal,
            has_audio_signal=has_audio_signal,
            has_visual_signal=has_visual_signal,
            has_boundaries=has_boundaries,
        )
        strategy = f"smart_auto_v3_{duration_mode}_{signal_label}"

        logger.info(
            "Smart Clip v3 seleccionado | start=%.2fs | end=%.2fs | duration=%ds | mode=%s | content=%.3f | end_quality=%.3f | duration_pref=%.3f | score=%.3f | strategy=%s",
            best["start"],
            best["start"] + best["duration"],
            best["duration"],
            duration_mode,
            best["content_score"],
            best["end_quality"],
            best["duration_preference"],
            best["natural_score"],
            strategy,
        )

        return best["start"], best["duration"], strategy


def _decorate_segment(
    entry: dict,
    duration: int,
    target_duration: Optional[int],
    duration_mode: str,
    scene_cuts: List[float],
    silences: Optional[List[Tuple[float, float]]],
    audio_scores: dict,
    visual_scores: dict,
    total_duration: float,
) -> dict:
    start = float(entry["start"])
    end_quality = _end_quality_score(
        end=start + duration,
        scene_cuts=scene_cuts,
        silences=silences,
        audio_scores=audio_scores,
        visual_scores=visual_scores,
        total_duration=total_duration,
    )
    duration_preference = _duration_preference(
        duration=duration,
        target_duration=target_duration,
        duration_mode=duration_mode,
    )
    content_score = float(entry["score"])
    natural_score = (
        _CONTENT_SCORE_WEIGHT * content_score
        + _END_QUALITY_WEIGHT * end_quality
        + _DURATION_PREFERENCE_WEIGHT * duration_preference
    )

    return {
        **entry,
        "duration": duration,
        "content_score": content_score,
        "end_quality": end_quality,
        "duration_preference": duration_preference,
        "natural_score": max(0.0, min(1.0, natural_score)),
    }


def _duration_candidates(
    total_duration: float,
    target_duration: Optional[int],
    duration_mode: str,
) -> List[int]:
    max_duration = min(SHORT_MAX_DURATION_SECONDS, int(math.floor(total_duration)))
    if max_duration < SHORT_MIN_DURATION_SECONDS:
        return []

    if duration_mode == "exact":
        target = int(target_duration or 30)
        return [max(SHORT_MIN_DURATION_SECONDS, min(target, max_duration))]

    if duration_mode == "approximate":
        target = int(target_duration or 30)
        tolerance = _approx_tolerance(target)
        low = max(SHORT_MIN_DURATION_SECONDS, target - tolerance)
        high = min(max_duration, target + tolerance)
        if high < low:
            return [max(SHORT_MIN_DURATION_SECONDS, min(target, max_duration))]
        return list(range(low, high + 1))

    low = min(_AUTO_MIN_DURATION_SECONDS, max_duration)
    low = max(SHORT_MIN_DURATION_SECONDS, low)
    durations = list(range(low, max_duration + 1, _AUTO_DURATION_STEP_SECONDS))
    if max_duration not in durations:
        durations.append(max_duration)
    return sorted(set(durations))


def _duration_preference(
    duration: int,
    target_duration: Optional[int],
    duration_mode: str,
) -> float:
    if duration_mode == "exact":
        return 1.0

    if duration_mode == "approximate":
        target = int(target_duration or 30)
        tolerance = max(1, _approx_tolerance(target))
        distance_ratio = min(1.0, abs(duration - target) / tolerance)
        # El borde de la tolerancia sigue siendo válido; solo pierde un 20%.
        return 1.0 - 0.20 * distance_ratio

    if _AUTO_IDEAL_MIN_SECONDS <= duration <= _AUTO_IDEAL_MAX_SECONDS:
        return 1.0
    if duration < _AUTO_IDEAL_MIN_SECONDS:
        span = max(1, _AUTO_IDEAL_MIN_SECONDS - _AUTO_MIN_DURATION_SECONDS)
        ratio = (duration - _AUTO_MIN_DURATION_SECONDS) / span
        return max(0.75, min(1.0, 0.75 + 0.25 * ratio))

    span = max(1, SHORT_MAX_DURATION_SECONDS - _AUTO_IDEAL_MAX_SECONDS)
    ratio = (SHORT_MAX_DURATION_SECONDS - duration) / span
    return max(0.75, min(1.0, 0.75 + 0.25 * ratio))


def _end_quality_score(
    end: float,
    scene_cuts: List[float],
    silences: Optional[List[Tuple[float, float]]],
    audio_scores: dict,
    visual_scores: dict,
    total_duration: float,
) -> float:
    if end >= total_duration - 0.15:
        return 1.0

    end_boundaries = list(scene_cuts)
    if silences:
        # Terminar justo antes de una pausa suele sentirse como cierre de frase o beat.
        end_boundaries.extend(silence_start for silence_start, _ in silences)

    boundary_score = _boundary_proximity(end, end_boundaries, window=2.0) if end_boundaries else 0.5
    activity_score = _activity_drop_score(
        end=end,
        audio_scores=audio_scores,
        visual_scores=visual_scores,
        total_duration=total_duration,
    )

    return 0.75 * boundary_score + 0.25 * activity_score


def _activity_drop_score(
    end: float,
    audio_scores: dict,
    visual_scores: dict,
    total_duration: float,
) -> float:
    available = []
    for scores in (audio_scores, visual_scores):
        if not _has_meaningful_signal(scores):
            continue

        before_start = max(0.0, end - 2.0)
        before_duration = max(0.25, end - before_start)
        after_duration = max(0.25, min(2.0, total_duration - end))

        before = _window_avg(scores, before_start, before_duration)
        after = _window_avg(scores, end, after_duration)
        drop = max(-1.0, min(1.0, before - after))
        available.append(0.5 + 0.5 * drop)

    if not available:
        return 0.5
    return sum(available) / len(available)


def _fallback_duration(
    total_duration: float,
    target_duration: Optional[int],
    duration_mode: str,
) -> int:
    max_duration = max(
        SHORT_MIN_DURATION_SECONDS,
        min(SHORT_MAX_DURATION_SECONDS, int(math.floor(total_duration))),
    )

    if duration_mode == "auto":
        if total_duration <= _AUTO_MIN_DURATION_SECONDS:
            return max_duration
        return min(40, max_duration)

    target = int(target_duration or 30)
    return max(SHORT_MIN_DURATION_SECONDS, min(target, max_duration))


def _approx_tolerance(target_duration: int) -> int:
    proportional = int(round(target_duration * 0.10))
    return max(
        _APPROX_MIN_TOLERANCE_SECONDS,
        min(_APPROX_MAX_TOLERANCE_SECONDS, proportional),
    )


def _normalize_duration_mode(duration_mode: str) -> str:
    value = getattr(duration_mode, "value", duration_mode)
    normalized = str(value or "exact").strip().lower()
    if normalized not in {"auto", "approximate", "exact"}:
        logger.warning("duration_mode desconocido '%s'; usando exact", duration_mode)
        return "exact"
    return normalized


def _signal_label(
    has_face_signal: bool,
    has_audio_signal: bool,
    has_visual_signal: bool,
    has_boundaries: bool,
) -> str:
    if has_face_signal and has_audio_signal and has_visual_signal:
        return "multisignal"
    if has_face_signal and has_audio_signal:
        return "face_audio"
    if has_audio_signal and has_visual_signal:
        return "audio_visual"
    if has_audio_signal:
        return "audio"
    if has_face_signal:
        return "faces"
    if has_visual_signal:
        return "visual"
    if has_boundaries:
        return "boundaries"
    return "fallback"
