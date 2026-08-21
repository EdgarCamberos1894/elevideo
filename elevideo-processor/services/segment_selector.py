import json
import logging
import math
import re
import subprocess
from typing import List, Optional, Tuple

from models.schemas import SHORT_MIN_DURATION_SECONDS

logger = logging.getLogger(__name__)

_SAMPLE_STEP = 1.0
_REFINEMENT_STEP = 0.25
_REFINEMENT_RADIUS = 1.0
_MAX_VISUAL_SAMPLES = 480
_BASE_VISUAL_SAMPLE_EVERY = 1.5

# FFmpeg scdet usa una escala 0-100; 10 es el valor por defecto y está
# dentro del rango recomendado 8-14 para cambios de escena significativos.
_SCENE_CHANGE_THRESHOLD = 10.0

# Detecta pausas suficientemente largas como para servir de frontera natural
# sin confundir micro-pausas normales del habla con silencio editorial.
_SILENCE_NOISE_DB = -35
_SILENCE_MIN_DURATION = 0.35

_WEIGHT_FACES = 0.34
_WEIGHT_ACTIVE_AUDIO = 0.28
_WEIGHT_AUDIO_ENERGY = 0.20
_WEIGHT_VISUAL_ACTIVITY = 0.18

_BASE_SCORE_WEIGHT = 0.80
_HOOK_SCORE_WEIGHT = 0.12
_BOUNDARY_SCORE_WEIGHT = 0.08


