"""Flask web app: upload a file or paste a URL, get a deepfake verdict.

Run it with::

    python -m deepfake_detector.app          # or: flask --app deepfake_detector.app run

Credentials can come from two places:

* the server's `.env` (see config.py) -- convenient when you run it yourself, and
* the web UI -- so you can share this app with a customer who enters their OWN
  BytePlus AK/SK and AppID, without ever seeing yours.

Credentials entered in the UI are used only for that single request to build the
client; they are never logged, never persisted server-side, and take precedence
over `.env`. If neither source has credentials, the UI asks the user to enter them.
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, render_template, request

from .config import ConfigError, Settings
from .detector import DeepfakeDetector
from .media import IMAGE_EXTS, MediaError, VIDEO_EXTS, VIDEO_MAX_BYTES
from .results import DetectionError

logger = logging.getLogger("deepfake_detector")

# Cap request bodies at the largest sample we accept (video), plus a little
# overhead for multipart framing.
MAX_CONTENT_LENGTH = VIDEO_MAX_BYTES + (1 * 1024 * 1024)


def _env_settings() -> tuple[Settings | None, str]:
    """Load optional server-side settings from .env. Returns (settings, error)."""
    try:
        return Settings.from_env(), ""
    except ConfigError as exc:
        return None, str(exc)


def _settings_for_request(form, env_settings: Settings | None) -> Settings | None:
    """Resolve which credentials to use for this request.

    UI-provided credentials win. If the user supplied any credential field, we
    build settings from those (region/endpoint fall back to the server's when
    left blank). If the user supplied none, we use the server's .env settings
    (which may be None when the app is shared without any server credentials).
    """
    ak = (form.get("ak") or "").strip()
    sk = (form.get("sk") or "").strip()
    appid = (form.get("appid") or "").strip()
    region = (form.get("region") or "").strip()
    endpoint = (form.get("endpoint") or "").strip()

    if not any((ak, sk, appid, region, endpoint)):
        return env_settings  # no overrides -> use server config (may be None)

    # Region/endpoint/timeout may sensibly inherit from the server defaults;
    # AK/SK/AppID must be supplied by the user (validated in from_values).
    return Settings.from_values(
        ak=ak,
        sk=sk,
        appid=appid,
        region=region or (env_settings.region if env_settings else "ap-southeast-1"),
        endpoint=endpoint,
        timeout=env_settings.timeout if env_settings else None,
    )


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    env_settings, config_error = _env_settings()

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            has_server_creds=env_settings is not None,
            server_settings=env_settings.masked() if env_settings else None,
            image_exts=sorted(IMAGE_EXTS),
            video_exts=sorted(VIDEO_EXTS),
        )

    @app.get("/api/health")
    def health():
        # Only ever expose masked, non-secret info about the server's own config.
        return jsonify(
            {
                "status": "ok" if env_settings else "no-server-creds",
                "has_server_creds": env_settings is not None,
                "config_error": config_error,
                "settings": env_settings.masked() if env_settings else None,
            }
        )

    @app.post("/api/detect")
    def detect():
        role = (request.form.get("role") or "user").strip() or "user"
        url = (request.form.get("url") or "").strip()
        upload = request.files.get("file")

        # Resolve credentials (UI overrides win; else server .env).
        try:
            settings = _settings_for_request(request.form, env_settings)
        except ConfigError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        if settings is None:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "No BytePlus credentials. Open the "
                        "“BytePlus credentials” section and enter your "
                        "Access Key, Secret Key, and AppID.",
                        "need_credentials": True,
                    }
                ),
                400,
            )

        detector = DeepfakeDetector(settings)

        try:
            if upload and upload.filename:
                data = upload.read()
                result = detector.detect_bytes(
                    data, upload.filename, role=role, source="upload"
                )
            elif url:
                result = detector.detect_url(url, role=role)
            else:
                return jsonify({"ok": False, "error": "Provide a file or a URL."}), 400
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
