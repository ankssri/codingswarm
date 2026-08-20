"""Structured, UI-friendly representation of a detection response.

The BytePlus ``Moderate`` response is a nested Pydantic model. This module
flattens it into a small dataclass that the web UI and CLI can render directly,
and interprets the deepfake-specific fields (category 109, decision type 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Primary risk category returned for the deepfake-detection scenario.
DEEPFAKE_CATEGORY = "109"

# Decision types as documented for the deepfake scenario.
DECISION_PASS = 1   # Allow: content did not trigger the deepfake policy.
DECISION_BLOCK = 2  # Block: content triggered the deepfake policy.

DECISION_NAMES = {
    1: "Pass (Allow)",
    2: "Block",
    3: "Mark",
    4: "Replace",
    5: "Secure reply (Regenerate)",
}

# Human-readable labels for known deepfake sub-categories. The API may return
# labels not in this map; those are shown verbatim.
LABEL_NAMES = {
    "10900000": "Deepfake / manipulated media",
}


@dataclass
class Risk:
    """A single risk entry from ``RiskInfo.Risks``."""

    category: str
    label: str
    prob: float

    @property
    def is_deepfake(self) -> bool:
        return str(self.category) == DEEPFAKE_CATEGORY

    @property
    def label_name(self) -> str:
        return LABEL_NAMES.get(str(self.label), f"Label {self.label}")

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "label": self.label,
            "label_name": self.label_name,
            "prob": self.prob,
            "is_deepfake": self.is_deepfake,
        }


@dataclass
class DetectionResult:
    """Flattened, presentation-ready detection outcome."""

    manipulated: bool
    decision_type: int
    verdict: str
    summary: str
    probability: float | None
    content_format: str
    msg_id: str
    risks: list[Risk] = field(default_factory=list)
    hit_strategy_ids: list[str] = field(default_factory=list)
    degraded: bool = False
    degrade_reason: str = ""
    request_id: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def decision_name(self) -> str:
        return DECISION_NAMES.get(self.decision_type, f"Decision {self.decision_type}")

    def to_dict(self) -> dict:
        return {
            "manipulated": self.manipulated,
            "decision_type": self.decision_type,
            "decision_name": self.decision_name,
            "verdict": self.verdict,
            "summary": self.summary,
            "probability": self.probability,
            "content_format": self.content_format,
            "msg_id": self.msg_id,
            "risks": [r.to_dict() for r in self.risks],
            "hit_strategy_ids": self.hit_strategy_ids,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
            "request_id": self.request_id,
            "raw": self.raw,
        }

    # -- construction --------------------------------------------------------

    @classmethod
    def from_response_dict(cls, data: dict[str, Any]) -> "DetectionResult":
        """Build a result from the SDK response serialized with by_alias=True.

        Tolerates missing/None sections so a degraded or partial response still
        yields a usable object instead of raising.
        """
        meta = data.get("ResponseMetadata") or {}
        request_id = meta.get("RequestId", "") or ""
        error = meta.get("Error") or {}
        error_code = (error.get("Code") or "").strip()
        if error_code:
            raise DetectionError(
                error.get("Message") or f"Server returned error code {error_code}",
                code=error_code,
                request_id=request_id,
            )

        result = data.get("Result") or {}
        msg_id = result.get("MsgID", "") or ""
        content_format = result.get("ContentInfo", "") or ""
        degraded = bool(result.get("Degraded", False))
        degrade_reason = result.get("DegradeReason", "") or ""

        risk_info = result.get("RiskInfo") or {}
        raw_risks = risk_info.get("Risks") or []
        risks = [
            Risk(
                category=str(r.get("Category", "")),
                label=str(r.get("Label", "")),
                prob=float(r.get("Prob", 0.0) or 0.0),
            )
            for r in raw_risks
        ]

        decision = result.get("Decision") or {}
        decision_type = int(decision.get("DecisionType", DECISION_PASS) or DECISION_PASS)
        hit_ids = decision.get("HitStrategyIDs") or []
        hit_ids = [str(x) for x in hit_ids]

        deepfake_risks = [r for r in risks if r.is_deepfake]
        manipulated = decision_type == DECISION_BLOCK or bool(deepfake_risks)
        probability = max((r.prob for r in deepfake_risks), default=None)
        if probability is None and risks:
            probability = max(r.prob for r in risks)

        if manipulated:
            verdict = "Manipulated"
            pct = f"{probability * 100:.1f}%" if probability is not None else "n/a"
            summary = f"Deepfake / manipulated content detected (confidence {pct})."
        else:
            verdict = "Authentic"
            summary = "No manipulation detected. Content did not trigger the deepfake policy."

        if degraded:
            summary += f" [Detection degraded: {degrade_reason or 'unknown reason'}]"

        return cls(
            manipulated=manipulated,
            decision_type=decision_type,
            verdict=verdict,
            summary=summary,
            probability=probability,
            content_format=content_format,
            msg_id=msg_id,
            risks=risks,
            hit_strategy_ids=hit_ids,
            degraded=degraded,
            degrade_reason=degrade_reason,
            request_id=request_id,
            raw=data,
        )


class DetectionError(RuntimeError):
    """Raised when the API returns a server-side error."""

    def __init__(self, message: str, *, code: str = "", request_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id