class SegmentSelector:

    @staticmethod
    def select_best_segment(
        video_path: str,
        total_duration: float,
        target_duration: int,
        detector=None,
        config=None,
    ) -> Tuple[float, int, str]:
        if total_duration <= target_duration:
            actual = min(
                target_duration,
                max(SHORT_MIN_DURATION_SECONDS, int(round(total_duration))),
            )
            logger.info(
                "Video corto (%.2fs <= %ds): usando video completo",
                total_duration,
                target_duration,
            )
            return 0.0, actual, "full_video"

        try:
            return SegmentSelector._analyze_and_select(
                video_path,
                total_duration,
                target_duration,
                detector,
                config,
            )
        except Exception as e:
            logger.warning(
                "Análisis Short Auto falló (%s). Usando segmento central como fallback.",
                e,
            )
            start, duration = SegmentSelector._central_segment(
                total_duration,
                target_duration,
            )
            return start, duration, "central_fallback"

    @staticmethod
    def get_video_duration(video_path: str) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            video_path,
        ]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return float(json.loads(result.stdout)["format"]["duration"])
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"No se pudo obtener la duración: {video_path}"
            ) from e
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"Metadata inválida o incompleta: {video_path}"
            ) from e

    @staticmethod
    def _analyze_and_select(
        video_path: str,
        total_duration: float,
        target_duration: int,
        detector=None,
        config=None,
    ) -> Tuple[float, int, str]:
        candidates = SegmentSelector._generate_candidates(
            total_duration,
            target_duration,
        )

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
                face_scores, visual_scores = (
                    SegmentSelector._analyze_visual_signals(
                        video_path=video_path,
                        total_duration=total_duration,
                        detector=detector,
                        scene_cuts=scene_cuts,
                    )
                )
            except Exception as e:
                logger.warning(
                    "Análisis visual Short Auto falló (%s). "
                    "Continuando con audio/escenas.",
                    e,
                )

        logger.info(
            "Short Auto signals | audio=%d | silences=%d | scenes=%d | "
            "faces=%d | visual_activity=%d",
            len(audio_scores),
            len(silences) if silences is not None else 0,
            len(scene_cuts),
            len(face_scores),
            len(visual_scores),
        )

        has_face_signal = _has_meaningful_signal(face_scores)
        has_audio_signal = _has_meaningful_signal(audio_scores)
        has_visual_signal = _has_meaningful_signal(visual_scores)
        has_active_audio = silences is not None and has_audio_signal
        has_boundaries = bool(scene_cuts) or bool(silences)

        if not (
            has_face_signal
            or has_audio_signal
            or has_visual_signal
            or has_boundaries
        ):
            start, duration = SegmentSelector._central_segment(
                total_duration,
                target_duration,
            )
            logger.info(
                "Short Auto sin señales útiles; usando segmento central | start=%.2fs",
                start,
            )
            return start, duration, "central_fallback_no_signals"

        best_start, best_score, coarse_detail = SegmentSelector._score_candidates(
            candidates=candidates,
            target_duration=target_duration,
            audio_scores=audio_scores,
            visual_scores=visual_scores,
            scene_cuts=scene_cuts,
            face_scores=face_scores,
            silences=silences,
            log_top=False,
        )

        top_starts = [
            item["start"]
            for item in sorted(
                coarse_detail,
                key=lambda x: x["score"],
                reverse=True,
            )[:5]
        ]
        refined_candidates = SegmentSelector._refine_candidates(
            top_starts=top_starts,
            total_duration=total_duration,
            target_duration=target_duration,
            scene_cuts=scene_cuts,
            silences=silences,
        )

        if refined_candidates:
            refined_start, refined_score, _ = SegmentSelector._score_candidates(
                candidates=refined_candidates,
                target_duration=target_duration,
                audio_scores=audio_scores,
                visual_scores=visual_scores,
                scene_cuts=scene_cuts,
                face_scores=face_scores,
                silences=silences,
                log_top=True,
            )
            if refined_score >= best_score:
                best_start, best_score = refined_start, refined_score

        if has_face_signal and has_visual_signal and has_active_audio:
            strategy = "smart_auto_v2"
        elif has_face_signal and has_active_audio:
            strategy = "smart_auto_v2_face_audio"
        elif has_audio_signal or has_active_audio:
            strategy = "smart_auto_v2_audio"
        elif has_visual_signal:
            strategy = "smart_auto_v2_visual"
        else:
            strategy = "smart_auto_v2_boundaries"

        logger.info(
            "Segmento seleccionado | start=%.2fs | score=%.3f | strategy=%s",
            best_start,
            best_score,
            strategy,
        )
        return best_start, target_duration, strategy

    @staticmethod
    def _generate_candidates(
        total_duration: float,
        target_duration: int,
    ) -> List[float]:
        max_start = total_duration - target_duration
        candidates: List[float] = []
        current = 0.0

        while current <= max_start:
            candidates.append(round(current, 3))
            current += _SAMPLE_STEP

        if not candidates or candidates[-1] < max_start - 0.1:
            candidates.append(round(max_start, 3))

        return candidates

    @staticmethod
    def _refine_candidates(
        top_starts: List[float],
        total_duration: float,
        target_duration: int,
        scene_cuts: List[float],
        silences: Optional[List[Tuple[float, float]]],
    ) -> List[float]:
        max_start = max(0.0, total_duration - target_duration)
        refined = set()

        def add(value: float) -> None:
            refined.add(round(min(max(value, 0.0), max_start), 3))

        for start in top_starts:
            offset = -_REFINEMENT_RADIUS
            while offset <= _REFINEMENT_RADIUS + 1e-9:
                add(start + offset)
                offset += _REFINEMENT_STEP

            end = start + target_duration

            # Un cambio de escena cerca del inicio/fin es una frontera editorial
            # especialmente útil para evitar cortes "a mitad" de una toma.
            for cut in scene_cuts:
                if abs(cut - start) <= 1.5:
                    add(cut)
                if abs(cut - end) <= 1.5:
                    add(cut - target_duration)

            if silences:
                for silence_start, silence_end in silences:
                    # Para iniciar, preferimos justo después de una pausa.
                    if abs(silence_end - start) <= 1.5:
                        add(silence_end)
                    # Para terminar, preferimos justo antes de una pausa.
                    if abs(silence_start - end) <= 1.5:
                        add(silence_start - target_duration)

        return sorted(refined)

    @staticmethod
    def _analyze_audio_and_silence(
        video_path: str,
        total_duration: float,
    ) -> Tuple[dict, Optional[List[Tuple[float, float]]]]:
        filter_chain = (
            "asetnsamples=n=1024,"
            "astats=metadata=1:reset=1,"
            "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-,"
            f"silencedetect=noise={_SILENCE_NOISE_DB}dB:"
            f"d={_SILENCE_MIN_DURATION}"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i",
            video_path,
            "-vn",
            "-af",
            filter_chain,
            "-f",
            "null",
            "-",
        ]

        timeout = max(60, min(300, int(total_duration * 0.5) + 30))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            text = (result.stderr or "") + "\n" + (result.stdout or "")

            rms_pattern = re.compile(
                r"pts_time:(\d+(?:\.\d+)?)\s+"
                r"lavfi\.astats\.Overall\.RMS_level=(-?\d+(?:\.\d+)?)"
            )
            rms_by_time = {}
            for match in rms_pattern.finditer(text):
                t = float(match.group(1))
                rms_db = float(match.group(2))
                rms_by_time[t] = (
                    10 ** (rms_db / 20)
                    if math.isfinite(rms_db) and rms_db > -100
                    else 0.0
                )

            if not rms_by_time:
                # Si FFmpeg no encontró stream de audio, silences=None comunica
                # "señal no disponible", distinto de [] = audio continuo sin pausas.
                return {}, None

            window_scores: dict = {}
            max_time = max(rms_by_time)
            t = 0.0
            while t <= max_time + _SAMPLE_STEP:
                vals = [
                    value
                    for ts, value in rms_by_time.items()
                    if t <= ts < t + _SAMPLE_STEP
                ]
                if vals:
                    window_scores[round(t, 3)] = sum(vals) / len(vals)
                t += _SAMPLE_STEP

            audio_scores = _normalize_robust(window_scores)

            silences: List[Tuple[float, float]] = []
            current_start: Optional[float] = None
            event_pattern = re.compile(
                r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)"
            )
            for event in event_pattern.finditer(text):
                kind = event.group(1)
                value = max(0.0, float(event.group(2)))
                if kind == "start":
                    current_start = value
                elif current_start is not None:
                    silences.append(
                        (
                            min(current_start, total_duration),
                            min(value, total_duration),
                        )
                    )
                    current_start = None

            if current_start is not None and current_start < total_duration:
                silences.append((current_start, total_duration))

            return audio_scores, silences
        except Exception as e:
            logger.warning("Análisis de audio/silencios falló: %s", e)
            return {}, None

    @staticmethod
    def _detect_scene_cuts(
        video_path: str,
        total_duration: float,
    ) -> List[float]:
        # Reducir antes de scdet mantiene la señal de cortes y baja mucho el costo
        # en fuentes 4K.
        filter_chain = (
            "scale=320:-2:force_original_aspect_ratio=decrease,"
            f"scdet=threshold={_SCENE_CHANGE_THRESHOLD}"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i",
            video_path,
            "-an",
            "-vf",
            filter_chain,
            "-f",
            "null",
            "-",
        ]
        timeout = max(120, min(600, int(total_duration * 1.2) + 60))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            text = (result.stderr or "") + "\n" + (result.stdout or "")
            pattern = re.compile(
                r"lavfi\.scd\.time\s*[:=]\s*(\d+(?:\.\d+)?)"
            )
            return sorted(
                {
                    round(float(match.group(1)), 3)
                    for match in pattern.finditer(text)
                }
            )
        except Exception as e:
            logger.warning("Detección de escenas falló: %s", e)
            return []

    @staticmethod
    def _analyze_visual_signals(
        video_path: str,
        total_duration: float,
        detector,
        scene_cuts: List[float],
    ) -> Tuple[dict, dict]:
        import cv2

        sample_every = max(
            _BASE_VISUAL_SAMPLE_EVERY,
            total_duration / _MAX_VISUAL_SAMPLES,
        )

        face_scores: dict = {}
        motion_raw: dict = {}
        previous_gray = None
        previous_time: Optional[float] = None

        if hasattr(detector, "reset"):
            detector.reset()

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("No se pudo abrir el video para análisis visual")

        try:
            t = 0.0
            while t <= total_duration + 1e-9:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    t += sample_every
                    continue

                height, width = frame.shape[:2]
                if width > 960:
                    scale = 960.0 / width
                    frame = cv2.resize(
                        frame,
                        (960, max(2, int(height * scale))),
                        interpolation=cv2.INTER_AREA,
                    )

                sample_time = round(t, 3)

                faces = detector.detect(frame)
                face_scores[sample_time] = _face_sample_score(
                    faces,
                    frame.shape[1],
                    frame.shape[0],
                    detector,
                )

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if gray.shape[1] > 320:
                    scale = 320.0 / gray.shape[1]
                    gray = cv2.resize(
                        gray,
                        (320, max(2, int(gray.shape[0] * scale))),
                        interpolation=cv2.INTER_AREA,
                    )

                if previous_gray is not None and previous_time is not None:
                    if _has_scene_cut_between(
                        scene_cuts,
                        previous_time,
                        sample_time,
                    ):
                        # Un corte editorial no es movimiento del sujeto.
                        motion_raw[sample_time] = 0.0
                    else:
                        diff = cv2.absdiff(previous_gray, gray)
                        motion_raw[sample_time] = cv2.mean(diff)[0] / 255.0

                previous_gray = gray
                previous_time = sample_time
                t += sample_every
        finally:
            cap.release()
            if hasattr(detector, "reset"):
                detector.reset()

        return _smooth_scores(face_scores), _smooth_scores(
            _normalize_robust(motion_raw)
        )

    @staticmethod
    def _score_candidates(
        candidates: List[float],
        target_duration: int,
        audio_scores: dict,
        visual_scores: dict,
        scene_cuts: List[float],
        face_scores: Optional[dict],
        silences: Optional[List[Tuple[float, float]]],
        log_top: bool = True,
    ) -> Tuple[float, float, list]:
        has_faces = _has_meaningful_signal(face_scores or {})
        has_audio = _has_meaningful_signal(audio_scores)
        has_visual = _has_meaningful_signal(visual_scores)
        has_active_audio = silences is not None and has_audio

        available = []
        if has_faces:
            available.append(("faces", _WEIGHT_FACES))
        if has_active_audio:
            available.append(("active_audio", _WEIGHT_ACTIVE_AUDIO))
        if has_audio:
            available.append(("audio", _WEIGHT_AUDIO_ENERGY))
        if has_visual:
            available.append(("visual", _WEIGHT_VISUAL_ACTIVITY))

        total_weight = sum(weight for _, weight in available) or 1.0
        effective = {
            name: weight / total_weight
            for name, weight in available
        }

        best_start = candidates[0]
        best_score = -1.0
        detail = []

        for start in candidates:
            face_score = (
                _window_avg(face_scores or {}, start, target_duration)
                if has_faces
                else None
            )
            audio_score = (
                _window_avg(audio_scores, start, target_duration)
                if has_audio
                else None
            )
            visual_score = (
                _window_avg(visual_scores, start, target_duration)
                if has_visual
                else None
            )
            active_audio_score = (
                _active_audio_ratio(silences, start, target_duration)
                if has_active_audio
                else None
            )

            if available:
                base = 0.0
                if face_score is not None:
                    base += effective["faces"] * face_score
                if active_audio_score is not None:
                    base += effective["active_audio"] * active_audio_score
                if audio_score is not None:
                    base += effective["audio"] * audio_score
                if visual_score is not None:
                    base += effective["visual"] * visual_score
            else:
                base = 0.5

            hook = _hook_score(
                start=start,
                target_duration=target_duration,
                face_scores=face_scores or {},
                audio_scores=audio_scores,
                visual_scores=visual_scores,
                silences=silences if has_active_audio else None,
            )
            boundary = _boundary_score(
                start=start,
                duration=target_duration,
                scene_cuts=scene_cuts,
                silences=silences,
            )

            score = (
                _BASE_SCORE_WEIGHT * base
                + _HOOK_SCORE_WEIGHT * hook
                + _BOUNDARY_SCORE_WEIGHT * boundary
            )
            score = max(0.0, min(1.0, score))

            detail.append(
                {
                    "start": start,
                    "face": face_score,
                    "audio": audio_score,
                    "active_audio": active_audio_score,
                    "visual": visual_score,
                    "hook": hook,
                    "boundary": boundary,
                    "cuts": _count_cuts(
                        scene_cuts,
                        start,
                        target_duration,
                    ),
                    "score": score,
                }
            )

            if score > best_score:
                best_score = score
                best_start = start

        if log_top:
            for rank, entry in enumerate(
                sorted(
                    detail,
                    key=lambda x: x["score"],
                    reverse=True,
                )[:3],
                1,
            ):
                logger.debug(
                    "Top %d | start=%.2fs | face=%.2f | active=%.2f | "
                    "audio=%.2f | visual=%.2f | hook=%.2f | boundary=%.2f | "
                    "cuts=%d | score=%.3f",
                    rank,
                    entry["start"],
                    entry["face"] or 0,
                    entry["active_audio"] or 0,
                    entry["audio"] or 0,
                    entry["visual"] or 0,
                    entry["hook"],
                    entry["boundary"],
                    entry["cuts"],
                    entry["score"],
                )

        return best_start, best_score, detail

    @staticmethod
    def _central_segment(
        total_duration: float,
        target_duration: int,
    ) -> Tuple[float, int]:
        center = total_duration / 2.0
        start_time = max(
            0.0,
            center - target_duration / 2.0,
        )
        if start_time + target_duration > total_duration:
            start_time = total_duration - target_duration
        return round(start_time, 3), target_duration


