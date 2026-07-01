"""Trajectory recorder adapted from DreamZero eval_utils/run_sim_eval.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from schemas_d2a import StepRecord


VIEW_ORDER = ("right", "wrist", "left")


def _as_uint8_image(image: Any) -> np.ndarray:
    if hasattr(image, "detach"):
        image = image.detach().cpu().numpy()
    arr = np.asarray(image)
    if arr.ndim == 4 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    if arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]
    return arr


def extract_views_from_obs(obs: dict[str, Any]) -> dict[str, np.ndarray]:
    policy = obs["policy"]
    return {
        "right": _as_uint8_image(policy["external_cam"]),
        "wrist": _as_uint8_image(policy["wrist_cam"]),
        "left": _as_uint8_image(policy["external_cam_2"]),
    }


class DreamZero2AHATrajectoryRecorder:
    """Save per-step camera frames and metadata for AHA-style processing."""

    def __init__(self, episode_dir: str | Path):
        self.episode_dir = Path(episode_dir)
        self.frames_dir = self.episode_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[StepRecord] = []
        self._views_by_step: list[dict[str, np.ndarray]] = []

    def record_step(
        self,
        step_index: int,
        views: dict[str, Any],
        action: Any | None = None,
        success_probe: dict[str, Any] | None = None,
    ) -> StepRecord:
        cached_views: dict[str, np.ndarray] = {}
        for view_name in VIEW_ORDER:
            if view_name not in views:
                continue
            arr = _as_uint8_image(views[view_name])
            cached_views[view_name] = arr

        action_list = None
        if action is not None:
            if hasattr(action, "detach"):
                action = action.detach().cpu().numpy()
            action_list = np.asarray(action).reshape(-1).astype(float).tolist()

        record = StepRecord(
            step_index=step_index,
            image_paths={},
            action=action_list,
            success_probe=success_probe or {},
        )
        self.records.append(record)
        self._views_by_step.append(cached_views)
        return record

    def write_frames(self, indices: list[int] | None = None) -> None:
        """Persist selected camera frames and update each record's image paths."""

        if indices is None:
            indices = list(range(len(self.records)))
        for record_index in indices:
            if record_index < 0 or record_index >= len(self.records):
                continue
            record = self.records[record_index]
            views = self._views_by_step[record_index]
            image_paths: dict[str, str] = {}
            for view_name in VIEW_ORDER:
                arr = views.get(view_name)
                if arr is None:
                    continue
                out_path = self.frames_dir / f"{view_name}_{record.step_index:04d}.png"
                Image.fromarray(arr).save(out_path)
                image_paths[view_name] = str(out_path)
            record.image_paths = image_paths

    def write_steps_json(self) -> Path:
        out_path = self.episode_dir / "steps.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump([record.to_dict() for record in self.records], f, indent=2)
        return out_path
