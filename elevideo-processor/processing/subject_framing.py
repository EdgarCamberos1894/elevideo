from collections import deque
from typing import Dict

import cv2
import mediapipe as mp
import numpy as np


class SubjectFramer:
    """Estima un centro horizontal de sujeto combinando rostro y torso."""

    _POSE_LANDMARKS = (
        mp.solutions.pose.PoseLandmark.LEFT_SHOULDER,
        mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER,
        mp.solutions.pose.PoseLandmark.LEFT_HIP,
        mp.solutions.pose.PoseLandmark.RIGHT_HIP,
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
            "face_left": face_left,
            "face_right": face_right,
            "face_width": float(max(1, face_w)),
            "pose_detected": False,
        }

        self.pose_attempts += 1
        result = self.pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not result.pose_landmarks:
            return self._smooth_center(subject)

        visible_x = []
        for landmark_id in self._POSE_LANDMARKS:
            landmark = result.pose_landmarks.landmark[int(landmark_id)]
            if landmark.visibility >= self.min_visibility:
                visible_x.append(float(np.clip(landmark.x * frame_w, 0, frame_w)))

        if len(visible_x) < 2:
            return self._smooth_center(subject)

        torso_left = min(visible_x)
        torso_right = max(visible_x)
        torso_width = max(1.0, torso_right - torso_left)
        torso_center = (torso_left + torso_right) / 2.0
        expansion = max(face_w * 0.15, torso_width * 0.18)

        subject["left"] = float(np.clip(min(face_left, torso_left - expansion), 0, frame_w))
        subject["right"] = float(np.clip(max(face_right, torso_right + expansion), 0, frame_w))
        subject["center_x"] = face_center * 0.55 + torso_center * 0.45
        subject["pose_detected"] = True
        subject["torso_center_x"] = torso_center
        self.pose_detections += 1
        return self._smooth_center(subject)

    def get_stats(self) -> dict:
        return {
            "pose_attempts": self.pose_attempts,
            "pose_detections": self.pose_detections,
        }

    def close(self) -> None:
        self.pose.close()

    def _smooth_center(self, subject: dict) -> dict:
        self._center_history.append(float(subject["center_x"]))
        recent = list(self._center_history)
        if len(recent) >= 3:
            median_center = float(np.median(recent[-3:]))
            subject["center_x"] = subject["center_x"] * 0.70 + median_center * 0.30
        return subject