def _face_sample_score(
    faces: list,
    frame_width: int,
    frame_height: int,
    detector,
) -> float:
    if not faces:
        return 0.0

    primary = (
        detector.get_primary_face(faces)
        if hasattr(detector, "get_primary_face")
        else faces[0]
    )
    if not primary:
        return 0.0

    _, _, width, height = primary.get("bbox", (0, 0, 0, 0))
    frame_area = max(1, frame_width * frame_height)
    area_ratio = max(0.0, width * height / frame_area)

    confidence = float(primary.get("confidence", 0.0) or 0.0)
    confidence = max(0.0, min(1.0, confidence))

    # Un rostro que ocupe ~2% del frame ya es suficientemente legible para
    # que el Smart Crop tenga una señal útil.
    size_score = max(0.0, min(1.0, area_ratio / 0.02))

    quality = primary.get("quality")
    stability = float(getattr(quality, "stability", 0.5) or 0.5)
    stability = max(0.0, min(1.0, stability))

    score = (
        0.45
        + 0.25 * confidence
        + 0.15 * size_score
        + 0.15 * stability
    )

    if primary.get("is_predicted"):
        score *= 0.70

    return max(0.0, min(1.0, score))


def _normalize_robust(scores: dict) -> dict:
    if not scores:
        return {}

    positive = sorted(
        value
        for value in scores.values()
        if value > 0 and math.isfinite(value)
    )
    if not positive:
        return {key: 0.0 for key in scores}

    # P90 evita que un golpe de audio o un cambio visual aislado aplaste
    # toda la escala del resto del video.
    index = min(
        len(positive) - 1,
        max(0, int(math.ceil(len(positive) * 0.90)) - 1),
    )
    reference = positive[index]
    if reference <= 0:
        return dict(scores)

    return {
        key: max(0.0, min(1.0, value / reference))
        for key, value in scores.items()
    }


