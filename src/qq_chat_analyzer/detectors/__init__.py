"""Candidate detectors for Smart Profile discovery."""

from .robot_detector import detect_robot_candidates
from .template_detector import detect_template_candidates


__all__ = [
    "detect_robot_candidates",
    "detect_template_candidates",
]
