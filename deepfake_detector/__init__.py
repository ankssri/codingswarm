"""Deepfake detection app built on the BytePlus LLM Application Firewall SDK.

This is a small, self-contained application (separate from CodeSwarm) that lets a
user submit an image or video -- as a direct file, a local path, or a URL -- and
runs it through BytePlus deepfake detection, returning a clear verdict.

Public API:

    from deepfake_detector import DeepfakeDetector, Settings, DetectionResult

Secrets (AK/SK, AppID, region) are read from a `.env` file and are never logged.
"""

from .config import Settings
from .detector import DeepfakeDetector
from .results import DetectionResult, Risk

__all__ = ["Settings", "DeepfakeDetector", "DetectionResult", "Risk"]

__version__ = "0.1.0"