def _smooth_scores(scores: dict) -> dict:
    if not scores:
        return {}

    times = sorted(scores)
    smoothed = {}
    for index, t in enumerate(times):
        neighbors = [
            scores[times[j]]
            for j in range(
                max(0, index - 1),
                min(len(times), index + 2),
            )
        ]
        smoothed[t] = sum(neighbors) / len(neighbors)
    return smoothed


def _has_meaningful_signal(scores: dict) -> bool:
    return bool(scores) and max(scores.values(), default=0.0) > 0.05


def _window_avg(
    scores: dict,
    start: float,
    duration: float,
) -> float:
    if not scores:
        return 0.5

    end = start + duration
    relevant = [
        value
        for t, value in scores.items()
        if start <= t < end
    ]

    if not relevant:
        midpoint = start + duration / 2.0
        closest = min(
            scores,
            key=lambda t: abs(t - midpoint),
        )
        return scores[closest]

    return sum(relevant) / len(relevant)


def _active_audio_ratio(
    silences: Optional[List[Tuple[float, float]]],
    start: float,
    duration: float,
) -> float:
    if silences is None:
        return 0.5

    if duration <= 0:
        return 0.0

    end = start + duration
    silent = 0.0
    for silence_start, silence_end in silences:
        overlap = max(
            0.0,
            min(end, silence_end) - max(start, silence_start),
        )
        silent += overlap

    return max(0.0, min(1.0, 1.0 - silent / duration))


