"""Shared schemas for DreamZero-to-AHA rollout attribution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


FailureType = Literal[
    "grasp_failure",
    "object_slip",
    "wrong_object",
    "wrong_location",
    "placement_failure",
    "collision_or_blockage",
    "no_progress",
    "timeout",
    "unknown",
    "other",
]


@dataclass
class StepRecord:
    """One DreamZero simulation step saved for later AHA-style attribution."""

    step_index: int
    image_paths: dict[str, str]
    action: list[float] | None = None
    success_probe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AttributionResult:
    """AHA-style attribution metadata normalized for downstream reporting."""

    success_answer: str | None = None
    failure_type: FailureType = "unknown"
    failure_reason: str | None = None
    raw_text: str | None = None
    plugin_name: str = "none"
    artifact_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EpisodeResult:
    """Final per-episode result written as JSON."""

    episode: int
    scene: int
    prompt: str
    success: bool | Literal["unknown"]
    end_reason: str
    steps: int
    output_dir: str
    video_path: str | None = None
    aha_grid_path: str | None = None
    aha_request_path: str | None = None
    attribution: AttributionResult | None = None
    success_probe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        failure_type = None
        if self.success != True and self.attribution is not None:
            failure_type = self.attribution.failure_type

        return {
            "episode": self.episode,
            "scene": self.scene,
            "prompt": self.prompt,
            "success": self.success,
            "failure_type": failure_type,
            # Task progress is not implemented yet.
            # "progress_score": None,
            "video_path": self.video_path,
            "aha_grid_path": self.aha_grid_path,
            "aha_request_path": self.aha_request_path,
            "end_reason": self.end_reason,
            "steps": self.steps,
            "output_dir": self.output_dir,
            "success_probe": self.success_probe,
        }


def ensure_path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)
