"""Configuration for the deepfake detector.

All credentials are loaded from environment variables (typically populated from a
`.env` file via python-dotenv). Secrets are NEVER written to logs or serialized
into API responses -- see ``Settings.masked()`` for the only representation that
is safe to display.

Environment variables
---------------------
BYTEPLUS_LLM_FIREWALL_AK       Access Key ID of your BytePlus account.       (required)
BYTEPLUS_LLM_FIREWALL_SK       Secret Access Key of your BytePlus account.   (required)
BYTEPLUS_DEEPFAKE_APPID        Asset AppID configured for SDK + Deepfake.    (required)
BYTEPLUS_DEEPFAKE_REGION       Instance region. Default: ap-southeast-1.
BYTEPLUS_DEEPFAKE_ENDPOINT     Full service endpoint. Derived from region if unset.
BYTEPLUS_DEEPFAKE_TIMEOUT      SDK request timeout in seconds. Default: 50.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is optional at import time but recommended.
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is a declared dependency
    load_dotenv = None


# Regions the LLM Application Firewall is offered in. Used only to build the
# endpoint URL when one is not supplied explicitly.
KNOWN_REGIONS = ("ap-southeast-1", "cn-hongkong")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _endpoint_for_region(region: str) -> str:
    return f"https://{region}.sdk.access-bp.llm-shield.omni-shield.ai"


@dataclass(frozen=True)
class Settings:
    """Immutable, validated runtime configuration."""

    ak: str
    sk: str
    appid: str
    region: str = "ap-southeast-1"
    endpoint: str = ""
    timeout: float = 50.0

    def __post_init__(self) -> None:
        # Derive the endpoint from the region when it was not provided.
        if not self.endpoint:
            object.__setattr__(self, "endpoint", _endpoint_for_region(self.region))

    # -- construction --------------------------------------------------------

    @classmethod
    def from_env(cls, *, load_env_file: bool = True, env_path: str | None = None) -> "Settings":
        """Build settings from the process environment / a `.env` file.

        Raises ``ConfigError`` listing every missing required variable so the UI
        can show one actionable message.
        """
        if load_env_file and load_dotenv is not None:
            # `.env` lives at the repo root by default; override with env_path.
            path = Path(env_path) if env_path else Path.cwd() / ".env"
            if path.exists():
                load_dotenv(path, override=False)
            else:
                load_dotenv(override=False)  # fall back to a discoverable .env

        ak = os.getenv("BYTEPLUS_LLM_FIREWALL_AK", "").strip()
        sk = os.getenv("BYTEPLUS_LLM_FIREWALL_SK", "").strip()
        appid = os.getenv("BYTEPLUS_DEEPFAKE_APPID", "").strip()
        region = os.getenv("BYTEPLUS_DEEPFAKE_REGION", "ap-southeast-1").strip() or "ap-southeast-1"
        endpoint = os.getenv("BYTEPLUS_DEEPFAKE_ENDPOINT", "").strip()
        timeout_raw = os.getenv("BYTEPLUS_DEEPFAKE_TIMEOUT", "50").strip()

        missing = [
            name
            for name, value in (
                ("BYTEPLUS_LLM_FIREWALL_AK", ak),
                ("BYTEPLUS_LLM_FIREWALL_SK", sk),
                ("BYTEPLUS_DEEPFAKE_APPID", appid),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in the deepfake section."
            )

        try:
            timeout = float(timeout_raw)
        except ValueError:
            raise ConfigError(
                f"BYTEPLUS_DEEPFAKE_TIMEOUT must be a number, got {timeout_raw!r}."
            )

        return cls(
            ak=ak,
            sk=sk,
            appid=appid,
            region=region,
            endpoint=endpoint,
            timeout=timeout,
        )

    @classmethod
    def from_values(
        cls,
        *,
        ak: str,
        sk: str,
        appid: str,
        region: str | None = None,
        endpoint: str | None = None,
        timeout: float | None = None,
    ) -> "Settings":
        """Build settings from explicit values (e.g. entered in the web UI).

        Validates the three required credentials and raises ``ConfigError``
        listing whatever is missing, so the UI can show one clear message.
        """
        ak = (ak or "").strip()
        sk = (sk or "").strip()
        appid = (appid or "").strip()
        region = (region or "").strip() or "ap-southeast-1"
        endpoint = (endpoint or "").strip()

        missing = [
            name
            for name, value in (("Access Key (AK)", ak), ("Secret Key (SK)", sk), ("AppID", appid))
            if not value
        ]
        if missing:
            raise ConfigError("Missing required credential(s): " + ", ".join(missing) + ".")

        return cls(
            ak=ak,
            sk=sk,
            appid=appid,
            region=region,
            endpoint=endpoint,
            timeout=float(timeout) if timeout else 50.0,
        )

    # -- safe representations ------------------------------------------------

    @staticmethod
    def _mask(secret: str) -> str:
        if not secret:
            return ""
        if len(secret) <= 4:
            return "****"
        return f"{secret[:4]}{'*' * 6}"

    def masked(self) -> dict:
        """A dict safe to log or return to the UI. Secrets are truncated."""
        return {
            "ak": self._mask(self.ak),
            "sk": self._mask(self.sk),
            "appid": self.appid,
            "region": self.region,
            "endpoint": self.endpoint,
            "timeout": self.timeout,
        }

    def __repr__(self) -> str:  # never leak secrets via repr()
        m = self.masked()
        return (
            "Settings(ak={ak!r}, sk={sk!r}, appid={appid!r}, region={region!r}, "
            "endpoint={endpoint!r}, timeout={timeout!r})".format(**m)
        )