def _hook_score(
    start: float,
    target_duration: int,
    face_scores: dict,
    audio_scores: dict,
    visual_scores: dict,
    silences: Optional[List[Tuple[float, float]]],
) -> float:
    hook_duration = min(3.0, float(target_duration))
    available = []

    if _has_meaningful_signal(face_scores):
        available.append(
            (0.40, _window_avg(face_scores, start, hook_duration))
        )
    if silences is not None and _has_meaningful_signal(audio_scores):
        available.append(
            (
                0.30,
                _active_audio_ratio(
                    silences,
                    start,
                    hook_duration,
                ),
            )
        )
    if _has_meaningful_signal(audio_scores):
        available.append(
            (0.15, _window_avg(audio_scores, start, hook_duration))
        )
    if _has_meaningful_signal(visual_scores):
        available.append(
            (0.15, _window_avg(visual_scores, start, hook_duration))
        )

    if not available:
        return 0.5

    total = sum(weight for weight, _ in available)
    return sum(
        weight * value
        for weight, value in available
    ) / total


def _boundary_score(
    start: float,
    duration: float,
    scene_cuts: List[float],
    silences: Optional[List[Tuple[float, float]]],
) -> float:
    end = start + duration

    start_boundaries = list(scene_cuts)
    end_boundaries = list(scene_cuts)

    if silences:
        start_boundaries.extend(
            silence_end
            for _, silence_end in silences
        )
        end_boundaries.extend(
            silence_start
            for silence_start, _ in silences
        )

    if not start_boundaries and not end_boundaries:
        return 0.5

    start_score = _boundary_proximity(
        start,
        start_boundaries,
    )
    end_score = _boundary_proximity(
        end,
        end_boundaries,
    )
    return (start_score + end_score) / 2.0


def _boundary_proximity(
    value: float,
    boundaries: List[float],
    window: float = 1.5,
) -> float:
    if not boundaries:
        return 0.5

    distance = min(
        abs(value - boundary)
        for boundary in boundaries
    )
    if distance >= window:
        return 0.0
    return 1.0 - distance / window


def _has_scene_cut_between(
    scene_cuts: List[float],
    start: float,
    end: float,
) -> bool:
    return any(start < cut <= end for cut in scene_cuts)


def _count_cuts(
    scene_cuts: List[float],
    start: float,
    duration: float,
) -> int:
    margin = 0.5
    end = start + duration
    return sum(
        1
        for cut in scene_cuts
        if (start + margin) < cut < (end - margin)
    )
