"""Tests for the deepfake_detector app.

These run without BytePlus credentials or network access: the detector is given
a fake client, and media is built from in-memory bytes.
"""

from __future__ import annotations

import base64
import struct

import pytest

from deepfake_detector import DeepfakeDetector, Settings
from deepfake_detector.config import ConfigError
from deepfake_detector import media as media_mod
from deepfake_detector.media import MediaError
from deepfake_detector.results import DetectionError, DetectionResult


# --- tiny valid-ish samples -------------------------------------------------

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
AVI_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"AVI " + b"\x00" * 64
MP4_BYTES = b"\x00\x00\x00\x18" + b"ftyp" + b"isom" + b"\x00" * 64


# --- config -----------------------------------------------------------------

def test_settings_missing_required(monkeypatch):
    for k in ("BYTEPLUS_LLM_FIREWALL_AK", "BYTEPLUS_LLM_FIREWALL_SK", "BYTEPLUS_DEEPFAKE_APPID"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ConfigError) as exc:
        Settings.from_env(load_env_file=False)
    msg = str(exc.value)
    assert "BYTEPLUS_LLM_FIREWALL_AK" in msg
    assert "BYTEPLUS_DEEPFAKE_APPID" in msg


def test_settings_endpoint_derived_from_region():
    s = Settings(ak="AKxxxx", sk="SKyyyy", appid="app-1", region="cn-hongkong")
    assert s.endpoint == "https://cn-hongkong.sdk.access-bp.llm-shield.omni-shield.ai"


def test_settings_masked_hides_secrets():
    s = Settings(ak="AKLTYWRhNDMwSECRET", sk="TWprNE5XVXlZSECRET", appid="app-1")
    masked = s.masked()
    assert "SECRET" not in masked["ak"]
    assert "SECRET" not in masked["sk"]
    assert masked["ak"].endswith("******")
    # repr must not leak either
    assert "SECRET" not in repr(s)


# --- media ------------------------------------------------------------------

@pytest.mark.parametrize("data,name,kind,ext", [
    (PNG_BYTES, "a.png", "image", "png"),
    (JPG_BYTES, "a.jpg", "image", "jpg"),
    (JPG_BYTES, "a.jpeg", "image", "jpeg"),
    (WEBP_BYTES, "a.webp", "image", "webp"),
    (MP4_BYTES, "clip.mp4", "video", "mp4"),
    (AVI_BYTES, "clip.avi", "video", "avi"),
])
def test_media_from_bytes_by_extension(data, name, kind, ext):
    m = media_mod.from_bytes(data, name)
    assert m.kind == kind
    assert m.ext == ext


def test_media_sniffs_extension_when_missing():
    m = media_mod.from_bytes(PNG_BYTES, "")  # no filename -> sniff magic bytes
    assert m.kind == "image"
    assert m.ext == "png"


def test_media_rejects_unsupported():
    with pytest.raises(MediaError):
        media_mod.from_bytes(b"GIF89a" + b"\x00" * 32, "a.gif")


def test_media_rejects_empty():
    with pytest.raises(MediaError):
        media_mod.from_bytes(b"", "a.png")


def test_media_rejects_oversized_image():
    big = PNG_BYTES + b"\x00" * (media_mod.IMAGE_MAX_BYTES + 1)
    with pytest.raises(MediaError):
        media_mod.from_bytes(big, "a.png")


# --- result parsing ---------------------------------------------------------

def _manip_response():
    return {
        "ResponseMetadata": {"Error": {"Code": "", "Message": ""}, "RequestId": "req-1"},
        "Result": {
            "MsgID": "msg-1",
            "RiskInfo": {"Risks": [{"Category": "109", "Label": "10900000", "Prob": 1.0}]},
            "Decision": {"DecisionType": 2, "HitStrategyIDs": ["rule-abc"]},
            "ContentInfo": "png",
            "Degraded": False,
        },
    }


def _authentic_response():
    return {
        "ResponseMetadata": {"Error": {"Code": "", "Message": ""}, "RequestId": "req-2"},
        "Result": {
            "MsgID": "msg-2",
            "RiskInfo": {"Risks": []},
            "Decision": {"DecisionType": 1, "HitStrategyIDs": []},
            "ContentInfo": "mp4",
            "Degraded": False,
        },
    }


def test_result_manipulated():
    r = DetectionResult.from_response_dict(_manip_response())
    assert r.manipulated is True
    assert r.verdict == "Manipulated"
    assert r.probability == 1.0
    assert r.decision_type == 2
    assert r.hit_strategy_ids == ["rule-abc"]
    assert r.risks[0].is_deepfake
    assert "manipulated" in r.summary.lower()


def test_result_authentic():
    r = DetectionResult.from_response_dict(_authentic_response())
    assert r.manipulated is False
    assert r.verdict == "Authentic"
    assert r.decision_type == 1


def test_result_error_raises():
    bad = {
        "ResponseMetadata": {"Error": {"Code": "InvalidAppId", "Message": "bad app"}, "RequestId": "r"},
        "Result": {},
    }
    with pytest.raises(DetectionError) as exc:
        DetectionResult.from_response_dict(bad)
    assert exc.value.code == "InvalidAppId"


def test_result_to_dict_roundtrip():
    r = DetectionResult.from_response_dict(_manip_response())
    d = r.to_dict()
    assert d["manipulated"] is True
    assert d["decision_name"].startswith("Block")
    assert d["risks"][0]["label_name"] == "Deepfake / manipulated media"


# --- detector with a fake client -------------------------------------------

class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def model_dump(self, by_alias=True):
        return self._data


class _FakeClient:
    def __init__(self, data):
        self._data = data
        self.last_request = None

    def Moderate(self, request):
        self.last_request = request
        return _FakeResponse(self._data)


def _settings():
    return Settings(ak="AKxxxx", sk="SKyyyy", appid="app-test", region="ap-southeast-1")


def test_detector_detect_bytes_image():
    client = _FakeClient(_manip_response())
    det = DeepfakeDetector(_settings(), client=client)
    result = det.detect_bytes(PNG_BYTES, "face.png")
    assert result.manipulated is True
    # request carried the base64 of our bytes and the asset id
    assert client.last_request.scene == "app-test"
    assert client.last_request.message.content == base64.b64encode(PNG_BYTES).decode()


def test_detector_detect_bytes_video_authentic():
    client = _FakeClient(_authentic_response())
    det = DeepfakeDetector(_settings(), client=client)
    result = det.detect_bytes(MP4_BYTES, "clip.mp4")
    assert result.manipulated is False
    assert result.content_format in ("mp4",)


def test_detector_rejects_unsupported_before_calling_api():
    client = _FakeClient(_authentic_response())
    det = DeepfakeDetector(_settings(), client=client)
    with pytest.raises(MediaError):
        det.detect_bytes(b"GIF89a" + b"\x00" * 16, "a.gif")
    assert client.last_request is None
