"""Command-line interface for the deepfake detector.

Examples
--------
    python -m deepfake_detector.cli ./photo.png
    python -m deepfake_detector.cli https://example.com/clip.mp4 --role assistant
    python -m deepfake_detector.cli ./photo.png --json
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse

from .config import ConfigError, Settings
from .detector import DeepfakeDetector
from .media import MediaError
from .results import DetectionError, DetectionResult


def _is_url(target: str) -> bool:
    return urlparse(target).scheme in ("http", "https")


def _print_human(result: DetectionResult) -> None:
    mark = "⚠ MANIPULATED" if result.manipulated else "✓ AUTHENTIC"
    print(f"\n{mark}")
    print(f"  {result.summary}")
    print(f"  Decision : {result.decision_name} ({result.decision_type})")
    print(f"  Format   : {result.content_format or '—'}")
    if result.risks:
        print("  Risks:")
        for r in result.risks:
            print(f"    - category {r.category} / {r.label_name} (label {r.label}), "
                  f"prob {r.prob:.3f}")
    if result.hit_strategy_ids:
        print(f"  Matched rules: {', '.join(result.hit_strategy_ids)}")
    if result.msg_id:
        print(f"  MsgID    : {result.msg_id}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deepfake-detect",
        description="Detect deepfake / manipulated images and videos via BytePlus.",
    )
    parser.add_argument("target", help="Local file path or http(s) URL of the image/video.")
    parser.add_argument(
        "--role", choices=["user", "assistant"], default="user",
        help="Content source: 'user' for uploads, 'assistant' for model output.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the full result as JSON.")
    parser.add_argument("--env", default=None, help="Path to a .env file.")
    # Optional credential overrides (use your own without a .env file).
    parser.add_argument("--ak", default=None, help="BytePlus Access Key ID (overrides .env).")
    parser.add_argument("--sk", default=None, help="BytePlus Secret Access Key (overrides .env).")
    parser.add_argument("--appid", default=None, help="Deepfake asset AppID (overrides .env).")
    parser.add_argument("--region", default=None, help="Region, e.g. ap-southeast-1.")
    parser.add_argument("--endpoint", default=None, help="Full endpoint override.")
    args = parser.parse_args(argv)

    try:
        if any((args.ak, args.sk, args.appid)):
            settings = Settings.from_values(
                ak=args.ak or "",
                sk=args.sk or "",
                appid=args.appid or "",
                region=args.region,
                endpoint=args.endpoint,
            )
        else:
            settings = Settings.from_env(env_path=args.env)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    detector = DeepfakeDetector(settings)

    try:
        if _is_url(args.target):
            result = detector.detect_url(args.target, role=args.role)
        else:
            result = detector.detect_file(args.target, role=args.role)
    except (MediaError, DetectionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_human(result)

    # Exit non-zero when manipulated so it composes in scripts/pipelines.
    return 3 if result.manipulated else 0


if __name__ == "__main__":
    raise SystemExit(main())
