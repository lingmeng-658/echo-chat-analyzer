"""Candidate detectors for Smart Profile discovery."""

from .interactive_bot_detector import detect_interactive_bot_candidates
from .robot_detector import detect_robot_candidates
from .template_detector import detect_template_candidates


__all__ = [
    "detect_interactive_bot_candidates",
    "detect_robot_candidates",
    "detect_template_candidates",
]
