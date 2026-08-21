from collections import deque
from threading import local
from typing import Dict, List

import cv2
import mediapipe as mp
import numpy as np


_thread_state = local()


def get_hybrid_profile() -> List[float]:
    """Devuelve el perfil de ancho relativo registrado por el job actual."""
    return list(getattr(_thread_state, "hybrid_profile", []))


def clear_hybrid_profile() -> None:
    _thread_state.hybrid_profile = []


class SubjectFramer:
    """Estima un centro horizontal de sujeto combinando rostro y torso."""

    _CENTER_LANDMARKS = (
        mp.solutions.pose.PoseLandmark.LEFT_SHOULDER,
        mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER,
        mp.solutions.pose.PoseLandmark.LEFT_HIP,
        mp.solutions.pose.PoseLandmark.RIGHT_HIP,
    )
    _WIDTH_LANDMARKS = (
        *_CENTER_LANDMARKS,
        mp.solutions.pose.PoseLandmark.LEFT_ELBOW,
        mp.solutions.pose.PoseLandmark.RIGHT_ELBOW,
        mp.solutions.pose.PoseLandmark.LEFT_WRIST,
        mp.solutions.pose.PoseLandmark.RIGHT_WRIST,
    )

    def __init__(self, min_visibility: float = 0.45):
        self.min_visibility = min_visibility
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=0,
            enable_segmentation=False,
            min_detection_confidence=0.50,
            min_tracking_confidence=0.50,
        )
        self.pose_attempts = 0
        self.pose_detections = 0
        self._center_history = deque(maxlen=5)
        self._required_width_ratios: List[float] = []
        clear_hybrid_profile()

    def analyze(self, frame, face: dict) -> Dict[str, float]:
        frame_h, frame_w = frame.shape[:2]
        face_x, _, face_w, _ = face["bbox"]
        face_left = float(np.clip(face_x, 0, frame_w))
        face_right = float(np.clip(face_x + face_w, 0, frame_w))
        face_center = float(face["center"][0])

        subject = {
            "center_x": face_center,
            "left": face_left,
            "right": face_right,
            "hybrid_left": face_left,
            "hybrid_right": face_right,
            "face_left": face_left,
            "face_right": face_right,
            "face_width": float(max(1, face_w)),
            "pose_detected": False,
        }

        self.pose_attempts += 1
        result = self.pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not result.pose_landmarks:
            subject = self._smooth_center(subject)
            self._record_required_width(subject, frame_w, frame_h)
            return subject

        center_x = self._visible_x(result, self._CENTER_LANDMARKS, frame_w)
        width_x = self._visible_x(result, self._WIDTH_LANDMARKS, frame_w)

        if len(center_x) < 2:
            subject = self._smooth_center(subject)
            self._record_required_width(subject, frame_w, frame_h)
            return subject

        torso_left = min(center_x)
        torso_right = max(center_x)
        torso_width = max(1.0, torso_right - torso_left)
        torso_center = (torso_left + torso_right) / 2.0
        expansion = max(face_w * 0.15, torso_width * 0.18)

        subject["left"] = float(np.clip(min(face_left, torso_left - expansion), 0, frame_w))
        subject["right"] = float(np.clip(max(face_right, torso_right + expansion), 0, frame_w))
        subject["center_x"] = face_center * 0.55 + torso_center * 0.45
        subject["pose_detected"] = True
        subject["torso_center_x"] = torso_center

        # Brazos y manos solo amplían el perfil usado por el zoom-out híbrido.
        # No alteran el centro ni la ventana normal de Smart Crop.
        if len(width_x) >= 2:
            body_left = min(width_x)
            body_right = max(width_x)
            body_width = max(1.0, body_right - body_left)
            hybrid_expansion = max(face_w * 0.15, body_width * 0.10)
            subject["hybrid_left"] = float(
                np.clip(min(subject["left"], body_left - hybrid_expansion), 0, frame_w)
            )
            subject["hybrid_right"] = float(
                np.clip(max(subject["right"], body_right + hybrid_expansion), 0, frame_w)
            )
        else:
            subject["hybrid_left"] = subject["left"]
            subject["hybrid_right"] = subject["right"]

        self.pose_detections += 1
        subject = self._smooth_center(subject)
        self._record_required_width(subject, frame_w, frame_h)
        return subject

    def get_stats(self) -> dict:
        ratios = self._required_width_ratios
        return {
            "pose_attempts": self.pose_attempts,
            "pose_detections": self.pose_detections,
            "hybrid_profile_samples": len(ratios),
            "max_required_width_ratio": max(ratios) if ratios else 1.0,
        }

    def close(self) -> None:
        _thread_state.hybrid_profile = list(self._required_width_ratios)
        self.pose.close()

    def _smooth_center(self, subject: dict) -> dict:
        self._center_history.append(float(subject["center_x"]))
        recent = list(self._center_history)
        if len(recent) >= 3:
            median_center = float(np.median(recent[-3:]))
            subject["center_x"] = subject["center_x"] * 0.70 + median_center * 0.30
        return subject

    def _visible_x(self, result, landmark_ids, frame_w: int) -> List[float]:
        visible = []
        for landmark_id in landmark_ids:
            landmark = result.pose_landmarks.landmark[int(landmark_id)]
            if landmark.visibility >= self.min_visibility:
                visible.append(float(np.clip(landmark.x * frame_w, 0, frame_w)))
        return visible

    def _record_required_width(self, subject: dict, frame_w: int, frame_h: int) -> None:
        """Registra cuánto ancho necesita el sujeto respecto al crop vertical base."""
        if frame_w <= 0 or frame_h <= 0:
            self._required_width_ratios.append(1.0)
            return

        base_crop_w = min(float(frame_w), float(frame_h) * 9.0 / 16.0)
        if base_crop_w <= 1.0:
            self._required_width_ratios.append(1.0)
            return

        subject_left = float(np.clip(subject.get("hybrid_left", subject.get("left", 0.0)), 0, frame_w))
        subject_right = float(
            np.clip(subject.get("hybrid_right", subject.get("right", frame_w)), 0, frame_w)
        )
        subject_width = max(1.0, subject_right - subject_left)
        face_width = float(max(1.0, subject.get("face_width", 1.0)))

        margin = max(
            face_width * 0.25,
            base_crop_w * 0.08,
            subject_width * 0.08,
        )
        required_width = min(float(frame_w), subject_width + margin * 2.0)
        ratio = required_width / base_crop_w
        self._required_width_ratios.append(float(np.clip(ratio, 0.25, 2.50)))
