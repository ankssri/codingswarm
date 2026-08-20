"""Flask web app: upload a file or paste a URL, get a deepfake verdict.

Run it with::

    python -m deepfake_detector.app          # or: flask --app deepfake_detector.app run

The credentials come from `.env` (see config.py). If they are missing, the app
still starts and shows a clear configuration banner instead of crashing.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .config import ConfigError, Settings
from .detector import DeepfakeDetector
from .media import IMAGE_EXTS, MediaError, VIDEO_EXTS, VIDEO_MAX_BYTES
from .results import DetectionError

logger = logging.getLogger("deepfake_detector")

# Cap request bodies at the largest sample we accept (video), plus a little
# overhead for multipart framing.
MAX_CONTENT_LENGTH = VIDEO_MAX_BYTES + (1 * 1024 * 1024)


def _load_detector() -> tuple[DeepfakeDetector | None, str]:
    """Try to build a detector. Returns (detector, error_message)."""
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        return None, str(exc)
    return DeepfakeDetector(settings), ""


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    detector, config_error = _load_detector()

    @app.get("/")
    def index():
        config_ok = detector is not None
        return render_template(
            "index.html",
            config_ok=config_ok,
            config_error=config_error,
            settings=detector.settings.masked() if detector else None,
            image_exts=sorted(IMAGE_EXTS),
            video_exts=sorted(VIDEO_EXTS),
        )

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok" if detector else "unconfigured",
                "config_error": config_error,
                "settings": detector.settings.masked() if detector else None,
            }
        )

    @app.post("/api/detect")
    def detect():
        if detector is None:
            return jsonify({"ok": False, "error": config_error}), 503

        role = (request.form.get("role") or "user").strip() or "user"
        url = (request.form.get("url") or "").strip()
        upload = request.files.get("file")

        try:
            if upload and upload.filename:
                data = upload.read()
                result = detector.detect_bytes(
                    data, upload.filename, role=role, source="upload"
                )
            elif url:
                result = detector.detect_url(url, role=role)
            else:
                return (
                    jsonify({"ok": False, "error": "Provide a file or a URL."}),
                    400,
                )
        except MediaError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except DetectionError as exc:
            logger.warning("Detection error (request_id=%s): %s", exc.request_id, exc)
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": str(exc),
                        "code": exc.code,
                        "request_id": exc.request_id,
                    }
                ),
                502,
            )
        except Exception as exc:  # noqa: BLE001 - surface a clean message to the UI
            logger.exception("Unexpected detection failure")
            return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500

        return jsonify({"ok": True, "result": result.to_dict()})

    @app.errorhandler(413)
    def too_large(_):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": f"File too large. Videos up to "
                    f"{VIDEO_MAX_BYTES // 1024 // 1024} MB, images up to 10 MB.",
                }
            ),
            413,
        )

    return app


app = create_app()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    import os

    host = os.getenv("DEEPFAKE_HOST", "127.0.0.1")
    port = int(os.getenv("DEEPFAKE_PORT", "5000"))
    debug = os.getenv("DEEPFAKE_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
