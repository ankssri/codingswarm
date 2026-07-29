"""Dataclasses describing the state the swarm builds up during a run."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class FeatureStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Feature:
    """A single unit of work the swarm builds, tests, and reviews."""

    id: str
    name: str
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    status: FeatureStatus = FeatureStatus.PENDING
    attempts: int = 0
    # History of what happened across build/test/review attempts.
    log: list[str] = field(default_factory=list)
    # Final test outcome + review outcomes for reporting.
    tests_passed: bool = False
    review_approved: bool = False
    review_score: int | None = None
    security_approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Requirements:
    summary: str = ""
    functional: list[str] = field(default_factory=list)
    non_functional: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestOutcome:
    passed: bool
    returncode: int
    output: str
    duration_s: float = 0.0


@dataclass
class ReviewOutcome:
    approved: bool
    score: int | None
    issues: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ProjectState:
    """Everything the swarm knows about the project under construction."""

    idea: str
    name: str
    target_language: str = "python"
    requirements: Requirements | None = None
    design: str = ""
    features: list[Feature] = field(default_factory=list)
    # path -> content of the generated (non-test) source files.
    source_files: dict[str, str] = field(default_factory=dict)
    # path -> content of the generated test files.
    test_files: dict[str, str] = field(default_factory=dict)

    def all_files(self) -> dict[str, str]:
        merged = dict(self.source_files)
        merged.update(self.test_files)
        return merged

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea": self.idea,
            "name": self.name,
            "target_language": self.target_language,
            "requirements": self.requirements.to_dict() if self.requirements else None,
            "design": self.design,
            "features": [f.to_dict() for f in self.features],
            "source_files": sorted(self.source_files),
            "test_files": sorted(self.test_files),
        }
