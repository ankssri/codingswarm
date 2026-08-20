"""The detector: encode a sample and run it through BytePlus deepfake detection.

The BytePlus SDK (``byteplussdkllmshield``) is imported lazily so this module can
be imported -- and unit-tested with a fake client -- without the SDK or any
network access being present.
"""

from __future__ import annotations

import base64
from typing import Any

from . import media as media_mod
from .config import Settings
from .media import Media
from .results import DetectionError, DetectionResult


def _build_client(settings: Settings):
    """Create a real BytePlus ClientV2 from settings (lazy import)."""
    from byteplussdkllmshield import ClientV2

    return ClientV2(
        settings.endpoint,
        settings.ak,
        settings.sk,
        settings.region,
        settings.timeout,
    )


def _content_type_for(kind: str):
    from byteplussdkllmshield import ContentTypeV2

    return ContentTypeV2.IMAGE if kind == "image" else ContentTypeV2.VIDEO


class DeepfakeDetector:
    """Submits images/videos to BytePlus and returns structured verdicts.

    Parameters
    ----------
    settings:
        Validated credentials/endpoint. See ``Settings.from_env``.
    client:
        Optional pre-built client. Injecting one lets tests supply a fake that
        implements ``Moderate(request)`` without touching the network.
    client_factory:
        Optional callable ``(settings) -> client``; defaults to the real SDK.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any | None = None,
        client_factory=None,
    ) -> None:
        self.settings = settings
        self._client = client
        self._client_factory = client_factory or _build_client

    @property
    def client(self):
        if self._client is None:
            self._client = self._client_factory(self.settings)
        return self._client

    # -- request building ----------------------------------------------------

    def _build_request(self, sample: Media, *, role: str = "user"):
        from byteplussdkllmshield import MessageV2, ModerateV2Request

        content = base64.b64encode(sample.data).decode("utf-8")
        return ModerateV2Request(
            scene=self.settings.appid,
            message=MessageV2(
                role=role,
                content=content,
                content_type=_content_type_for(sample.kind),
            ),
        )

    @staticmethod
    def _response_to_dict(response) -> dict:
        """Serialize an SDK response (Pydantic) to a plain aliased dict."""
        if response is None:
            raise DetectionError("Empty response from the detection service.")
        if hasattr(response, "model_dump"):
            return response.model_dump(by_alias=True)
        if hasattr(response, "to_dict"):
            return response.to_dict()
        if isinstance(response, dict):
            return response
        raise DetectionError(f"Unrecognized response type: {type(response)!r}")

    # -- public detection API ------------------------------------------------

    def detect(self, sample: Media, *, role: str = "user") -> DetectionResult:
        """Run detection on an already-validated ``Media`` sample."""
        request = self._build_request(sample, role=role)
        response = self.client.Moderate(request)
        data = self._response_to_dict(response)
        result = DetectionResult.from_response_dict(data)
        # Prefer the format we validated locally if the server omits it.
        if not result.content_format:
            result.content_format = sample.ext
        return result

    def detect_bytes(
        self, data: bytes, filename: str = "", *, role: str = "user", source: str = "upload"
    ) -> DetectionResult:
        sample = media_mod.from_bytes(data, filename, source=source)
        return self.detect(sample, role=role)

    def detect_file(self, path, *, role: str = "user") -> DetectionResult:
        sample = media_mod.from_path(path)
        return self.detect(sample, role=role)

    def detect_url(self, url: str, *, role: str = "user", timeout: float = 30.0) -> DetectionResult:
        sample = media_mod.from_url(url, timeout=timeout)
        return self.detect(sample, role=role)
