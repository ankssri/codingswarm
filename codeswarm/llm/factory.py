"""Build provider instances from resolved config."""

from __future__ import annotations

import os

from .base import LLMProvider
from .providers import MockProvider, OpenAICompatibleProvider


def _sanitize_key(raw: str) -> str:
    """Defensively clean a pasted API key.

    Strips surrounding whitespace/newlines, a stray pair of wrapping quotes, and
    an accidental leading 'Bearer ' — all common copy-paste mistakes that make a
    server reject the key as malformed.
    """
    key = (raw or "").strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        key = key[1:-1].strip()
    if key.lower().startswith("bearer "):
        key = key[len("bearer "):].strip()
    return key


def key_fingerprint(raw: str) -> str:
    """A masked, safe-to-log identifier for a key (never reveals the secret)."""
    key = _sanitize_key(raw)
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return f"len={len(key)}"
    return f"{key[:4]}…{key[-2:]} (len={len(key)})"


def build_provider(provider_name: str, provider_cfg: dict, *, model_override: str | None = None) -> LLMProvider:
    """Instantiate a provider from its config block.

    Args:
        provider_name: key such as "byteplus" | "openai" | "gemini" | "mock".
        provider_cfg: the matching entry from config["providers"].
        model_override: optional per-role model id.
    """
    model = model_override or provider_cfg.get("model")

    if provider_name == "mock":
        return MockProvider(model=model or "mock")

    if not model:
        raise ValueError(f"No model configured for provider '{provider_name}'.")

    api_key_env = provider_cfg.get("api_key_env", "")
    raw_key = os.environ.get(api_key_env, "") if api_key_env else ""
    api_key = _sanitize_key(raw_key)
    if not api_key:
        raise ValueError(
            f"Missing API key for provider '{provider_name}'. "
            f"Set the '{api_key_env}' environment variable (or add it to your .env file), "
            f"or run with --dry-run to use the offline mock provider."
        )

    return OpenAICompatibleProvider(
        name=provider_name,
        model=model,
        api_key=api_key,
        base_url=provider_cfg.get("base_url", ""),
    )
